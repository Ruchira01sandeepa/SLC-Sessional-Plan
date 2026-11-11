"""SLC U15 SOP physical tests: Excel template, import, results on the player profile, categories and the individual plan.

Admin / S&C download a template pre-filled with the squad's players, fill it, and upload it. The upload is previewed first
(nothing is saved) and then confirmed. Results are confidential: players do not see them."""
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import categorisation as cz
from ..db import get_db
from ..deps import audit, current_user
from ..age_norms import age_band
from ..exercises import bowling_types
from ..individual_plan import build_individual_plan
from ..individual_plan_excel import build_player_workbook
from ..models import (FitnessPhase, PdpRating, PdpRubricItem, Player, PlayerRole, Screening, Season, SkillTemplate, TestImportBatch,
                      TestResult, TestSession, User)
from .development import latest_role_skills
from ..permissions import authorize_player, authorize_squad
from ..test_battery import BY_KEY, LEVEL_LABEL, TRIALS, WINDOW_LABEL, WINDOWS, display
from ..test_import import MAX_BYTES, parse_workbook
from ..test_progress import progress as build_progress
from ..test_template_excel import build_template
from ..workload_service import evaluate_player, evaluate_players, today_lk
from .plans import _grid

router = APIRouter(tags=["testing"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ───────────── helpers ─────────────
def _window(w: str | None) -> str:
    if w not in WINDOWS:
        raise HTTPException(422, f"window must be one of {', '.join(WINDOWS)}")
    return w


def _season(db: Session, squad_id: int, season_id: int) -> Season:
    s = db.get(Season, season_id)
    if s is None or s.squad_id != squad_id:
        raise HTTPException(404, "Season not found")
    return s


def _finals(s: TestSession) -> dict:
    return {r.test_key: r.final_value for r in s.results if r.final_value is not None and r.test_key in BY_KEY}


def _cohort_entries(db: Session, squad_id: int, season_id: int, window: str) -> tuple[list[dict], dict[int, TestSession]]:
    sessions = list(db.scalars(select(TestSession).join(Player, Player.id == TestSession.player_id).where(
        Player.squad_id == squad_id, Player.is_active, TestSession.season_id == season_id, TestSession.window == FitnessPhase(window))))
    return [{"player_id": s.player_id, "level": s.level, "finals": _finals(s)} for s in sessions], {s.player_id: s for s in sessions}


def _workload(db: Session, player: Player) -> tuple[dict, dict]:
    """(readiness, workload summary) from the player's logged sessions and open alerts."""
    _, summ = evaluate_player(db, player, today_lk())
    return cz.readiness(summ.get("alerts_worst"), player.availability.value), summ


def _readiness(db: Session, player: Player) -> dict:
    return _workload(db, player)[0]


def _bowling(player: Player) -> set[str] | None:
    return bowling_types(player.role.value, player.style)


def _default_season(db: Session, squad_id: int, season_id: int | None) -> Season:
    if season_id is not None:
        return _season(db, squad_id, season_id)
    s = db.scalar(select(Season).where(Season.squad_id == squad_id).order_by(Season.start_date.desc()).limit(1))
    if s is None:
        raise HTTPException(404, "This squad has no season yet")
    return s


def _default_window(db: Session, player: Player, season_id: int, window: str | None) -> str:
    if window:
        return _window(window)
    for w in ("end_season", "mid_season", "baseline"):
        if db.scalar(select(TestSession.id).where(TestSession.player_id == player.id, TestSession.season_id == season_id,
                                                 TestSession.window == FitnessPhase(w))):
            return w
    return "baseline"


def _trial_shown(t, v):
    return display(t, v) if v is not None else None


def _session_out(s: TestSession) -> dict:
    res = {}
    for r in s.results:
        t = BY_KEY.get(r.test_key)
        if t:
            res[t.key] = {"label": t.label, "unit": t.unit, "area": t.area, "trials": [_trial_shown(t, v) for v in (r.trial_1, r.trial_2, r.trial_3)],
                          "final": _trial_shown(t, r.final_value), "setup": r.setup}
    return {"window": s.window.value, "window_label": WINDOW_LABEL[s.window.value], "level": s.level, "level_label": LEVEL_LABEL[s.level],
            "test_date": s.test_date.isoformat() if s.test_date else None, "height_cm": s.height_cm, "weight_kg": s.weight_kg,
            "test_version": s.test_version, "surface": s.surface, "timing_method": s.timing_method, "notes": s.notes, "results": res}


def _summary(player: Player, window: str, sess: TestSession | None, cat: dict | None) -> dict:
    by_key = {r.test_key: r for r in sess.results} if sess else {}
    areas = []
    for a in (cat["areas"] if cat else []):
        tests = []
        for t in a["tests"]:
            r = by_key.get(t["key"])
            bt = BY_KEY[t["key"]]
            tests.append({**t, "trials_display": [(_trial_shown(bt, v) if v is not None else None) for v in
                                                  ((r.trial_1, r.trial_2, r.trial_3) if r else (None,) * TRIALS)],
                          "age": age_band(t["key"], t.get("value"), player.squad.age_group if player.squad else None, player.gender.value)})
        areas.append({**a, "tests": tests})
    return {"player_id": player.id, "player": player.full_name, "role": player.role.value, "window": window, "window_label": WINDOW_LABEL[window],
            "level": sess.level if sess else None, "level_label": LEVEL_LABEL[sess.level] if sess else "Not tested",
            "band": cat["band"] if cat else None, "band_label": cat["band_label"] if cat else None, "overall": cat["overall"] if cat else None,
            "note": cat["note"] if cat else "No test results for this window.", "areas": areas,
            "areas_counted": cat["areas_counted"] if cat else 0, "areas_total": cat["areas_total"] if cat else 0,
            "cohort_size": cat["cohort_size"] if cat else 0,
            "focus_areas": cat["focus_areas"] if cat else [],
            "height_cm": sess.height_cm if sess else None, "weight_kg": sess.weight_kg if sess else None}


# ───────────── template and import ─────────────
@router.get("/squads/{squad_id}/test-template.xlsx")
def template(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    squad = authorize_squad(db, user, squad_id, "testing.write")
    season = _season(db, squad_id, season_id)
    window = _window(window)
    players = [{"id": p.id, "name": p.full_name} for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.full_name))]
    if not players:
        raise HTTPException(422, "This squad has no active players yet")
    audit(db, user, "test_template.downloaded", "squad", squad_id)
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"{squad.age_group.lower()}-test-template-{squad.name}-{window}").strip("-")
    return Response(build_template(squad={"id": squad.id, "name": squad.name}, season={"id": season.id, "name": season.name}, window=window, players=players),
                    media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.post("/squads/{squad_id}/test-import")
async def import_results(squad_id: int, request: Request, season_id: int, window: str, confirm: bool = False, filename: str | None = None,
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Body = the .xlsx file as raw bytes. confirm=false previews (nothing saved); confirm=true saves the accepted rows."""
    squad = authorize_squad(db, user, squad_id, "testing.write")
    _season(db, squad_id, season_id)
    window = _window(window)
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise HTTPException(400, "Invalid Content-Length header")
    if declared > MAX_BYTES:
        raise HTTPException(413, "The file is too large")
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The file is too large")
    players = {p.id: p.full_name for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active))}
    try:
        parsed = parse_workbook(data, players, squad.age_group)
    except ValueError as e:
        raise HTTPException(422, str(e))
    m = parsed["meta"]
    if (m.get("squad_id"), m.get("season_id"), m.get("window")) != (str(squad_id), str(season_id), window):
        raise HTTPException(422, "This file was made for a different squad, season or test window. Download the template again for the one you are importing.")

    accepted = [{"player_id": r["player_id"], "player": players[r["player_id"]], "level": r["level"], "level_label": LEVEL_LABEL[r["level"]], "sheet": r["sheet"], "row": r["row"],
                 "results": {BY_KEY[k].label: display(BY_KEY[k], v["final"]) for k, v in r["results"].items()}}
                for r in parsed["rows"]]
    out = {"saved": False, "accepted": accepted, "errors": parsed["errors"], "blank_rows": parsed["blank_rows"], "batch_id": None}
    if not confirm:
        return out
    if not parsed["rows"]:
        raise HTTPException(422, "There are no valid rows to save. Fix the listed errors and upload again.")

    batch = TestImportBatch(squad_id=squad_id, season_id=season_id, window=FitnessPhase(window), filename=(filename or "")[:200] or None,
                            uploaded_by=user.id, rows_ok=len(parsed["rows"]), rows_rejected=len({(e["sheet"], e["row"]) for e in parsed["errors"]}))
    db.add(batch)
    db.flush()
    for r in parsed["rows"]:
        old = db.scalar(select(TestSession).where(TestSession.player_id == r["player_id"], TestSession.season_id == season_id, TestSession.window == FitnessPhase(window)))
        if old is not None:                                  # re-import of the same window replaces it
            db.delete(old)
            db.flush()
        s = TestSession(player_id=r["player_id"], season_id=season_id, window=FitnessPhase(window), level=r["level"], test_date=r["test_date"], cleared=True,
                        height_cm=r["height_cm"], weight_kg=r["weight_kg"], test_version=r["version"], surface=r["surface"], timing_method=r["timing"],
                        notes=r["notes"], tested_by=user.id, batch_id=batch.id)
        for k, v in r["results"].items():
            t1, t2, t3 = v["trials"]
            s.results.append(TestResult(test_key=k, trial_1=t1, trial_2=t2, trial_3=t3, final_value=v["final"], setup=v["setup"]))
        db.add(s)
    audit(db, user, "test_results.imported", "squad", squad_id, f"{len(parsed['rows'])} rows, {batch.rows_rejected} rejected, window {window}")
    db.commit()
    out.update(saved=True, batch_id=batch.id)
    return out


# ───────────── results and categories ─────────────
@router.get("/squads/{squad_id}/seasons/{season_id}/test-categories")
def squad_categories(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every active player of the squad: level, band, focus areas and readiness for one test window."""
    authorize_squad(db, user, squad_id, "testing.read")
    _season(db, squad_id, season_id)
    window = _window(window)
    entries, sessions = _cohort_entries(db, squad_id, season_id, window)
    cats = cz.categorise(entries)
    rows = []
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.full_name)))
    evals = evaluate_players(db, players, today_lk())                 # one batch for the squad, not one evaluation per player
    for p in players:
        cat, sess = cats.get(p.id), sessions.get(p.id)
        rows.append({"player_id": p.id, "player": p.full_name, "role": p.role.value, "level": sess.level if sess else None,
                     "level_label": LEVEL_LABEL[sess.level] if sess else None, "band": cat["band"] if cat else None,
                     "band_label": cat["band_label"] if cat else None, "overall": cat["overall"] if cat else None,
                     "focus_areas": [f["label"] for f in cat["focus_areas"]] if cat else [], "note": cat["note"] if cat else None,
                     "readiness": cz.readiness(evals[p.id][1].get("alerts_worst"), p.availability.value)})
    return {"window": window, "window_label": WINDOW_LABEL[window], "min_cohort": cz.MIN_COHORT, "band_names": list(cz.BAND_NAMES), "players": rows}


