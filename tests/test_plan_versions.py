"""Coach-edited, saved plan versions and progress tracking with automatic dose progression."""
import io
from datetime import date, timedelta

import openpyxl
import pytest

from app.models import WorkloadLog
from app.plan_edits import EditError, apply_edits
from app.plan_progress import exercise_progress, plan_progress
from app.workload_service import today_lk
from .test_personal_plan import plan as make_plan
from .test_testing import add_players, fill, get_template, good_row, make_season, upload

TODAY = date(2027, 3, 1)


def _area(p, phase="pre_season", area=None):
    """The named area, or the first area of the phase that has exercises and alternatives to swap in."""
    areas = next(x for x in p["phases"] if x["phase"] == phase)["areas"]
    if area:
        return next(a for a in areas if a["area"] == area)
    return next(a for a in areas if len(a["exercises"]) >= 2 and a["alternatives"])


# ───────────── edits (pure) ─────────────
def test_swap_remove_add_dose_goal_and_note():
    p = make_plan(pcts={"plank": 10.0}, extra={"window": "baseline", "cohort_values": {"plank": [30, 40, 50, 60, 70, 80]}})
    phase, a = next((ph["phase"], a) for ph in p["phases"] for a in ph["areas"] if len(a["exercises"]) >= 2 and a["alternatives"])
    ar = a["area"]
    first, alt = a["exercises"][0]["name"], a["alternatives"][0]["name"]
    out = apply_edits(p, [{"type": "swap", "phase": phase, "area": ar, "index": 0, "exercise": alt}])
    b = _area(out, phase, ar)
    assert b["exercises"][0]["name"] == alt and b["exercises"][0]["edited"] and b["alternatives"][0]["name"] == first
    assert _area(p, phase, ar)["exercises"][0]["name"] == first                        # the original is not changed
    out = apply_edits(out, [{"type": "remove", "phase": phase, "area": ar, "index": 0},
                            {"type": "add", "phase": phase, "area": ar, "exercise": first},
                            {"type": "dose", "phase": phase, "area": ar, "index": 0, "rep": "10-12", "set": "3"},
                            {"type": "goal", "index": 0, "target_display": "80.00", "by": "End of season test"},
                            {"type": "note", "text": "Prefers morning sessions"}])
    b = _area(out, phase, ar)
    assert b["exercises"][-1]["name"] == first and b["exercises"][-1]["edited"] == "added by the coach"
    assert b["exercises"][0]["rep"] == "10-12" and b["exercises"][0]["basis"] == "Set by the coach."
    assert out["goals"][0]["target_display"] == "80.00" and "80.00" in out["goals"][0]["label"] and out["goals"][0]["edited"]
    assert out["coach_note"] == "Prefers morning sessions"


def test_invalid_edits_are_rejected_with_a_clear_message():
    p = make_plan(pcts={"plank": 10.0})
    with pytest.raises(EditError, match="not an alternative"):
        apply_edits(p, [{"type": "swap", "phase": "pre_season", "area": "core", "index": 0, "exercise": "Box jump, low box"}])  # not core work
    with pytest.raises(EditError, match="no exercise number"):
        apply_edits(p, [{"type": "remove", "phase": "pre_season", "area": "core", "index": 99}])
    with pytest.raises(EditError, match="no phase"):
        apply_edits(p, [{"type": "dose", "phase": "winter", "area": "core", "index": 0, "rep": "5"}])
    ph, ar, i, ex = next((ph["phase"], a["area"], i, e) for ph in p["phases"] for a in ph["areas"] for i, e in enumerate(a["exercises"])
                         if (e.get("rep_start") or 0) >= 3)
    with pytest.raises(EditError, match="below the starting value"):
        apply_edits(p, [{"type": "dose", "phase": ph, "area": ar, "index": i, "rep_target": ex["rep_start"] - 1}])
    with pytest.raises(EditError, match="unknown type"):
        apply_edits(p, [{"type": "delete_everything"}])


# ───────────── progression (pure) ─────────────
EX = {"name": "Push-up", "rep_start": 8, "rep_target": 10, "sets_start": 2, "sets_target": 3}


def log(days_ago, reps=8, sets=2, ok=True, pain=False):
    return {"log_date": TODAY - timedelta(days=days_ago), "reps_done": reps, "sets_done": sets, "technique_ok": ok, "pain": pain}


