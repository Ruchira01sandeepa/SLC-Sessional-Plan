"""A player's individual seasonal (macrocycle) plan in 16 steps (Zatsiorsky & Kraemer ch. 1 and 5).
STEP 0 answers are saved per player and season; the plan is rebuilt from them on demand and is never built before STEP 0 is answered."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.planning import athlete_season_plan as asp
from app.exports.excel.athlete_season_plan_excel import build_athlete_workbook
from app.core.db import get_db
from app.core.deps import audit, current_user
from app.reference.exercises import groups_for
from app.core.models import AthletePlanInput, CalendarEvent, EventType, Player, TestSession, User
from app.core.permissions import authorize_squad
from app.assessment.test_battery import AREA_LABEL, BY_KEY, WINDOW_LABEL, WINDOWS, display
from app.workload.workload_service import today_lk
from app.api.plans import _local_date, _utc_naive
from app.api.testing import XLSX, _bowling, _file_name, _player_in_squad, _season, _windows_for

router = APIRouter(tags=["athlete-plan"])
ROLE_LABEL = {"fast_bowler": "Fast bowler", "spin_bowler": "Spin bowler", "batter": "Batter", "bat_wicketkeeper": "Batting wicketkeeper",
              "all_rounder": "All-rounder"}


class CompIn(BaseModel):
    name: str = Field(max_length=120)
    start: date
    days: int = Field(1, ge=1, le=60)
    importance: str = Field("secondary", pattern="^(main|secondary)$")


class PeriodIn(BaseModel):
    name: str = Field("Exams", max_length=80)
    start: date
    end: date


class Step0In(BaseModel):
    position: str | None = Field(None, max_length=120)
    age: int | None = Field(None, ge=8, le=60)
    sex: str | None = Field(None, pattern="^(male|female)$")
    body_weight_kg: float | None = Field(None, ge=20, le=150)
    training_age_years: float | None = Field(None, ge=0, le=30)
    level: str | None = Field(None, pattern="^(beginner|qualified|elite)$")
    competitions: list[CompIn] = Field(default_factory=list, max_length=40)
    plan_start: date | None = None
    plan_end: date | None = None
    training_days: int | None = Field(None, ge=1, le=7)
    sessions_per_day: int | None = Field(None, ge=1, le=3)
    sport_result: str | None = Field(None, max_length=300)
    limiting: list[str] = Field(default_factory=list, max_length=8)
    injuries: str | None = Field(None, max_length=500)
    recovery: str | None = Field(None, max_length=300)
    equipment: str | None = Field(None, max_length=300)
    school_periods: list[PeriodIn] = Field(default_factory=list, max_length=10)
    last_season_peak: str | None = Field(None, max_length=200)
    last_season_loads: str | None = Field(None, max_length=300)
    load_increase: str | None = Field(None, pattern="^(mild|normal|sharp)$")


def _context(db: Session, squad_id: int, season_id: int, player: Player) -> dict:
    """What the app already knows for STEP 0: position, age, sex, body weight, the season and its matches, test results and ranks."""
    season = _season(db, squad_id, season_id)
    today = today_lk()
    wins = _windows_for(db, squad_id, season_id)
    window = next((w for w in reversed(WINDOWS) if w in wins and player.id in wins[w][1]), None)
    tests, limiting = [], []
    if window:
        cats, sessions = wins[window]
        finals = {r.test_key: r.final_value for r in sessions[player.id].results if r.final_value is not None and r.test_key in BY_KEY}
        ranks = {a["area"]: a["percentile"] for a in (cats.get(player.id) or {}).get("areas", [])}
        for k, v in finals.items():
            t = BY_KEY[k]
            tests.append({"test": t.label, "value": f"{display(t, v)} {t.unit}", "rank": ranks.get(t.area), "area": AREA_LABEL[t.area]})
        for area, pct in sorted(ranks.items(), key=lambda x: (x[1] if x[1] is not None else 99)):
            ab = asp.AREA_ABILITY.get(area)
            if pct is not None and pct < 50 and ab and ab not in limiting:
                limiting.append(ab)
    weight = db.scalar(select(TestSession.weight_kg).where(TestSession.player_id == player.id, TestSession.weight_kg.is_not(None))
                       .order_by(TestSession.test_date.desc()).limit(1))
    matches = [_local_date(e.start_at) for e in db.scalars(select(CalendarEvent).where(
        CalendarEvent.squad_id == squad_id, CalendarEvent.event_type == EventType.match,
        CalendarEvent.start_at >= _utc_naive(min(today, season.start_date), False), CalendarEvent.start_at < _utc_naive(season.end_date, True)))]
    days = (season.end_date - season.start_date).days + 1
    comps = ([{"name": season.name, "start": season.start_date.isoformat(), "days": days, "importance": "main"}] if days <= 28 else
             [{"name": f"Match {d:%d %b}", "start": d.isoformat(), "days": 1, "importance": "secondary"} for d in sorted(set(matches))])
    d = player.date_of_birth
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    position = ROLE_LABEL.get(player.role.value, player.role.value) + (f" ({player.style})" if player.style else "")
    prefill = {"sport": "Cricket", "position": position, "age": age, "sex": player.gender.value, "body_weight_kg": weight,
               "competitions": comps, "plan_start": max(today, min(today, season.start_date)).isoformat(),
               "season_name": season.name, "season_start": season.start_date.isoformat(), "season_end": season.end_date.isoformat(),
               "limiting": limiting + (["technique"] if limiting else [])}
    return {"season": season, "today": today, "prefill": prefill, "tests": tests, "matches": matches,
            "window": WINDOW_LABEL[window] if window else None}


def _saved(db: Session, season_id: int, player_id: int) -> AthletePlanInput | None:
    return db.scalar(select(AthletePlanInput).where(AthletePlanInput.season_id == season_id, AthletePlanInput.player_id == player_id))


@router.get("/squads/{squad_id}/seasons/{season_id}/athlete-plans/{player_id}/step0")
def get_step0(squad_id: int, season_id: int, player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """STEP 0: the questions, what the app already knows (prefill) and the coach's saved answers."""
    authorize_squad(db, user, squad_id, "testing.read")
    p = _player_in_squad(db, squad_id, player_id)
    ctx = _context(db, squad_id, season_id, p)
    row = _saved(db, season_id, p.id)
    return {"player": {"id": p.id, "name": p.full_name, "role": p.role.value}, "season": {"id": ctx["season"].id, "name": ctx["season"].name},
            "questions": [{"n": n, "text": t} for n, t in asp.QUESTIONS], "prefill": ctx["prefill"], "tests": ctx["tests"],
            "test_window": ctx["window"], "answers": row.answers if row else None, "saved_at": row.updated_at if row else None,
            "abilities": asp.ABILITY, "levels": asp.LEVELS, "increase": {k: v[0] for k, v in asp.INCREASE.items()}}


