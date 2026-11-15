"""Earlier workload: weeks before the app was used, entered as one summary per player and week."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import earlier_workload as ew
from app.models import WorkloadLog
from app.workload_service import today_lk

H = lambda w, who: w["h"][who]
MON = date(2026, 10, 5)


# ───────────── pure ─────────────
def test_sessions_are_spread_one_a_day_and_avoid_taken_days():
    assert ew.session_days(MON, 0) == []
    three = ew.session_days(MON, 3)
    assert len(set(three)) == 3 and all(MON <= d < MON + timedelta(days=7) for d in three)
    assert ew.session_days(MON, 7) == [MON + timedelta(days=i) for i in range(7)]
    taken = {MON, MON + timedelta(days=2)}
    assert not taken & set(ew.session_days(MON, 4, taken))                  # free days first
    assert len(ew.session_days(MON, 7, taken)) == 7                        # all 7: taken days used only when needed
    with pytest.raises(ValueError):
        ew.session_days(MON, 8)


def test_week_spread_keeps_the_totals():
    rows = ew.spread_week(MON, sessions=4, minutes=75, rpe=6, overs=20.3, bowling_days=3)
    assert len(rows) == 4 and all(r["duration_min"] == 75 and r["rpe"] == 6 for r in rows)
    balls = [r["balls_bowled"] for r in rows if r["balls_bowled"]]
    assert len(balls) == 3 and sum(balls) == 123 and max(balls) - min(balls) <= 1          # 20.3 overs = 123 balls, evenly
    s = ew.summarise(rows)
    assert s == {"sessions": 4, "minutes": 75, "rpe": 6, "overs": 20.3, "bowling_days": 3, "load": 4 * 75 * 6}
    for bad in (dict(sessions=2, minutes=60, rpe=5, overs=10, bowling_days=3), dict(sessions=2, minutes=5, rpe=5),
                dict(sessions=2, minutes=60, rpe=11), dict(sessions=2, minutes=60, rpe=5, overs=3.7), dict(sessions=2, minutes=60, rpe=5, bowling_days=1)):
        with pytest.raises(ValueError):
            ew.spread_week(MON, **bad)


# ───────────── API ─────────────
def _monday(weeks_back: int) -> date:
    t = today_lk()
    return t - timedelta(days=t.weekday()) - timedelta(weeks=weeks_back)


def _put(client, w, who, week, rows):
    return client.put(f"/squads/{w['squad_a']}/workload/earlier", json={"week_start": week.isoformat(), "rows": rows}, headers=H(w, who))


def test_enter_replace_and_clear_a_week(client, world, db):
    w, bob = world, world["bob"]
    wk = _monday(2)
    r = _put(client, w, "coach_a", wk, [{"player_id": bob, "sessions": 4, "minutes": 75, "rpe": 6, "overs": 24, "bowling_days": 3}])
    assert r.status_code == 200 and r.json()["saved"] == 1
    got = client.get(f"/squads/{w['squad_a']}/workload/earlier?week_start={wk}", headers=H(w, "sc_a")).json()
    entry = next(p for p in got["players"] if p["player_id"] == bob)["entry"]
    assert entry["sessions"] == 4 and entry["overs"] == 24 and entry["bowling_days"] == 3
    _put(client, w, "coach_a", wk, [{"player_id": bob, "sessions": 2, "minutes": 60, "rpe": 5}])          # re-entering replaces
    assert len(db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == bob)).all()) == 2
    _put(client, w, "coach_a", wk, [{"player_id": bob, "sessions": 0}])                                  # 0 clears
    assert db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == bob)).all() == []


def test_weeks_with_logged_sessions_are_refused_and_nothing_is_saved(client, world, db):
    w, bob, ann = world, world["bob"], world["ann"]
    wk = _monday(1)
    db.add(WorkloadLog(player_id=bob, log_date=wk + timedelta(days=1), session_type="training", duration_min=60, rpe=5))
    db.commit()
    r = _put(client, w, "coach_a", wk, [{"player_id": ann, "sessions": 3, "minutes": 60, "rpe": 5},
                                        {"player_id": bob, "sessions": 3, "minutes": 60, "rpe": 5}])
    assert r.status_code == 422 and "already has sessions" in str(r.json()["detail"])
    assert db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == ann)).all() == []            # all or nothing
    assert next(p for p in client.get(f"/squads/{w['squad_a']}/workload/earlier?week_start={wk}", headers=H(w, "admin")).json()["players"]
                if p["player_id"] == bob)["logged_sessions"] == 1


def test_three_earlier_weeks_give_a_load_ratio(client, world):
    w, bob = world, world["bob"]
    before = next(r for r in client.get(f"/squads/{w['squad_a']}/workload/overview", headers=H(w, "admin")).json() if r["player_id"] == bob)
    assert before["acwr"] is None
    for k in (4, 3, 2, 1):
        assert _put(client, w, "coach_a", _monday(k), [{"player_id": bob, "sessions": 4, "minutes": 70, "rpe": 6}]).status_code == 200
    after = next(r for r in client.get(f"/squads/{w['squad_a']}/workload/overview", headers=H(w, "admin")).json() if r["player_id"] == bob)
    assert after["history_days"] >= 21


def test_rules_and_access(client, world):
    w, bob, cara = world, world["bob"], world["cara"]
    assert _put(client, w, "coach_a", _monday(0), [{"player_id": bob, "sessions": 1, "minutes": 60, "rpe": 5}]).status_code == 422   # this week
    assert _put(client, w, "coach_a", _monday(20), [{"player_id": bob, "sessions": 1, "minutes": 60, "rpe": 5}]).status_code == 422  # too far back
    assert _put(client, w, "coach_a", _monday(1), [{"player_id": cara, "sessions": 1, "minutes": 60, "rpe": 5}]).status_code == 422  # other squad
    assert _put(client, w, "bob_login", _monday(1), [{"player_id": bob, "sessions": 1, "minutes": 60, "rpe": 5}]).status_code == 403
    assert _put(client, w, "physio_a", _monday(1), [{"player_id": bob, "sessions": 1, "minutes": 60, "rpe": 5}]).status_code == 403
    assert client.get(f"/squads/{w['squad_b']}/workload/earlier?week_start={_monday(1)}", headers=H(w, "coach_a")).status_code == 404
