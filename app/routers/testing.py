"""SLC U15 SOP physical tests: Excel template, import, results on the player profile, categories and the individual plan.

Admin / S&C download a template pre-filled with the squad's players, fill it, and upload it. The upload is previewed first
(nothing is saved) and then confirmed. Results are confidential: players do not see them."""
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field

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
                      TestResult, TestSession, User, WorkloadLog, EventType, MaturityStatus, Squad, ScGroupAssignment, WellnessLog)
from .development import latest_role_skills
from ..permissions import authorize_player, authorize_squad, role_allows
from ..test_workload import bowling_advice, day_load, training_targets
from ..player_profile import physical_goal
from ..age_groups import profile as age_profile
from ..workload_rules import effective_limits
from ..workload_service import sync_alerts
from ..test_battery import AREAS, BY_KEY, LEVEL_LABEL, TRIALS, WINDOW_LABEL, WINDOWS, display
from ..physical_report_excel import build_physical_report
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
    saved_sessions = []
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
        saved_sessions.append(s)
    test_day = {}
    if role_allows(user, "workload.write"):                       # the test day counts in each player's workload
        db.flush()
        for s in saved_sessions:
            st = log_test_day(db, user, db.get(Player, s.player_id), s)
            test_day[st] = test_day.get(st, 0) + 1
    audit(db, user, "test_results.imported", "squad", squad_id, f"{len(parsed['rows'])} rows, {batch.rows_rejected} rejected, window {window}")
    db.commit()
    out.update(saved=True, batch_id=batch.id, test_day_load=test_day)
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



# ───────────── workload from the testing record (test-day load, training loads, fast-bowler workload) ─────────────
TEST_DAY_MARK = "test_battery"            # marks the workload log the system writes for a test day (never a coach's own log)


def _results(sess: TestSession) -> dict:
    return {r.test_key: {"trials": [r.trial_1, r.trial_2, r.trial_3], "final": r.final_value} for r in sess.results if r.final_value is not None}


def _test_day_log(db: Session, p: Player, sess: TestSession) -> WorkloadLog | None:
    return db.scalar(select(WorkloadLog).where(WorkloadLog.player_id == p.id, WorkloadLog.log_date == sess.test_date,
                                               WorkloadLog.session_type == EventType.fitness_test).order_by(WorkloadLog.id).limit(1))


def log_test_day(db: Session, user: User | None, p: Player, sess: TestSession) -> str:
    """Write (or refresh) the test-day load in the player's workload log. Returns logged / updated / coach_logged / skipped."""
    if sess.test_date is None or sess.test_date > today_lk():
        return "skipped"
    load = day_load(_results(sess))
    if not load["minutes"]:
        return "skipped"
    row = _test_day_log(db, p, sess)
    if row is not None and row.match_participation != TEST_DAY_MARK:
        return "coach_logged"                                      # a coach already logged this test day: keep their numbers
    status = "updated" if row else "logged"
    if row is None:
        row = WorkloadLog(player_id=p.id, log_date=sess.test_date, session_type=EventType.fitness_test, attended=True,
                          recorded_by=user.id if user else None, match_participation=TEST_DAY_MARK)
        db.add(row)
    row.duration_min, row.rpe, row.session_intensity = load["minutes"], load["rpe"], 8
    db.flush()
    sync_alerts(db, p)
    return status