def test_two_good_weeks_add_a_rep_then_a_set_at_the_target():
    r = exercise_progress(EX, [log(20), log(16)], TODAY, "ready")                     # one finished block, 2 good sessions
    assert (r["current_reps"], r["current_sets"], r["status"]) == (9, 2, "progressed")
    blocks = [log(62), log(58), log(48, 9), log(44, 9), log(34, 10), log(30, 10), log(20, 10, 3), log(16, 10, 3)]
    r = exercise_progress(EX, blocks, TODAY, "ready")
    assert (r["current_reps"], r["current_sets"]) == (10, 3) and r["status"] == "at_target"     # never above the targets
    assert [h["result"] for h in r["history"]][:3] == ["progressed", "progressed", "progressed"]


@pytest.mark.parametrize("logs,status,why", [
    ([log(20)], "held", "Only 1 session"),
    ([log(20), log(16, ok=False)], "held", "Technique"),
    ([log(20), log(16, reps=6)], "held", "prescribed reps"),
])
def test_hold_rules(logs, status, why):
    r = exercise_progress(EX, logs, TODAY, "ready")
    assert r["status"] == status and why in r["reason"] and (r["current_reps"], r["current_sets"]) == (8, 2)


def test_pain_steps_back_and_refers():
    r = exercise_progress(EX, [log(34), log(30), log(20), log(16, reps=9, pain=True)], TODAY, "ready")
    assert r["status"] == "stepped_back" and r["current_reps"] == 8 and "physiotherapist" in r["reason"]


def test_running_block_is_not_judged_and_readiness_holds():
    r = exercise_progress(EX, [log(5), log(2)], TODAY, "ready")
    assert r["status"] == "in_progress" and r["next_review"] == (TODAY + timedelta(days=9)).isoformat()
    r = exercise_progress(EX, [log(5)], TODAY, "caution")
    assert "Readiness is Caution" in r["reason"]


def test_plan_progress_covers_every_exercise_and_adherence():
    p = make_plan(pcts={"plank": 10.0})
    ex = _area(p, area="core")["exercises"][0]
    logs = [{**log(3), "phase": "pre_season", "area": "core", "exercise": ex["name"]}]
    pr = plan_progress(p, logs, TODAY, "ready")
    k = f"pre_season|core|{ex['name']}"
    assert pr["exercises"][k]["sessions"] == 1 and len(pr["adherence"]["weeks"]) == 4 and pr["logged_sessions"] == 1


