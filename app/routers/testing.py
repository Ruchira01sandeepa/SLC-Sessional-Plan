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
from ..test_battery import (AREAS, BY_KEY, LEVEL_LABEL, LEVELS, SIT_REACH, SKINFOLD_SITES, SKINFOLD_LABEL, TRIALS, WINDOW_LABEL, WINDOWS,
                            best_of, display, parse_skinfold, parse_value, skinfold_final, skinfold_sum, tests_for)
from ..age_norms import plausible
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
    age_group = db.scalar(select(Squad.age_group).where(Squad.id == squad_id))
    gender = dict(db.execute(select(Player.id, Player.gender).where(Player.squad_id == squad_id)).all())
    return [{"player_id": s.player_id, "level": s.level, "finals": _finals(s), "age_group": age_group,
             "gender": gender[s.player_id].value if gender.get(s.player_id) is not None else None}
            for s in sessions], {s.player_id: s for s in sessions}


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
            "test_version": s.test_version, "surface": s.surface, "timing_method": s.timing_method, "notes": s.notes, "results": res,
            "raw": {r.test_key: [r.trial_1, r.trial_2, r.trial_3] for r in s.results}, "extras": _extras(s)}


def _extras(s: TestSession | None) -> dict:
    """Sit and reach and the 8 skinfolds of one session (recorded and shown, not ranked)."""
    by = {r.test_key: r for r in s.results} if s else {}
    sr = by.get(SIT_REACH.key)
    sites, finals = [], {}
    for key, label in SKINFOLD_SITES:
        r = by.get(key)
        trials = [r.trial_1, r.trial_2, r.trial_3] if r else [None] * 3
        final = r.final_value if r else None
        finals[key] = final
        sites.append({"key": key, "label": label, "trials": trials, "final": final,
                      "third_needed": skinfold_final(trials)[1] if r and trials[2] is None else False, "note": r.setup if r else None})
    return {"sit_reach": {"trials": [sr.trial_1, sr.trial_2, sr.trial_3], "final": sr.final_value, "note": sr.setup} if sr else None,
            "skinfolds": sites, "skinfold_sum": skinfold_sum(finals), "third_needed": sum(1 for x in sites if x["third_needed"]),
            "copied": sorted({x["note"] for x in sites if x["note"]})}


def _test_goal(a: dict, t: dict, cohort: dict | None, window: str, age_group: str | None, gender: str) -> dict | None:
    """The result this player should aim for at the next test window (player_profile.physical_goal: about 15 rank points
    higher in the group, at least the age group's expected value, never more than 8% in one window)."""
    i = WINDOWS.index(window)
    nxt = WINDOW_LABEL[WINDOWS[i + 1]] if i + 1 < len(WINDOWS) else "next season's baseline"
    # an unranked area (group too small) still gets a goal, from the age reference
    g = physical_goal({**a, "percentile": a.get("percentile") or 0}, t["key"], (cohort or {}).get(t["key"]), nxt, age_group, gender)
    if not g:
        return None
    pct = t.get("percentile")
    age = t.get("age") or {}
    keep = (pct is not None and pct >= 75) or age.get("band") == "strong"
    kind = "keep" if keep else "focus" if pct is not None and pct < 50 else "improve"
    why = {"keep": "Already strong: keep it, a small step on is enough.",
           "focus": "Focus test: below the middle of the group. The goal moves it towards the middle in one window.",
           "improve": "Middle of the group: a steady step towards the top quarter."}[kind]
    if age.get("expected") is not None:
        why += f" Expected for {age['age_group']}: {age['expected']} {g['unit']}."
    return {"target": g["target"], "display": g["target_display"], "unit": g["unit"], "by": nxt, "kind": kind, "why": why,
            "change": g["target_display"] != g["current_display"]}