def _test_workload_rows(db: Session, squad_id: int, season_id: int, window: str) -> list[dict]:
    squad = db.get(Squad, squad_id)
    entries, sessions = _cohort_entries(db, squad_id, season_id, window)
    cats = cz.categorise(entries)
    players = [p for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.squad_no, Player.full_name))
               if p.id in sessions]
    evals = evaluate_players(db, players, today_lk())
    defaults = dict(age_profile(squad.age_group).fast_limits)
    rows = []
    for p in players:
        sess = sessions[p.id]
        res = _results(sess)
        cat = cats.get(p.id)
        areas = {a["area"]: a["percentile"] for a in (cat or {}).get("areas", [])}
        existing = _test_day_log(db, p, sess) if sess.test_date else None
        logged = None if existing is None else ("system" if existing.match_participation == TEST_DAY_MARK else "coach")
        rows.append({"player_id": p.id, "player": p.full_name, "role": p.role.value, "squad_no": p.squad_no, "test_date": sess.test_date,
                     "day_load": day_load(res), "logged": logged,
                     "logged_load": (existing.rpe or 0) * (existing.duration_min or 0) if existing else None,
                     "targets": training_targets(res, in_spurt=p.maturity_status == MaturityStatus.circa_phv),
                     "bowling": bowling_advice(p.role.value, _bowling(p), effective_limits(p.role.value, p.workload_limits, squad.age_group),
                                               defaults, areas, evals[p.id][1].get("bowling")),
                     "load_7d": evals[p.id][1].get("acute_load_7d"), "acwr": evals[p.id][1].get("acwr")})
    return rows