# ───────────── API ─────────────
@pytest.fixture
def setup(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    return ids[0], sid


def test_preview_save_versions_and_fresh(client, world, setup):
    pid, sid = setup
    h = world["h"]["coach_a"]
    url = f"/players/{pid}/individual-plan"
    gen = client.get(f"{url}?season_id={sid}&window=baseline", headers=h).json()
    assert gen["saved"] is None and gen["latest_saved"] is None and "progress" in gen
    ph = gen["phases"][0]
    a = next(x for x in ph["areas"] if x["exercises"] and x["alternatives"])
    swap = {"type": "swap", "phase": ph["phase"], "area": a["area"], "index": 0, "exercise": a["alternatives"][0]["name"]}
    pv = client.post(f"{url}/preview", headers=h, json={"base": "fresh", "edits": [swap], "season_id": sid, "window": "baseline"})
    assert pv.status_code == 200 and next(x for x in pv.json()["phases"][0]["areas"] if x["area"] == a["area"])["exercises"][0]["name"] == swap["exercise"]
    assert client.get(f"{url}/versions?season_id={sid}", headers=h).json() == []                 # a preview saves nothing
    v1 = client.post(f"{url}/versions", headers=h, json={"base": "fresh", "edits": [swap], "note": "First version", "season_id": sid, "window": "baseline"})
    assert v1.status_code == 201 and v1.json()["saved"]["version"] == 1 and v1.json()["coach_note"] == "First version"
    cur = client.get(f"{url}?season_id={sid}", headers=h).json()
    assert cur["saved"]["version"] == 1
    assert next(x for x in cur["phases"][0]["areas"] if x["area"] == a["area"])["exercises"][0]["name"] == swap["exercise"]
    v2 = client.post(f"{url}/versions", headers=h, json={"base": "saved", "edits": [{"type": "note", "text": "Second"}], "season_id": sid})
    assert v2.json()["saved"]["version"] == 2 and v2.json()["saved"]["based_on"] == "version 1"
    assert next(x for x in v2.json()["phases"][0]["areas"] if x["area"] == a["area"])["exercises"][0]["name"] == swap["exercise"]   # edits carried over
    fresh = client.get(f"{url}?season_id={sid}&fresh=true", headers=h).json()
    assert fresh["saved"] is None and fresh["latest_saved"]["version"] == 2
    assert [v["version"] for v in client.get(f"{url}/versions?season_id={sid}", headers=h).json()] == [2, 1]
    assert client.get(f"{url}/versions/1?season_id={sid}", headers=h).json()["edit_list"] == [swap]
    bad = client.post(f"{url}/versions", headers=h, json={"base": "saved", "edits": [{"type": "swap", "phase": ph["phase"], "area": a["area"], "index": 0,
                                                                                      "exercise": "Something invented"}], "season_id": sid})
    assert bad.status_code == 422 and "not an alternative" in bad.json()["detail"]
    x = client.get(f"/players/{pid}/individual-plan.xlsx?season_id={sid}", headers=world["h"]["admin"])
    focus = openpyxl.load_workbook(io.BytesIO(x.content))["Focus plan"]
    assert swap["exercise"] in [c.value for row in focus.iter_rows() for c in row]               # the export is the saved version


def test_only_coaching_staff_edit_or_log(client, world, setup):
    pid, sid = setup
    body = {"base": "fresh", "edits": [], "season_id": sid}
    assert client.post(f"/players/{pid}/individual-plan/versions", headers=world["h"]["physio_a"], json=body).status_code == 403
    assert client.post(f"/players/{pid}/individual-plan/versions", headers=world["h"]["coach_b"], json=body).status_code == 404   # other squad
    assert client.post(f"/players/{pid}/plan-sessions", headers=world["h"]["physio_a"],
                       json={"items": [{"phase": "pre_season", "area": "core", "exercise": "Plank"}]}).status_code == 403


def test_logging_sessions_moves_the_dose(client, world, db, setup):
    pid, sid = setup
    h = world["h"]["coach_a"]
    plan = client.post(f"/players/{pid}/individual-plan/versions", headers=h, json={"base": "fresh", "edits": [], "season_id": sid}).json()
    ph, a, ex = next((ph, a, e) for ph in plan["phases"] for a in ph["areas"] for e in a["exercises"] if e.get("rep_start") and e["rep_target"] > e["rep_start"])
    item = {"phase": ph["phase"], "area": a["area"], "exercise": ex["name"], "sets_done": ex["sets_start"], "reps_done": ex["rep_start"]}
    today = today_lk()
    for d in (20, 16):
        r = client.post(f"/players/{pid}/plan-sessions", headers=h, json={"log_date": (today - timedelta(days=d)).isoformat(), "season_id": sid, "items": [item]})
        assert r.status_code == 201, r.text
    k = f"{ph['phase']}|{a['area']}|{ex['name']}"
    pr = r.json()["progress"]["exercises"][k]
    assert pr["status"] == "progressed" and pr["current_reps"] == ex["rep_start"] + 1 and pr["sessions"] == 2
    r = client.post(f"/players/{pid}/plan-sessions", headers=h, json={"minutes": 40, "rpe": 6, "season_id": sid, "items": [item]})
    assert r.status_code == 201 and db.query(WorkloadLog).filter_by(player_id=pid, duration_min=40, rpe=6).count() == 1   # counted in the workload
    assert client.post(f"/players/{pid}/plan-sessions", headers=h, json={"items": [{**item, "exercise": "Not in plan"}]}).status_code == 422
    assert client.post(f"/players/{pid}/plan-sessions", headers=h, json={"log_date": (today + timedelta(days=1)).isoformat(), "items": [item]}).status_code == 422
    rows = client.get(f"/players/{pid}/plan-sessions", headers=h).json()
    assert len(rows) == 3 and rows[0]["exercise"] == ex["name"]


def test_pain_steps_back_at_once_without_waiting_for_the_block():
    r = exercise_progress(EX, [log(34), log(30), log(2, reps=9, pain=True)], TODAY, "ready")       # +1 rep earned, then pain today
    assert r["status"] == "stepped_back" and r["current_reps"] == 8 and "now" in r["reason"]
    r = exercise_progress(EX, [log(1, pain=True)], TODAY, "ready")                                   # at the start already: stays at the start
    assert r["status"] == "stepped_back" and (r["current_reps"], r["current_sets"]) == (8, 2)