@router.put("/squads/{squad_id}/seasons/{season_id}/athlete-plans/{player_id}/step0")
def put_step0(squad_id: int, season_id: int, player_id: int, body: Step0In, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "testing.write")
    _season(db, squad_id, season_id)
    p = _player_in_squad(db, squad_id, player_id)
    bad = [x for x in body.limiting if x not in asp.ABILITY]
    if bad:
        raise HTTPException(422, f"Unknown ability: {', '.join(bad)}")
    if any(sp.end < sp.start for sp in body.school_periods):
        raise HTTPException(422, "A school / exam period ends before it starts")
    row = _saved(db, season_id, p.id)
    data = body.model_dump(mode="json")
    if row is None:
        row = AthletePlanInput(season_id=season_id, player_id=p.id, answers=data, updated_by=user.id)
        db.add(row)
    else:
        row.answers, row.updated_by = data, user.id
    audit(db, user, "athlete_plan.step0_saved", "player", p.id)
    db.commit()
    return {"ok": True}


def _build(db: Session, user: User, squad_id: int, season_id: int, player_id: int) -> tuple[dict, Player]:
    authorize_squad(db, user, squad_id, "testing.read")
    p = _player_in_squad(db, squad_id, player_id)
    row = _saved(db, season_id, p.id)
    if row is None:
        raise HTTPException(409, "Answer STEP 0 first: the plan is not built until the inputs are answered.")
    ctx = _context(db, squad_id, season_id, p)
    plan = asp.build_athlete_plan(answers=row.answers, prefill=ctx["prefill"], role=p.role.value,
                                  role_groups=groups_for(p.role.value, _bowling(p)) or ["fielding"], today=ctx["today"],
                                  matches=ctx["matches"], tests=ctx["tests"])
    plan["player"] = {"id": p.id, "name": p.full_name, "role": p.role.value}
    plan["season"] = {"id": ctx["season"].id, "name": ctx["season"].name}
    return plan, p


@router.get("/squads/{squad_id}/seasons/{season_id}/athlete-plans/{player_id}.xlsx")
def get_plan_xlsx(squad_id: int, season_id: int, player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan, p = _build(db, user, squad_id, season_id, player_id)
    audit(db, user, "athlete_plan.exported", "player", p.id)
    db.commit()
    name = _file_name("Seasonal-plan-16-steps", p.full_name, plan["season"]["name"])
    return Response(build_athlete_workbook(plan), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/athlete-plans/{player_id}")
def get_plan(squad_id: int, season_id: int, player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """STEPS 1-16 for one athlete, built from the saved STEP 0 answers."""
    return _build(db, user, squad_id, season_id, player_id)[0]