@router.get("/squads/{squad_id}/seasons/{season_id}/test-workload")
def test_workload(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """For every player tested in the window: the test-day load, training loads from the results and (pace bowlers) bowling workload."""
    authorize_squad(db, user, squad_id, "testing.read")
    _season(db, squad_id, season_id)
    window = _window(window)
    rows = _test_workload_rows(db, squad_id, season_id, window)
    return {"window": window, "window_label": WINDOW_LABEL[window], "players": rows,
            "notes": ["Test-day load = session RPE x minutes, the same units as the workload log. Minutes come from the player's own 2 km "
                      "and plank times and the number of trials done; RPE is a standard estimate for each maximal test.",
                      "Training loads are taken from each player's own results (pace from the 2 km time, sets from the push-up, "
                      "inverted-row and plank maximum). Lower volumes in the growth spurt.",
                      "Pace bowlers: a stricter limit is SUGGESTED when endurance or core is below the middle. It is not applied "
                      "automatically: set it under the player's bowling limits if the coach agrees.",
                      "Every number is a proposal for the coach."]}


@router.post("/squads/{squad_id}/seasons/{season_id}/test-workload/log")
def log_test_workload(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Add the test-day load of every tested player to their workload log (refreshes the system's own entries; never
    changes a test day a coach logged by hand)."""
    authorize_squad(db, user, squad_id, "testing.write")
    if not role_allows(user, "workload.write"):
        raise HTTPException(403, "You cannot write workload logs")
    _season(db, squad_id, season_id)
    window = _window(window)
    _, sessions = _cohort_entries(db, squad_id, season_id, window)
    counts: dict[str, int] = {}
    for pid, sess in sessions.items():
        st = log_test_day(db, user, db.get(Player, pid), sess)
        counts[st] = counts.get(st, 0) + 1
    audit(db, user, "test_workload.logged", "season", season_id, ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    db.commit()
    return {"window": window, **{k: counts.get(k, 0) for k in ("logged", "updated", "coach_logged", "skipped")}}


# ───────────── the squad's Physical (S&C) page: dashboard, S&C groups, re-test and progress, growth ─────────────
from .. import physical_hub as ph  # noqa: E402
from ..exercises import groups_for  # noqa: E402
from ..models import CalendarEvent  # noqa: E402
from .plans import _local_date, _phases_for, _utc_naive  # noqa: E402


@router.get("/squads/{squad_id}/seasons/{season_id}/physical")
def physical_page(squad_id: int, season_id: int, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "testing.read")
    season = _season(db, squad_id, season_id)
    wins = _windows_for(db, squad_id, season_id)
    window = _window(window) if window else next((w for w in reversed(WINDOWS) if w in wins), "baseline")
    cats = wins[window][0] if window in wins else {}
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.squad_no, Player.full_name)))
    plist = [{"id": p.id, "name": p.full_name, "role": p.role.value, "squad_no": p.squad_no, "maturity_status": p.maturity_status.value,
              "style_pace": p.role == PlayerRole.all_rounder and "fast" in (_bowling(p) or set())} for p in players]
    dash = ph.heatmap(plist, cats)

    phases, phases_source = _phases_for(season)
    today = today_lk()
    phase = ph.current_phase(phases, today)
    by_id = {p.id: p for p in players}
    overrides = {a.player_id: a.area for a in db.scalars(select(ScGroupAssignment).where(ScGroupAssignment.season_id == season_id))
                 if a.player_id in by_id}
    groups = ph.make_groups(dash["rows"], overrides=overrides)
    for g in groups:
        rg: list[str] = []
        for m in g["players"]:
            for x in groups_for(m["role"], _bowling(by_id[m["player_id"]])):
                if x not in rg:
                    rg.append(x)
        g["session"] = ph.group_session(g, phase, rg) if phase else None

    tests = [_local_date(e.start_at) for e in db.scalars(select(CalendarEvent).where(
        CalendarEvent.squad_id == squad_id, CalendarEvent.event_type == EventType.fitness_test,
        CalendarEvent.start_at >= _utc_naive(season.start_date - timedelta(days=30), False), CalendarEvent.start_at < _utc_naive(season.end_date + timedelta(days=30), True)))]
    retest = ph.retest_plan({"start_date": season.start_date, "end_date": season.end_date}, phases, list(wins), tests, today)
    per = {p.id: build_progress(_player_windows(p.id, wins)) for p in players if any(p.id in s for _, s in wins.values())}
    progress = ph.progress_rows(per, {p.id: p.full_name for p in players})

    measures: dict[int, list[dict]] = {p.id: [] for p in players}
    for s in db.scalars(select(TestSession).where(TestSession.player_id.in_([p.id for p in players] or [-1]))):
        if s.test_date and (s.height_cm or s.weight_kg):
            measures[s.player_id].append({"date": s.test_date, "height_cm": s.height_cm, "weight_kg": s.weight_kg})
    later = None
    order = list(WINDOWS)
    for w in order[order.index(window) + 1:]:
        if w in wins:
            later = w
            break
    cohort_vals: dict[str, list[float]] = {}
    for s_ in (wins[window][1].values() if window in wins else []):
        for k, v in _finals(s_).items():
            cohort_vals.setdefault(k, []).append(v)
    targets = []
    for r in dash["rows"]:
        lt = _finals(wins[later][1][r["player_id"]]) if later and r["player_id"] in wins[later][1] else None
        t = ph.test_targets(cats[r["player_id"]], cohort_vals, retest.get("label") or "next test", lt, db.get(Squad, squad_id).age_group, physical_goal)
        targets.append({"player_id": r["player_id"], "name": r["name"], "targets": t})
    growth = ph.growth_rows(plist, measures)
    return {"season": {"id": season.id, "name": season.name}, "window": window, "window_label": WINDOW_LABEL[window],
            "later_window": later, "targets": targets, "today": _today_board(db, squad_id, players, {g["player_id"]: g for g in growth}),
            "attendance": _attendance(db, players), "group_options": [{"key": a["area"], "label": a["label"]} for a in dash["areas"]] + [{"key": ph.GENERAL, "label": "All-round maintenance"}],
            "windows_with_results": list(wins), "phase": phase, "phase_label": ph.PHASE_LABEL.get(phase) if phase else None,
            "phases_source": phases_source, "dashboard": dash, "groups": groups, "retest": retest, "progress": progress,
            "growth": growth,
            "notes": ["Ranks compare each player with the same-level group in this window (100 = best, below 50 = priority, 70+ = strength). "
                      "They are not pass or fail marks.",
                      "S&C groups are formed from each player's weakest area; a player can be moved by the coach. Group doses are a conservative "
                      "range; each player's own S&C plan has their personal dose.",
                      "Growth rate needs two heights at least 3 months apart. Record height and mass at every test.",
                      "Every exercise and number is a proposal for the coach."]}


def _today_board(db: Session, squad_id: int, players: list[Player], growth_by: dict) -> dict:
    """What each player should do in S&C today: availability, alerts, latest wellness, matches today/tomorrow, recent bowling."""
    today = today_lk()
    ids = [p.id for p in players] or [-1]
    evals = evaluate_players(db, players, today)
    well: dict[int, list] = {}
    for w in db.scalars(select(WellnessLog).where(WellnessLog.player_id.in_(ids), WellnessLog.log_date >= today - timedelta(days=6),
                                                  WellnessLog.log_date <= today).order_by(WellnessLog.log_date)):
        well.setdefault(w.player_id, []).append(w)
    bowled = {pid for pid, in db.execute(select(WorkloadLog.player_id).where(
        WorkloadLog.player_id.in_(ids), WorkloadLog.log_date >= today - timedelta(days=1), WorkloadLog.log_date <= today, WorkloadLog.balls_bowled > 0))}
    matches = {_local_date(e.start_at) for e in db.scalars(select(CalendarEvent).where(
        CalendarEvent.squad_id == squad_id, CalendarEvent.event_type == EventType.match,
        CalendarEvent.start_at >= _utc_naive(today, False), CalendarEvent.start_at < _utc_naive(today + timedelta(days=1), True)))}
    rows = []
    for p in players:
        alerts, summ = evals[p.id]
        ws = well.get(p.id, [])
        recent = [w for w in ws if w.log_date >= today - timedelta(days=1)]
        latest = recent[-1] if recent else None
        sleeps = [w.sleep_hours for w in ws if w.sleep_hours is not None][-3:]
        info = {"availability": p.availability.value, "alerts_worst": summ.get("alerts_worst"),
                "alert_codes": sorted({a.message.split(".")[0] for a in alerts if a.severity == "warn"})[:2],
                "pain_recent": any(w.pain_flag for w in ws if w.log_date >= today - timedelta(days=2)),
                "soreness": latest.soreness if latest else None, "fatigue": latest.fatigue if latest else None,
                "sleep_avg": sum(sleeps) / len(sleeps) if len(sleeps) == 3 else None,
                "match_today": today in matches, "match_tomorrow": (today + timedelta(days=1)) in matches,
                "bowled_recent": p.id in bowled, "role": p.role.value, "in_spurt": growth_by.get(p.id, {}).get("in_spurt")}
        a = ph.today_action(info)
        rows.append({"player_id": p.id, "name": p.full_name, "role": p.role.value, **a,
                     "wellness": {"date": latest.log_date, "soreness": latest.soreness, "fatigue": latest.fatigue} if latest else None})
    rows.sort(key=lambda r: (ph.ACTION_ORDER.index(r["action"]), r["name"]))
    counts = {k: sum(1 for r in rows if r["action"] == k) for k in ph.ACTION_ORDER}
    return {"date": today, "match_today": today in matches, "match_tomorrow": (today + timedelta(days=1)) in matches,
            "counts": counts, "labels": ph.ACTIONS, "players": rows,
            "no_wellness": [r["name"] for r in rows if r["wellness"] is None]}


def _attendance(db: Session, players: list[Player]) -> dict:
    ids = [p.id for p in players] or [-1]
    today = today_lk()
    logs = [{"player_id": r.player_id, "log_date": r.log_date, "attended": r.attended, "group": r.match_participation[len(ph.SC_MARK):],
             "load": (r.rpe or 0) * (r.duration_min or 0) if r.attended else 0}
            for r in db.scalars(select(WorkloadLog).where(WorkloadLog.player_id.in_(ids), WorkloadLog.log_date >= today - timedelta(days=28),
                                                          WorkloadLog.match_participation.like(ph.SC_MARK + "%")))]
    return ph.attendance(logs, [{"id": p.id, "name": p.full_name} for p in players], today)


class GroupMoveIn(BaseModel):
    area: str | None = Field(default=None, max_length=30)          # None = back to the automatic group


@router.put("/squads/{squad_id}/seasons/{season_id}/sc-groups/{player_id}")
def move_to_group(squad_id: int, season_id: int, player_id: int, body: GroupMoveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A coach moves a player to another S&C group (or back to the automatic one with area = null)."""
    authorize_squad(db, user, squad_id, "workload.limits")
    _season(db, squad_id, season_id)
    p = db.get(Player, player_id)
    if p is None or p.squad_id != squad_id:
        raise HTTPException(404, "Player not found in this squad")
    if body.area is not None and body.area != ph.GENERAL and body.area not in AREAS:
        raise HTTPException(422, f"Unknown group '{body.area}'")
    row = db.scalar(select(ScGroupAssignment).where(ScGroupAssignment.season_id == season_id, ScGroupAssignment.player_id == player_id))
    if body.area is None:
        if row:
            db.delete(row)
    else:
        if row is None:
            row = ScGroupAssignment(season_id=season_id, player_id=player_id, area=body.area)
            db.add(row)
        row.area, row.set_by = body.area, user.id
    audit(db, user, "sc_group.moved", "player", player_id, body.area or "automatic")
    db.commit()
    return {"player_id": player_id, "area": body.area}


class ScAttend(BaseModel):
    player_id: int
    attended: bool = True
    rpe: int | None = Field(default=None, ge=1, le=10)


class ScSessionIn(BaseModel):
    log_date: date
    group: str = Field(min_length=1, max_length=26)
    minutes: int = Field(ge=10, le=180)
    rpe: int = Field(ge=1, le=10)
    players: list[ScAttend] = Field(min_length=1, max_length=60)


@router.post("/squads/{squad_id}/sc-sessions", status_code=201)
def log_group_session(squad_id: int, body: ScSessionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Log one group S&C session for many players at once: present players get the session in their workload (minutes x RPE),
    absent ones an 'not attended' entry. Logging the same group and date again replaces it."""
    authorize_squad(db, user, squad_id, "workload.limits")
    if body.log_date > today_lk():
        raise HTTPException(422, "A session cannot be logged in the future")
    mark = ph.SC_MARK + body.group
    ids = [x.player_id for x in body.players]
    players = {p.id: p for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.id.in_(ids)))}
    missing = [i for i in ids if i not in players]
    if missing:
        raise HTTPException(422, "Some players are not in this squad")
    for old in db.scalars(select(WorkloadLog).where(WorkloadLog.player_id.in_(ids), WorkloadLog.log_date == body.log_date,
                                                    WorkloadLog.match_participation == mark)):
        db.delete(old)
    db.flush()
    present = 0
    for x in body.players:
        if x.attended:
            present += 1
            db.add(WorkloadLog(player_id=x.player_id, log_date=body.log_date, session_type=EventType.training, attended=True,
                               duration_min=body.minutes, rpe=x.rpe or body.rpe, session_intensity=body.rpe, recorded_by=user.id, match_participation=mark))
        else:
            db.add(WorkloadLog(player_id=x.player_id, log_date=body.log_date, session_type=EventType.training, attended=False,
                               recorded_by=user.id, match_participation=mark))
    db.flush()
    for pid in ids:
        sync_alerts(db, players[pid])
    audit(db, user, "sc_session.logged", "squad", squad_id, f"{body.group} {body.log_date}: {present} of {len(ids)} present")
    db.commit()
    return {"present": present, "absent": len(ids) - present, "group": body.group, "log_date": body.log_date}


@router.get("/squads/{squad_id}/seasons/{season_id}/physical-report.xlsx")
def physical_report(squad_id: int, season_id: int, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The squad's Physical page as one workbook: heat map, today, groups and sessions, targets, progress, growth."""
    d = physical_page(squad_id, season_id, window, db, user)
    squad = db.get(Squad, squad_id)
    audit(db, user, "physical_report.exported", "season", season_id)
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"physical-report-{squad.name}-{d['season']['name']}-{d['window']}").strip("-") or "physical-report"
    return Response(build_physical_report(squad.name, d), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