def _summary(player: Player, window: str, sess: TestSession | None, cat: dict | None, cohort: dict | None = None) -> dict:
    by_key = {r.test_key: r for r in sess.results} if sess else {}
    ag = player.squad.age_group if player.squad else None
    areas = []
    for a in (cat["areas"] if cat else []):
        tests = []
        for t in a["tests"]:
            r = by_key.get(t["key"])
            bt = BY_KEY[t["key"]]
            row = {**t, "trials_display": [(_trial_shown(bt, v) if v is not None else None) for v in
                                           ((r.trial_1, r.trial_2, r.trial_3) if r else (None,) * TRIALS)],
                   "age": age_band(t["key"], t.get("value"), ag, player.gender.value)}
            row["goal"] = _test_goal(a, row, cohort, window, ag, player.gender.value)
            tests.append(row)
        areas.append({**a, "tests": tests})
    return {"player_id": player.id, "player": player.full_name, "role": player.role.value, "window": window, "window_label": WINDOW_LABEL[window],
            "level": sess.level if sess else None, "level_label": LEVEL_LABEL[sess.level] if sess else "Not tested",
            "band": cat["band"] if cat else None, "band_label": cat["band_label"] if cat else None, "overall": cat["overall"] if cat else None,
            "note": cat["note"] if cat else "No test results for this window.", "areas": areas,
            "areas_counted": cat["areas_counted"] if cat else 0, "areas_total": cat["areas_total"] if cat else 0,
            "cohort_size": cat["cohort_size"] if cat else 0,
            "focus_areas": cat["focus_areas"] if cat else [], "benchmark": cat.get("benchmark") if cat else None,
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
                 "results": {(BY_KEY[k].label if k in BY_KEY else SKINFOLD_LABEL.get(k, SIT_REACH.label) + (" skinfold" if k in SKINFOLD_LABEL else "")):
                             (display(BY_KEY[k], v["final"]) if k in BY_KEY else f"{v['final']:g}") for k, v in r["results"].items()}}
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
                     "benchmark": ({k: cat["benchmark"][k] for k in ("total", "max", "percent", "band", "band_label")}
                                   if cat and cat.get("benchmark") else None),
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
    mine = next((e for e in entries if e["player_id"] == p.id), None)
    cohort: dict[str, list[float]] = {}
    for e in entries:
        if mine and e["level"] == mine["level"]:
            for k, v in e["finals"].items():
                if v is not None:
                    cohort.setdefault(k, []).append(v)
    return {"season": {"id": season.id, "name": season.name}, "window": window, "sessions": [_session_out(s) for s in sessions],
            "category": _summary(p, window, by_player.get(p.id), cat, cohort), "readiness": _readiness(db, p),
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
    results = squad_test_results(squad_id, season_id, d["window"], db, user) if d.get("window") else None
    return Response(build_physical_report(squad.name, d, results), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/test-summary.pdf")
def test_summary_pdf(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The Fitness page's overall test results summary for one window as a professional PDF document."""
    from ..test_summary_pdf import build_test_summary_pdf
    d = squad_test_results(squad_id, season_id, window, db, user)
    entries, _ = _cohort_entries(db, squad_id, season_id, d["window"])
    i = WINDOWS.index(d["window"])
    nxt = WINDOW_LABEL[WINDOWS[i + 1]] if i + 1 < len(WINDOWS) else "Next season's baseline"
    data = build_test_summary_pdf(d, cz.categorise(entries), band_names=cz.BAND_NAMES, next_label=nxt, prepared=today_lk())
    audit(db, user, "test_summary.exported", "season", season_id, d["window"])
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"test-results-summary-{d['squad']}-{d['season']['name']}-{d['window']}").strip("-") or "test-results-summary"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


# ───────────── periodized S&C seasonal plan (Zatsiorsky ch. 5 + youth ch. 10) ─────────────
from .. import sc_periodization as scp  # noqa: E402
from ..sc_periodization_excel import build_sc_season_workbook  # noqa: E402


def _sc_season(db: Session, user: User, squad_id: int, season_id: int, window: str | None, player: Player | None = None) -> tuple[dict, Squad]:
    """The squad plan, or with `player` the same periodization built on that player's own test ranks and role."""
    authorize_squad(db, user, squad_id, "testing.read")
    season = _season(db, squad_id, season_id)
    squad = db.get(Squad, squad_id)
    wins = _windows_for(db, squad_id, season_id)
    window = _window(window) if window else next((w for w in reversed(WINDOWS) if w in wins), "baseline")
    cats = wins[window][0] if window in wins else {}
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active)))
    areas: dict[str, list[float]] = {}
    for c in cats.values():
        for a in c["areas"]:
            if a["percentile"] is not None:
                areas.setdefault(a["area"], []).append(a["percentile"])
    squad_areas = [{"area": a, "priority": sum(1 for v in vs if v < 50), "median": sorted(vs)[len(vs) // 2]} for a, vs in areas.items()]
    if player is not None:
        own = cats.get(player.id)
        squad_areas = ([{"area": a["area"], "priority": 1 if a["percentile"] < 50 else 0, "median": a["percentile"]}
                        for a in own["areas"] if a["percentile"] is not None] if own else squad_areas)
        players = [player]
    role_groups: list[str] = []
    for p in players:
        for g in groups_for(p.role.value, _bowling(p)):
            if g not in role_groups:
                role_groups.append(g)
    phases, _ = _phases_for(season)
    today = today_lk()
    matches = [_local_date(e.start_at) for e in db.scalars(select(CalendarEvent).where(
        CalendarEvent.squad_id == squad_id, CalendarEvent.event_type == EventType.match,
        CalendarEvent.start_at >= _utc_naive(min(today, season.start_date), False), CalendarEvent.start_at < _utc_naive(season.end_date, True)))]
    lead = today if season.start_date > today and (season.start_date - today).days <= 42 else None
    plan = scp.build_macrocycle(season={"name": season.name, "start_date": season.start_date, "end_date": season.end_date},
                                phases=phases, squad_areas=squad_areas, role_groups=role_groups or ["fielding"], today=today,
                                matches=matches, lead_in_from=lead)
    plan["window"] = window
    plan["based_on"] = (f"{len(cats)} tested players ({WINDOW_LABEL[window]})" if cats else
                        "no test results yet: targets use a default order until the squad is tested")
    if player is not None:
        own = cats.get(player.id)
        plan["player"] = {"id": player.id, "name": player.full_name, "role": player.role.value, "squad_no": player.squad_no,
                          "ranks": {a["label"]: a["percentile"] for a in own["areas"]} if own else {}}
        plan["based_on"] = (f"{player.full_name}'s own {WINDOW_LABEL[window]} test ranks (weakest areas first)" if own else
                            f"{player.full_name} has no test results in this window: the squad's needs are used until they are tested")
    return plan, squad


@router.get("/squads/{squad_id}/seasons/{season_id}/sc-season-plan")
def sc_season_plan(squad_id: int, season_id: int, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The squad's periodized S&C plan for the season: macrocycle -> mesocycles -> microcycles, built on Zatsiorsky."""
    return _sc_season(db, user, squad_id, season_id, window)[0]


@router.get("/squads/{squad_id}/seasons/{season_id}/sc-season-plan.xlsx")
def sc_season_plan_xlsx(squad_id: int, season_id: int, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan, squad = _sc_season(db, user, squad_id, season_id, window)
    audit(db, user, "sc_season_plan.exported", "season", season_id)
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"SC-season-plan-{squad.name}-{plan['season']['name']}").strip("-") or "SC-season-plan"
    return Response(build_sc_season_workbook(squad.name, plan), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})



def _player_in_squad(db: Session, squad_id: int, player_id: int) -> Player:
    p = db.get(Player, player_id)
    if p is None or p.squad_id != squad_id:
        raise HTTPException(404, "Player not found in this squad")
    return p


def _file_name(*parts: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", "-".join(parts)).strip("-") or "plan"


@router.get("/squads/{squad_id}/seasons/{season_id}/sc-season-plan/players/{player_id}.xlsx")
def sc_season_plan_player_xlsx(squad_id: int, season_id: int, player_id: int, window: str | None = None,
                               db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One player's periodized S&C seasonal plan (their own targets, their role's exercises)."""
    authorize_squad(db, user, squad_id, "testing.read")
    p = _player_in_squad(db, squad_id, player_id)
    plan, squad = _sc_season(db, user, squad_id, season_id, window, p)
    audit(db, user, "sc_season_plan.exported", "player", p.id)
    db.commit()
    name = _file_name("SC-season-plan", p.full_name, plan["season"]["name"])
    return Response(build_sc_season_workbook(f"{p.full_name} ({squad.name})", plan), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/squads/{squad_id}/seasons/{season_id}/sc-season-plans.zip")
def sc_season_plans_zip(squad_id: int, season_id: int, window: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every plan in one download: the squad plan plus one workbook per active player."""
    import io
    import zipfile
    plan, squad = _sc_season(db, user, squad_id, season_id, window)
    buf = io.BytesIO()
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active).order_by(Player.squad_no, Player.full_name)))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"00-{_file_name('Squad', squad.name, plan['season']['name'])}.xlsx", build_sc_season_workbook(squad.name, plan))
        for i, p in enumerate(players, 1):
            pp, _ = _sc_season(db, user, squad_id, season_id, window, p)
            num = f"{p.squad_no:02d}" if p.squad_no is not None else f"x{i:02d}"
            z.writestr(f"{num}-{_file_name(p.full_name)}.xlsx", build_sc_season_workbook(f"{p.full_name} ({squad.name})", pp))
    audit(db, user, "sc_season_plans.exported", "season", season_id, f"{len(players)} players")
    db.commit()
    name = _file_name("SC-season-plans", squad.name, plan["season"]["name"])
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


