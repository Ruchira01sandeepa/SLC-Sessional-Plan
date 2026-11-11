"""A player's individual plan: generated, edited and saved by a coach as versions, and tracked session by session.

The plan IN USE is the newest saved version for the season, or a freshly generated plan when none is saved yet.
Logged focus sessions are checked against the plan in use and move each exercise's dose automatically (plan_progress.py)."""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..individual_plan_excel import build_player_workbook
from ..models import EventType, IndividualPlanVersion, PlanExerciseLog, Player, User, WorkloadLog
from ..permissions import authorize_player
from ..plan_edits import EditError, apply_edits
from ..plan_progress import plan_progress
from ..test_progress import progress as build_progress
from ..workload_service import sync_alerts, today_lk
from .testing import XLSX, _bowling, _default_season, _grid, _plan, _plan_json, _player_windows, _windows_for, _workload

router = APIRouter(tags=["individual plan"])


class EditsIn(BaseModel):
    base: str = Field(default="saved", pattern="^(saved|fresh)$")     # edit the newest saved version, or a freshly generated plan
    edits: list[dict] = Field(default_factory=list, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    season_id: int | None = None
    window: str | None = None


class LogItem(BaseModel):
    phase: str = Field(max_length=20)
    area: str = Field(max_length=30)
    exercise: str = Field(max_length=200)
    sets_done: int | None = Field(default=None, ge=0, le=100)
    reps_done: int | None = Field(default=None, ge=0, le=500)
    technique_ok: bool = True
    pain: bool = False
    note: str | None = Field(default=None, max_length=300)


class SessionIn(BaseModel):
    log_date: date | None = None
    minutes: int | None = Field(default=None, ge=1, le=300)          # with rpe: also logged as a training session in the workload
    rpe: int | None = Field(default=None, ge=1, le=10)
    season_id: int | None = None
    items: list[LogItem] = Field(min_length=1, max_length=40)


def _latest(db: Session, player_id: int, season_id: int) -> IndividualPlanVersion | None:
    return db.scalar(select(IndividualPlanVersion).where(IndividualPlanVersion.player_id == player_id, IndividualPlanVersion.season_id == season_id)
                     .order_by(IndividualPlanVersion.version.desc()).limit(1))


def _meta(v: IndividualPlanVersion, db: Session) -> dict:
    by = db.get(User, v.created_by) if v.created_by else None
    return {"version": v.version, "saved_at": v.created_at.isoformat(), "saved_by": by.full_name if by else None, "based_on": v.based_on,
            "note": v.note, "window": v.window, "edits": len(v.edits or [])}


def _generated(db: Session, user: User, p: Player, season_id: int | None, window: str | None) -> dict:
    plan, summary, _, season, _ = _plan(db, user, p, season_id, window)
    return jsonable_encoder(_plan_json(plan, summary, season))


def _logs(db: Session, p: Player) -> list[dict]:
    return [{"log_date": l.log_date, "phase": l.phase, "area": l.area, "exercise": l.exercise, "sets_done": l.sets_done, "reps_done": l.reps_done,
             "technique_ok": l.technique_ok, "pain": l.pain} for l in db.scalars(select(PlanExerciseLog).where(PlanExerciseLog.player_id == p.id))]


def _in_use(db: Session, user: User, p: Player, season_id: int | None, window: str | None, fresh: bool) -> tuple[dict, IndividualPlanVersion | None]:
    season = _default_season(db, p.squad_id, season_id)
    saved = _latest(db, p.id, season.id)
    if saved and not fresh:
        return dict(saved.data), saved
    return _generated(db, user, p, season.id, window), saved


def _with_progress(db: Session, p: Player, plan: dict, saved: IndividualPlanVersion | None, shown_saved: bool) -> dict:
    ready, _ = _workload(db, p)
    return {**plan, "saved": _meta(saved, db) if saved and shown_saved else None, "latest_saved": _meta(saved, db) if saved else None,
            "current_readiness": ready, "progress": plan_progress(plan, _logs(db, p), today_lk(), ready["status"])}


@router.get("/players/{player_id}/individual-plan")
def individual_plan(player_id: int, season_id: int | None = None, window: str | None = None, fresh: bool = False,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The plan in use (newest saved version), or a freshly generated plan with fresh=true or when none is saved."""
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    plan, saved = _in_use(db, user, p, season_id, window, fresh)
    return _with_progress(db, p, plan, saved, shown_saved=bool(saved and not fresh))


def _edited(db: Session, user: User, p: Player, body: EditsIn) -> tuple[dict, IndividualPlanVersion | None, str]:
    plan, saved = _in_use(db, user, p, body.season_id, body.window, fresh=body.base == "fresh")
    based_on = f"version {saved.version}" if saved and body.base == "saved" else "generated"
    try:
        out = apply_edits(plan, body.edits)
    except EditError as e:
        raise HTTPException(422, str(e))
    if body.note is not None:
        out["coach_note"] = body.note.strip() or None
    return out, saved, based_on


@router.post("/players/{player_id}/individual-plan/preview")
def preview(player_id: int, body: EditsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The plan with the edits applied, NOT saved. The screen calls this after every change."""
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    out, saved, _ = _edited(db, user, p, body)
    return _with_progress(db, p, out, saved, shown_saved=False)


@router.post("/players/{player_id}/individual-plan/versions", status_code=201)
def save_version(player_id: int, body: EditsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    out, prev, based_on = _edited(db, user, p, body)
    season_id = out["season"]["id"]
    n = (db.scalar(select(func.max(IndividualPlanVersion.version)).where(IndividualPlanVersion.player_id == p.id,
                                                                        IndividualPlanVersion.season_id == season_id)) or 0) + 1
    out.pop("saved", None), out.pop("latest_saved", None), out.pop("progress", None), out.pop("current_readiness", None)
    v = IndividualPlanVersion(player_id=p.id, season_id=season_id, window=out.get("summary", {}).get("window") or body.window or "baseline",
                              version=n, data=jsonable_encoder(out), edits=body.edits or None, based_on=based_on,
                              note=(body.note or "").strip() or None, created_by=user.id)
    db.add(v)
    db.flush()
    audit(db, user, "individual_plan.saved", "player", p.id, f"version {n}, {len(body.edits)} edit(s), from {based_on}")
    db.commit()
    return _with_progress(db, p, v.data, v, shown_saved=True)


@router.get("/players/{player_id}/individual-plan/versions")
def list_versions(player_id: int, season_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    season = _default_season(db, p.squad_id, season_id)
    rows = db.scalars(select(IndividualPlanVersion).where(IndividualPlanVersion.player_id == p.id, IndividualPlanVersion.season_id == season.id)
                      .order_by(IndividualPlanVersion.version.desc()))
    return [_meta(v, db) for v in rows]


@router.get("/players/{player_id}/individual-plan/versions/{version}")
def get_version(player_id: int, version: int, season_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    season = _default_season(db, p.squad_id, season_id)
    v = db.scalar(select(IndividualPlanVersion).where(IndividualPlanVersion.player_id == p.id, IndividualPlanVersion.season_id == season.id,
                                                      IndividualPlanVersion.version == version))
    if v is None:
        raise HTTPException(404, "Plan version not found")
    return {**v.data, "saved": _meta(v, db), "edit_list": v.edits or []}


def _dated(plan: dict) -> dict:
    """Saved plans hold dates as text; the Excel writer needs dates."""
    out = dict(plan)
    out["weeks"] = [{**w, "start": date.fromisoformat(str(w["start"])[:10])} for w in plan["weeks"]]
    out["reviews"] = [{**r, "date": date.fromisoformat(str(r["date"])[:10])} for r in plan.get("reviews", [])]
    return out


@router.get("/players/{player_id}/individual-plan.xlsx")
def individual_plan_xlsx(player_id: int, season_id: int | None = None, window: str | None = None, fresh: bool = False,
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    plan, saved = _in_use(db, user, p, season_id, window, fresh)
    season = _default_season(db, p.squad_id, plan["season"]["id"])
    g = _grid(db, user, p.squad_id, season.id)
    audit(db, user, "individual_plan.exported", "player", p.id, f"version {saved.version}" if saved and not fresh else "generated")
    db.commit()
    win = plan.get("summary", {}).get("window") or window or "plan"
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"individual-plan-{p.full_name}-{season.name}-{win}").strip("-") or "individual-plan"
    prog = build_progress(_player_windows(p.id, _windows_for(db, p.squad_id, season.id)))
    return Response(build_player_workbook(plan["summary"], _dated(plan), g, _bowling(p), prog), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


# ───────────── logging focus sessions against the plan ─────────────
@router.post("/players/{player_id}/plan-sessions", status_code=201)
def log_session(player_id: int, body: SessionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    day = body.log_date or today_lk()
    if day > today_lk():
        raise HTTPException(422, "A session cannot be logged in the future")
    plan, saved = _in_use(db, user, p, body.season_id, None, fresh=False)
    known = {(ph["phase"], a["area"], e["name"]) for ph in plan["phases"] for a in ph["areas"] for e in a["exercises"]}
    bad = [f"{i.exercise} ({i.area}, {i.phase})" for i in body.items if (i.phase, i.area, i.exercise) not in known]
    if bad:
        raise HTTPException(422, "Not in the player's plan: " + "; ".join(bad))
    for i in body.items:
        db.add(PlanExerciseLog(player_id=p.id, plan_version_id=saved.id if saved else None, log_date=day, phase=i.phase, area=i.area,
                               exercise=i.exercise, sets_done=i.sets_done, reps_done=i.reps_done, technique_ok=i.technique_ok, pain=i.pain,
                               note=(i.note or "").strip() or None, recorded_by=user.id))
    if body.minutes and body.rpe:                       # the focus session also counts in the workload (RPE x minutes)
        db.add(WorkloadLog(player_id=p.id, log_date=day, session_type=EventType.training, attended=True, duration_min=body.minutes, rpe=body.rpe,
                           recorded_by=user.id))
        db.flush()
        sync_alerts(db, p)
    audit(db, user, "plan_session.logged", "player", p.id, f"{len(body.items)} exercise(s) on {day.isoformat()}"
          + (", pain reported" if any(i.pain for i in body.items) else ""))
    db.commit()
    return _with_progress(db, p, plan, saved, shown_saved=bool(saved))


@router.get("/players/{player_id}/plan-sessions")
def list_sessions(player_id: int, limit: int = Query(60, ge=1, le=500), db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    rows = db.scalars(select(PlanExerciseLog).where(PlanExerciseLog.player_id == p.id).order_by(PlanExerciseLog.log_date.desc(), PlanExerciseLog.id)
                      .limit(limit))
    return [{"id": r.id, "log_date": r.log_date.isoformat(), "phase": r.phase, "area": r.area, "exercise": r.exercise, "sets_done": r.sets_done,
             "reps_done": r.reps_done, "technique_ok": r.technique_ok, "pain": r.pain, "note": r.note} for r in rows]
