"""Workload from the SLC physical testing record: test-day load, training loads from the results, fast-bowler workload."""
from datetime import date

import pytest
from sqlalchemy import select

import app.api.testing as testing_router
from app.core.models import EventType, Player, PlayerRole, WorkloadLog
from app.workload.test_workload import bowling_advice, day_load, training_targets
H = lambda w, who: w["h"][who]
from .test_testing import add_players, fill, get_template, good_row, make_season, upload

RES = {"run_2km": {"trials": [567, None, None], "final": 567}, "broad_jump": {"trials": [220, 215, 223], "final": 223},
       "sprint_20m": {"trials": [3.44, 3.24, 3.53], "final": 3.24}, "shuttle_5_10_5": {"trials": [6.23, 6.01, 5.82], "final": 5.82},
       "pushups": {"trials": [30, None, None], "final": 30}, "inverted_row": {"trials": [13, None, None], "final": 13},
       "plank": {"trials": [125, None, None], "final": 125}}
FAST = {"max_spell_overs": 5, "max_match_day_overs": 16, "caution_match_day_overs": 12, "max_bowling_days_week": 3}


# ───────────── pure ─────────────
def test_day_load_uses_the_players_own_times_and_trials():
    d = day_load(RES)
    run = next(p for p in d["parts"] if p["key"] == "run_2km")
    plank = next(p for p in d["parts"] if p["key"] == "plank")
    assert run["minutes"] == round(567 / 60, 1) and run["rpe"] == 9 and run["load"] == round(run["minutes"] * 9)
    assert plank["minutes"] == round(125 / 60 + 1, 1)
    assert next(p for p in d["parts"] if p["key"] == "sprint_20m")["minutes"] == 4.5                  # 3 trials x 1.5 min
    assert d["load"] == sum(p["load"] for p in d["parts"]) and d["minutes"] == round(sum(p["minutes"] for p in d["parts"]))
    assert 1 <= d["rpe"] <= 10
    slower = day_load({**RES, "run_2km": {"trials": [660], "final": 660}})
    assert slower["load"] > d["load"]                                                                 # a slower run is more work
    two = day_load({**RES, "sprint_20m": {"trials": [3.3, 3.2, None], "final": 3.2}})
    assert next(p for p in two["parts"] if p["key"] == "sprint_20m")["minutes"] == 3.0
    assert day_load({})["parts"][0]["key"] == "warm_up" and len(day_load({})["parts"]) == 2           # nothing tested: warm-up and cool-down only


def test_training_doses_come_from_the_results():
    t = {x["test"]: x for x in training_targets(RES)}
    assert "4:43" not in t["2 km run"]["prescription"] and "5:54" in t["2 km run"]["prescription"]   # 9:27 / 2 = 4:43.5 per km, easy x1.25
    assert "3 sets of 15-19 push-ups" in t["Push-ups"]["prescription"]                                 # 50-65% of 30
    assert "3 sets of 6-8 inverted rows" in t["Inverted row"]["prescription"]
    assert "60 s" in t["Plank"]["prescription"]
    spurt = {x["test"]: x for x in training_targets(RES, in_spurt=True)}
    assert "15-25" in spurt["Standing broad jump"]["prescription"] and "4-6 sprints" in spurt["20 m sprint"]["prescription"]
    assert training_targets({}) == []


def test_fast_bowler_limits_follow_endurance_and_core():
    ok = bowling_advice("fast_bowler", None, FAST, FAST, {"endurance": 60, "core": 70}, {"overs_7d": 12.0, "days_bowled_7d": ["a", "b"]})
    assert ok["suggested"] == ok["limits"] and not ok["stricter"] and ok["current"] == {"overs_7d": 12.0, "bowling_days_7d": 2}
    low = bowling_advice("fast_bowler", None, FAST, FAST, {"endurance": 30, "core": 20}, None)
    assert low["stricter"] and low["suggested"]["max_match_day_overs"] == 12 and low["suggested"]["max_spell_overs"] == 4
    assert len(low["reasons"]) == 2
    assert bowling_advice("all_rounder", {"fast"}, None, FAST, {}, None)["limits"]["max_spell_overs"] == 5
    assert bowling_advice("all_rounder", {"spin"}, None, FAST, {}, None) is None
    assert bowling_advice("batter", None, None, FAST, {}, None) is None


# ───────────── API ─────────────
@pytest.fixture
def tested(client, world, db, monkeypatch):
    monkeypatch.setattr(testing_router, "today_lk", lambda: date(2027, 3, 1))     # the test day (1 Feb 2027) is in the past
    ids = add_players(db, world)
    db.get(Player, ids[0]).role = PlayerRole.fast_bowler
    db.commit()
    sid = make_season(client, world)
    r = upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    assert r.status_code == 200, r.text
    return ids, sid, r.json()


def _test_logs(db, pid):
    return db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == pid, WorkloadLog.session_type == EventType.fitness_test)).all()


def test_import_adds_the_test_day_to_the_workload(client, world, db, tested):
    ids, sid, res = tested
    assert res["test_day_load"] == {"logged": len(ids)}
    logs = _test_logs(db, ids[0])
    assert len(logs) == 1 and logs[0].log_date == date(2027, 2, 1) and logs[0].duration_min > 20 and logs[0].rpe


def test_overview_and_relogging_is_idempotent_and_keeps_coach_logs(client, world, db, tested):
    ids, sid, _ = tested
    url = f"/squads/{world['squad_a']}/seasons/{sid}/test-workload"
    d = client.get(f"{url}?window=baseline", headers=H(world, "coach_a")).json()
    assert len(d["players"]) == len(ids) and all(r["logged"] == "system" for r in d["players"])
    fast = next(r for r in d["players"] if r["player_id"] == ids[0])
    assert fast["bowling"] and fast["bowling"]["limits"]["max_spell_overs"] == 5
    assert all(r["bowling"] is None for r in d["players"] if r["player_id"] != ids[0])                # batters: no bowling part
    assert fast["targets"] and fast["day_load"]["load"] > 0
    # a coach's own log for the test day is never changed
    own = _test_logs(db, ids[1])[0]
    own.match_participation, own.rpe = None, 3
    db.commit()
    r = client.post(f"{url}/log?window=baseline", headers=H(world, "sc_a")).json()
    assert r["updated"] == len(ids) - 1 and r["coach_logged"] == 1 and r["logged"] == 0
    db.expire_all()
    assert _test_logs(db, ids[1])[0].rpe == 3 and all(len(_test_logs(db, i)) == 1 for i in ids)       # no duplicates


def test_who_can_see_and_log(client, world, tested):
    ids, sid, _ = tested
    url = f"/squads/{world['squad_a']}/seasons/{sid}/test-workload"
    assert client.get(f"{url}?window=baseline", headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.post(f"{url}/log?window=baseline", headers=H(world, "physio_a")).status_code == 403
    assert client.get(f"{url}?window=winter", headers=H(world, "admin")).status_code == 422