# ───────────── enter results by hand (one player, one window): SOP tests, sit and reach, skinfolds ─────────────
class TestEntryIn(BaseModel):
    level: str | None = None
    test_date: date | None = None
    height_cm: float | None = Field(default=None, ge=120, le=200)
    weight_kg: float | None = Field(default=None, ge=25, le=120)
    results: dict[str, list[str | float | None]] = Field(default_factory=dict)       # test key -> up to 3 trials (blank = not done)


@router.put("/players/{player_id}/tests/{season_id}/{window}")
def enter_tests(player_id: int, season_id: int, window: str, body: TestEntryIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Save one player's trials typed in the Fitness results form. Same rules as the Excel import: three trials, the best valid one
    counts (skinfolds: mean of two within 5%, else median of three); a blank trial stays blank; nothing is estimated."""
    p = authorize_player(db, user, db.get(Player, player_id), "testing.write")
    _season(db, p.squad_id, season_id)
    window = _window(window)
    sess = db.scalar(select(TestSession).where(TestSession.player_id == p.id, TestSession.season_id == season_id, TestSession.window == FitnessPhase(window)))
    level = body.level or (sess.level if sess else "super_provincial")
    if level not in LEVELS:
        raise HTTPException(422, f"level must be one of {', '.join(LEVELS)}")
    allowed = {t.key: t for t in tests_for(level)}
    ag = p.squad.age_group if p.squad else None
    errors, parsed = [], {}
    for key, raw in body.results.items():
        if len(raw) > 3:
            errors.append(f"{key}: at most 3 trials")
            continue
        if key not in allowed and key != SIT_REACH.key and key not in SKINFOLD_LABEL:
            errors.append(f"{BY_KEY[key].label if key in BY_KEY else key} is not a {LEVEL_LABEL[level]} test")
            continue
        test = allowed.get(key, SIT_REACH)
        trials = []
        for v in list(raw) + [None] * (3 - len(raw)):
            if v is None or (isinstance(v, str) and not v.strip()):
                trials.append(None)
                continue
            try:
                trials.append(parse_skinfold(v) if key in SKINFOLD_LABEL else parse_value(test, v, plausible(key, ag) if key in allowed else None))
            except ValueError as e:
                errors.append(f"{SKINFOLD_LABEL.get(key, test.label)}: {e}")
                trials.append(None)
        parsed[key] = (trials, skinfold_final(trials)[0] if key in SKINFOLD_LABEL else best_of(test, trials))
    if errors:
        raise HTTPException(422, "; ".join(errors))
    if sess is None:
        sess = TestSession(player_id=p.id, season_id=season_id, window=FitnessPhase(window), level=level, cleared=True, tested_by=user.id)
        db.add(sess)
    sess.level = level
    for k in ("test_date", "height_cm", "weight_kg"):
        if k in body.model_fields_set:
            setattr(sess, k, getattr(body, k))
    for r in list(sess.results):                       # a level change drops the other level's tests
        if r.test_key in BY_KEY and r.test_key not in allowed:
            sess.results.remove(r)
    by = {r.test_key: r for r in sess.results}
    for key, (trials, final) in parsed.items():
        r = by.get(key)
        if final is None:
            if r is not None:
                sess.results.remove(r)
            continue
        if r is None:
            r = TestResult(test_key=key)
            sess.results.append(r)
        r.trial_1, r.trial_2, r.trial_3, r.final_value = trials[0], trials[1], trials[2], final
        if key not in BY_KEY:
            r.setup = None                             # measured now: no longer copied from another player
    db.flush()
    if role_allows(user, "workload.write") and any(k in allowed for k in parsed):
        log_test_day(db, user, p, sess)
    audit(db, user, "test_results.entered", "player", p.id, f"window {window}, {len(parsed)} test(s)")
    db.commit()
    db.refresh(sess)
    return _session_out(sess)


@router.get("/squads/{squad_id}/seasons/{season_id}/body-tests")
def body_tests(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The squad's skinfold record (8 sites and the sum) and sit and reach for one window, in squad-number order."""
    authorize_squad(db, user, squad_id, "testing.read")
    _season(db, squad_id, season_id)
    window = _window(window)
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active)
                              .order_by(Player.standby, Player.squad_no.is_(None), Player.squad_no, Player.full_name)))
    sess = {s.player_id: s for s in db.scalars(select(TestSession).where(
        TestSession.season_id == season_id, TestSession.window == FitnessPhase(window), TestSession.player_id.in_([p.id for p in players] or [-1])))}
    rows = []
    for p in players:
        s = sess.get(p.id)
        rows.append({"player_id": p.id, "name": p.full_name, "squad_no": p.squad_no, "standby": p.standby,
                     "weight_kg": s.weight_kg if s else None, **_extras(s)})
    sums = [r["skinfold_sum"] for r in rows if r["skinfold_sum"] is not None]
    srs = [r["sit_reach"]["final"] for r in rows if r["sit_reach"]]
    return {"window": window, "window_label": WINDOW_LABEL[window], "sites": [{"key": k, "label": lab} for k, lab in SKINFOLD_SITES], "players": rows,
            "squad_mean_sum": round(sum(sums) / len(sums), 1) if sums else None,
            "squad_mean_sit_reach": round(sum(srs) / len(srs), 1) if srs else None}