@router.get("/players/{player_id}/testing")
def player_testing(player_id: int, season_id: int | None = None, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """All test windows for the player, plus the category and readiness for the chosen window."""
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    season = _default_season(db, p.squad_id, season_id)
    window = _default_window(db, p, season.id, window)
    sessions = list(db.scalars(select(TestSession).where(TestSession.player_id == p.id, TestSession.season_id == season.id)))
    order = {w: i for i, w in enumerate(WINDOWS)}
    sessions.sort(key=lambda s: order[s.window.value])
    entries, by_player = _cohort_entries(db, p.squad_id, season.id, window)
    cat = cz.categorise(entries).get(p.id)
    return {"season": {"id": season.id, "name": season.name}, "window": window, "sessions": [_session_out(s) for s in sessions],
            "category": _summary(p, window, by_player.get(p.id), cat), "readiness": _readiness(db, p),
            "band_names": list(cz.BAND_NAMES), "min_cohort": cz.MIN_COHORT}


# ───────────── the player's own seasonal plan ─────────────
def _plan(db: Session, user: User, p: Player, season_id: int | None, window: str | None):
    season = _default_season(db, p.squad_id, season_id)
    window = _default_window(db, p, season.id, window)
    entries, by_player = _cohort_entries(db, p.squad_id, season.id, window)
    cat = cz.categorise(entries).get(p.id)
    g = _grid(db, user, p.squad_id, season.id)
    ready, summ = _workload(db, p)
    plan = build_individual_plan(player={"name": p.full_name, "role": p.role.value, "date_of_birth": p.date_of_birth, "gender": p.gender.value,
                                         "age_group": p.squad.age_group if p.squad else None,
                                         "maturity_status": p.maturity_status.value, "custom_limits": p.workload_limits},
                                 cat=cat, ready=ready, g=g, bowling_types=_bowling(p), workload=summ,
                                 extra=_personal_inputs(db, p, season.id, window, entries))
    return plan, _summary(p, window, by_player.get(p.id), cat), g, season, window


def _personal_inputs(db: Session, p: Player, season_id: int, window: str, entries: list[dict]) -> dict:
    """Everything else the individual plan uses: the previous window, growth, coach ratings, screening, the player's test group."""
    mine = next((e for e in entries if e["player_id"] == p.id), None)
    cohort: dict[str, list[float]] = {}
    for e in entries:
        if mine and e["level"] == mine["level"]:
            for k, v in e["finals"].items():
                cohort.setdefault(k, []).append(v)
    prev_cat = None
    for w in reversed(WINDOWS[:WINDOWS.index(window)]):
        prev_entries, prev_sessions = _cohort_entries(db, p.squad_id, season_id, w)
        if p.id in prev_sessions:
            prev_cat = cz.categorise(prev_entries).get(p.id)
            break
    heights = [(s.test_date, s.height_cm) for s in db.scalars(select(TestSession).where(TestSession.player_id == p.id))
               if s.test_date and s.height_cm]
    pdp = {}
    for r, item in db.execute(select(PdpRating, PdpRubricItem).join(PdpRubricItem, PdpRubricItem.id == PdpRating.rubric_item_id)
                              .where(PdpRating.player_id == p.id).order_by(PdpRating.rated_on)):
        pdp[(item.group_name, item.skill_name)] = r.rating                       # later dates overwrite: the latest rating wins
    scr = db.scalar(select(Screening).where(Screening.player_id == p.id).order_by(Screening.screening_date.desc()).limit(1))
    tpl = {t.id: t for t in db.scalars(select(SkillTemplate).where(SkillTemplate.player_role == p.role))}
    role_skills = [{"group": tpl[tid].group_name, "skill": tpl[tid].skill_name, "status": a.status.value, "kind": tpl[tid].kind.value,
                    "since": a.period_start.isoformat()}
                   for tid, a in latest_role_skills(db, p).items() if tid in tpl]
    return {"window": window, "cohort_values": cohort, "prev_cat": prev_cat, "heights": heights, "pdp": pdp,
            "needs": {(n.category, n.item): n.level for n in scr.needs} if scr else None,
            "screening": {"start_age": scr.start_age, "this_year_objective": scr.this_year_objective} if scr else None,
            "role_skills": role_skills}


def _plan_json(plan: dict, summary: dict, season: Season) -> dict:
    return {**plan, "weeks": [{**w, "start": w["start"].isoformat()} for w in plan["weeks"]], "summary": summary, "season": {"id": season.id, "name": season.name}}


# The individual-plan endpoints (plan in use, edits, versions, Excel, session logs) are in routers/plan_versions.py.


# ───────────── progress between windows ─────────────
def _windows_for(db: Session, squad_id: int, season_id: int) -> dict[str, tuple[dict, dict]]:
    """{window: (categorisation by player, sessions by player)} for every window that has results in the season."""
    out = {}
    for w in WINDOWS:
        entries, sessions = _cohort_entries(db, squad_id, season_id, w)
        if sessions:
            out[w] = (cz.categorise(entries), sessions)
    return out


def _player_windows(player_id: int, wins: dict) -> list[dict]:
    return [{"window": w, "level": sessions[player_id].level, "finals": _finals(sessions[player_id]), "cat": cats.get(player_id)}
            for w, (cats, sessions) in wins.items() if player_id in sessions]


@router.get("/players/{player_id}/test-progress")
def player_progress(player_id: int, season_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Test-by-test change across baseline, mid-season and end of season, plus band movement and focus-area changes."""
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    season = _default_season(db, p.squad_id, season_id)
    out = build_progress(_player_windows(p.id, _windows_for(db, p.squad_id, season.id)))
    return {**out, "season": {"id": season.id, "name": season.name}}


@router.get("/squads/{squad_id}/seasons/{season_id}/test-progress")
def squad_progress(squad_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One line per active player: first to latest band, tests improved, focus areas resolved or new."""
    authorize_squad(db, user, squad_id, "testing.read")
    _season(db, squad_id, season_id)
    wins = _windows_for(db, squad_id, season_id)
    rows = []
    for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.full_name)):
        pw = _player_windows(p.id, wins)
        pr = build_progress(pw)
        mv = pr["band_movement"]
        rows.append({"player_id": p.id, "player": p.full_name, "windows_tested": [w["window"] for w in pw],
                     "band_text": mv["text"] if mv else None, "band_delta": mv["delta"] if mv else None,
                     "overall_delta": mv["overall_delta"] if mv else None, "tests_compared": pr["tests_compared"],
                     "tests_improved": pr["tests_improved"], "focus_resolved": pr["focus_resolved"], "focus_new": pr["focus_new"]})
    return {"windows_with_results": [w for w in wins], "players": rows}