@router.get("/squads/{squad_id}/seasons/{season_id}/test-results")
def squad_test_results(squad_id: int, season_id: int, window: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The Fitness page report for one window: every active player's results (level, date, height, weight, BMI, best trial of
    every SOP test, sit and reach, skinfolds), the age-group reference per test, each player's change since their previous
    test, and the squad averages of every test window on record (past tests)."""
    from ..age_norms import age_band, reference
    from ..test_progress import _change
    authorize_squad(db, user, squad_id, "testing.read")
    season = _season(db, squad_id, season_id)
    window = _window(window)
    squad = db.get(Squad, squad_id)
    ag = squad.age_group or "U15"
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active)
                              .order_by(Player.standby, Player.squad_no.is_(None), Player.squad_no, Player.full_name)))
    # every test window on record for this squad, in time order (season start, then baseline / mid / end)
    seasons = {x.id: x for x in db.scalars(select(Season).where(Season.squad_id == squad_id))}
    worder = {w: i for i, w in enumerate(WINDOWS)}
    all_sess = list(db.scalars(select(TestSession).where(TestSession.season_id.in_(list(seasons) or [-1]))))
    slot = lambda x: (seasons[x.season_id].start_date, x.season_id, worder[x.window.value])
    here = (season.start_date, season.id, worder[window])
    by_slot: dict[tuple, list[TestSession]] = {}
    for x in all_sess:
        by_slot.setdefault(slot(x), []).append(x)
    finals = lambda x: {r.test_key: r.final_value for r in x.results if r.final_value is not None and r.test_key in BY_KEY}

    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    history = []
    for k in sorted(by_slot):
        xs = by_slot[k]
        fs = [finals(x) for x in xs]
        sums = [_extras(x)["skinfold_sum"] for x in xs]
        means = {}
        for key, t in BY_KEY.items():
            m = _mean([f.get(key) for f in fs])
            if m is not None:
                means[key] = {"value": round(m, 2), "display": display(t, round(m) if t.kind != "decimal" else m)}
        x0 = xs[0]
        dates = sorted(x.test_date for x in xs if x.test_date)
        history.append({"season_id": x0.season_id, "season": seasons[x0.season_id].name, "window": x0.window.value,
                        "window_label": WINDOW_LABEL[x0.window.value], "date": dates[0].isoformat() if dates else None,
                        "tested": len(xs), "current": k == here, "means": means,
                        "height_cm": _mean([x.height_cm for x in xs]), "weight_kg": _mean([x.weight_kg for x in xs]),
                        "skinfold_sum": _mean(sums),
                        "sit_reach": _mean([e["sit_reach"]["final"] for e in map(_extras, xs) if e["sit_reach"]])})

    current = {x.player_id: x for x in by_slot.get(here, [])}
    earlier: dict[int, TestSession] = {}
    for k in sorted(by_slot):
        if k < here:
            for x in by_slot[k]:
                earlier[x.player_id] = x                                   # the latest earlier test wins
    rows = []
    for pl in players:
        x = current.get(pl.id)
        out = _session_out(x) if x else None
        ex = out["extras"] if out else _extras(None)
        vals = finals(x) if x else {}
        prev = earlier.get(pl.id)
        change = None
        if x and prev:
            pv = finals(prev)
            change = {"label": f"{WINDOW_LABEL[prev.window.value]}, {seasons[prev.season_id].name}",
                      "tests": {k: {**_change(BY_KEY[k], pv[k], v), "from": display(BY_KEY[k], pv[k])} for k, v in vals.items() if k in pv}}
        rows.append({"player_id": pl.id, "name": pl.full_name, "role": pl.role.value, "squad_no": pl.squad_no, "standby": pl.standby,
                     "level": x.level if x else None, "level_label": LEVEL_LABEL[x.level] if x else None,
                     "test_date": out["test_date"] if out else None, "height_cm": x.height_cm if x else None, "weight_kg": x.weight_kg if x else None,
                     "bmi": round(x.weight_kg / (x.height_cm / 100) ** 2, 1) if x and x.weight_kg and x.height_cm else None,
                     "results": {k: v["final"] for k, v in out["results"].items()} if out else {},
                     "trials": {k: v["trials"] for k, v in out["results"].items()} if out else {},
                     "values": vals, "age": {k: (age_band(k, v, ag) or {}).get("band") for k, v in vals.items()}, "change": change,
                     "sit_reach": ex["sit_reach"]["final"] if ex["sit_reach"] else None, "skinfold_sum": ex["skinfold_sum"],
                     "skinfolds": {sf["key"]: sf["final"] for sf in ex["skinfolds"]}, "third_needed": ex["third_needed"], "copied": ex["copied"]})

    def _ref(t):
        r = reference(t.key, ag)
        return None if r is None else {"developing": r[0], "expected": r[1], "strong": r[2],
                                       "expected_display": display(t, r[1]), "strong_display": display(t, r[2])}
    return {"window": window, "window_label": WINDOW_LABEL[window], "squad": squad.name, "age_group": ag,
            "season": {"id": season.id, "name": season.name},
            "tests": [{"key": t.key, "label": t.label, "unit": t.unit, "kind": t.kind, "levels": list(t.levels),
                       "higher_is_better": t.higher_is_better, "reference": _ref(t)} for t in BY_KEY.values()],
            "sites": [{"key": k, "label": lab} for k, lab in SKINFOLD_SITES], "players": rows, "history": history}


def player_test_report(db: Session, squad_id: int, season_id: int, p: Player) -> dict:
    """One player's test results for the plan PDF: every window this season (trials, best, age reference, squad percentile,
    body measures, skinfolds, band and SLC points) and the change between windows."""
    from ..age_norms import age_band, reference
    ag = db.scalar(select(Squad.age_group).where(Squad.id == squad_id)) or "U15"
    wins = _windows_for(db, squad_id, season_id)
    out = []
    for w, (cats, sessions) in wins.items():
        s = sessions.get(p.id)
        if s is None:
            continue
        cat = cats.get(p.id) or {}
        pct = {t["key"]: t.get("percentile") for a in cat.get("areas", []) for t in a.get("tests", [])}
        tests = []
        for r in sorted(s.results, key=lambda r: list(BY_KEY).index(r.test_key) if r.test_key in BY_KEY else 99):
            t = BY_KEY.get(r.test_key)
            if t is None or r.final_value is None:
                continue
            ref = reference(t.key, ag)
            band = age_band(t.key, r.final_value, ag)
            tests.append({"key": t.key, "label": t.label, "unit": t.unit,
                          "trials": [_trial_shown(t, v) for v in (r.trial_1, r.trial_2, r.trial_3)], "best": display(t, r.final_value),
                          "expected": display(t, ref[1]) if ref else None, "age": band["band"] if band else None,
                          "age_label": band["label"] if band else None, "percentile": pct.get(t.key)})
        ex = _extras(s)
        bm = cat.get("benchmark")
        out.append({"window": w, "window_label": WINDOW_LABEL[w], "level_label": LEVEL_LABEL[s.level],
                    "test_date": s.test_date, "height_cm": s.height_cm, "weight_kg": s.weight_kg,
                    "bmi": round(s.weight_kg / (s.height_cm / 100) ** 2, 1) if s.weight_kg and s.height_cm else None,
                    "band": cat.get("band"), "band_label": cat.get("band_label"), "overall": cat.get("overall"),
                    "benchmark": {k: bm[k] for k in ("total", "max", "band_label")} if bm else None,
                    "focus": [f["label"] for f in cat.get("focus_areas", [])], "tests": tests,
                    "sit_reach": ex["sit_reach"]["final"] if ex["sit_reach"] else None,
                    "sit_reach_trials": ex["sit_reach"]["trials"] if ex["sit_reach"] else [None] * 3,
                    "sit_reach_note": ex["sit_reach"]["note"] if ex["sit_reach"] else None,
                    "skinfolds": [{"label": x["label"], "final": x["final"]} for x in ex["skinfolds"]],
                    "skinfold_sum": ex["skinfold_sum"], "copied": ex["copied"]})
    return {"age_group": ag, "windows": out, "progress": build_progress(_player_windows(p.id, wins)) if len(out) > 1 else None,
            "next": _next_targets(p, ag, wins, out[-1]) if out else None}


SR_STEP = 5.0            # sit and reach: aim about 5 cm further in one test window (short of the toes: towards / to the toes)


def sit_reach_target(cm: float | None) -> dict | None:
    """Short of the toes: 5 cm further, at most to the toes. Reaching the toes: +2 cm. 10 cm or more past the toes: keep it."""
    if cm is None:
        return None
    if cm < 0:
        target, kind, why = min(0.0, cm + SR_STEP), "focus", "Short of the toes: daily hamstring and lower-back work; aim for the toes."
    elif cm < 10:
        target, kind, why = cm + 2.0, "improve", "Reaches the toes: a small step further."
    else:
        target, kind, why = cm, "keep", "Already very flexible: keep it."
    return {"key": "sit_reach", "label": "Sit and reach", "unit": "cm from toes", "now": f"{cm:+.1f}", "target": f"{target:+.1f}",
            "kind": kind, "why": why}


def _next_targets(p: Player, ag: str, wins: dict, last: dict) -> dict:
    """The next test window and a target for every test of the latest one (physical_goal: about 15 rank points higher in the
    same-level group, at least the age group's expected value, never more than 8% in one window), plus sit and reach."""
    w = last["window"]
    i = WINDOWS.index(w)
    nxt = WINDOW_LABEL[WINDOWS[i + 1]] if i + 1 < len(WINDOWS) else "Next season's baseline"
    cats, sessions = wins[w]
    me = sessions[p.id]
    cohort: dict[str, list[float]] = {}
    for s in sessions.values():
        if s.level == me.level:
            for k, v in _finals(s).items():
                cohort.setdefault(k, []).append(v)
    gender = p.gender.value if getattr(p, "gender", None) is not None and hasattr(p.gender, "value") else "male"
    targets = []
    for t in last["tests"]:
        test = BY_KEY[t["key"]]
        value = _finals(me).get(t["key"])
        pct = t.get("percentile")
        area = {"area": test.area, "label": test.label, "percentile": pct or 0, "source": "test",
                "tests": [{"key": t["key"], "value": value, "percentile": pct}]}
        g = physical_goal(area, t["key"], cohort.get(t["key"]), nxt, ag, gender)
        if not g:
            continue
        keep = (pct is not None and pct >= 75) or t.get("age") == "strong"
        kind = "keep" if keep else "focus" if pct is not None and pct < 50 else "improve"
        why = {"keep": "Already strong: keep it, a small step on is enough.", "focus": "Focus test: extra work in the plan until the next test.",
               "improve": "A steady step forward."}[kind]
        if t.get("expected"):
            why += f" {ag} expected: {t['expected']} {test.unit}."
        targets.append({"key": t["key"], "label": test.label, "unit": test.unit, "now": g["current_display"], "target": g["target_display"],
                        "kind": kind, "why": why})
    sr = sit_reach_target(last.get("sit_reach"))
    if sr:
        targets.append(sr)
    return {"window_label": nxt, "after": last.get("test_date"), "targets": targets}



def sit_reach_text(cm: float | None) -> str:
    """'+2.5 cm (past the toes)' / '-10.2 cm (short of the toes)'."""
    if cm is None:
        return "-"
    return f"{cm:+.1f} cm (" + ("past the toes" if cm > 0 else "short of the toes" if cm < 0 else "at the toes") + ")"


def body_measures(db: Session, player_id: int, season_id: int, window: str | None = None) -> list[tuple[str, str]]:
    """Recorded, not ranked: sit and reach, sum of 8 skinfolds, height, weight and BMI from the player's session for the window
    (the latest window with a session if none is given)."""
    q = select(TestSession).where(TestSession.player_id == player_id, TestSession.season_id == season_id)
    sessions = sorted(db.scalars(q), key=lambda x: WINDOWS.index(x.window.value))
    s = next((x for x in sessions if x.window.value == window), None) if window else (sessions[-1] if sessions else None)
    if s is None:
        return []
    ex = _extras(s)
    sr = ex["sit_reach"]
    out = [("Sit and reach", sit_reach_text(sr["final"]) + (f" - {sr['note']}" if sr and sr.get("note") else "") if sr else "-"),
           ("Sum of 8 skinfolds", f"{ex['skinfold_sum']:.1f} mm" if ex["skinfold_sum"] is not None else "-"),
           ("Height", f"{s.height_cm:.1f} cm" if s.height_cm else "-"), ("Weight", f"{s.weight_kg:.1f} kg" if s.weight_kg else "-"),
           ("BMI", f"{s.weight_kg / (s.height_cm / 100) ** 2:.1f}" if s.weight_kg and s.height_cm else "-")]
    return out
