"""Phase 3: workload rules engine, log/wellness API, alerts, limits, privacy."""
import json
from datetime import timedelta

import pytest

from app import workload_rules as wr
from app.models import PlayerMedical
from app.workload_service import today_lk

H = lambda w, who: w["h"][who]
TODAY = today_lk()
d = lambda n: TODAY - timedelta(days=n)          # n days ago


def L(n, **kw):
    kw.setdefault("duration_min", 60); kw.setdefault("rpe", 5)
    return wr.Log(date=d(n), **kw)


def codes(alerts):
    return {a.rule_code for a in alerts}


def run(logs, role="fast_bowler", wellness=(), avail="fit", custom=None):
    return wr.evaluate(list(logs), list(wellness), avail, role, custom, TODAY)


# ───────────── pure helpers ─────────────
def test_overs_and_balls():
    assert wr.overs_to_balls(3.2) == 20 and wr.overs_to_balls(0) == 0 and wr.overs_to_balls(5.0) == 30
    assert wr.balls_to_overs(20) == 3.2 and wr.balls_to_overs(36) == 6.0
    for bad in (3.7, 3.6, -1):
        with pytest.raises(ValueError):
            wr.overs_to_balls(bad)


def test_effective_limits():
    f = wr.effective_limits("fast_bowler", None)
    assert f["max_spell_overs"] == 5 and f["max_match_day_overs"] == 16 and f["caution_match_day_overs"] == 12 and f["max_bowling_days_week"] == 3
    assert wr.effective_limits("spin_bowler", None) is None
    assert wr.effective_limits("batter", {}) is None
    assert wr.effective_limits("spin_bowler", {"max_spell_overs": 4})["max_spell_overs"] == 4
    assert wr.effective_limits("fast_bowler", {"max_match_day_overs": 10})["caution_match_day_overs"] is None
    assert wr.effective_limits("fast_bowler", {"bogus": 3})["max_spell_overs"] == 5      # unknown keys ignored


def test_session_load():
    assert wr.session_load(wr.Log(date=TODAY, duration_min=60, rpe=6)) == (360.0, "RPE x minutes")
    assert wr.session_load(wr.Log(date=TODAY, duration_min=60, intensity=7))[0] == 420.0
    assert wr.session_load(wr.Log(date=TODAY, attended=False))[0] == 0.0
    assert wr.session_load(wr.Log(date=TODAY, duration_min=60))[0] is None
    assert wr.session_load(wr.Log(date=TODAY, rpe=5))[0] is None


# ───────────── load rules ─────────────
def steady(weeks=4, per_day=300, days_per_week=5):
    return [L(w * 7 + i, rpe=5, duration_min=per_day // 5) for w in range(weeks) for i in range(days_per_week)]


def test_acwr_needs_three_weeks():
    alerts, s = run([L(0, rpe=9, duration_min=120), L(1, rpe=9, duration_min=120)])
    assert s["acwr"] is None and s["acwr_status"] == "insufficient_data" and "LOAD_ACWR" not in codes(alerts)


def test_acwr_high_flags_warn():
    base = [L(i, rpe=5, duration_min=30) for i in range(7, 28)]                  # three steady weeks
    spike = [L(i, rpe=8, duration_min=90) for i in range(0, 7)]                  # then a big week
    alerts, s = run(base + spike)
    a = [x for x in alerts if x.rule_code == "LOAD_ACWR"]
    assert a and a[0].severity == "warn" and s["acwr"] > 1.5
    assert "LOAD_WEEK_SPIKE" in codes(alerts)


def test_steady_load_no_load_alerts():
    alerts, s = run([L(i, rpe=5, duration_min=40) for i in range(28) if i % 7 != 3])
    assert not (codes(alerts) & {"LOAD_ACWR", "LOAD_WEEK_SPIKE", "NO_REST_DAY"})
    assert s["acwr_status"] == "ok"


def test_no_rest_day_and_monotony():
    logs = [L(i, rpe=5, duration_min=60 + (i % 3) * 2) for i in range(14)]        # hard every day, barely any variation
    alerts, s = run(logs)
    assert "NO_REST_DAY" in codes(alerts)
    assert s["monotony_7d"] > 2 and "LOAD_MONOTONY" in codes(alerts)
    alerts, s = run([L(i, rpe=5, duration_min=60) for i in range(14)])           # identical days: spread is zero, ratio undefined
    assert s["monotony_7d"] is None and "LOAD_MONOTONY" not in codes(alerts)


def test_month_comparison_present():
    _, s = run([L(i) for i in range(0, 56, 2)])
    assert s["month_vs_last_month_pct"] is not None and len(s["weekly_loads_oldest_first"]) == 8


# ───────────── bowling rules ─────────────
def test_spell_limit_stop():
    alerts, _ = run([L(1, overs_bowled=6.0, spells=[{"overs": 6}])])
    a = [x for x in alerts if x.rule_code == "BOWL_SPELL_OVERS"]
    assert a and a[0].severity == "stop" and a[0].ref_date == d(1)


def test_day_limit_and_caution():
    assert "BOWL_DAY_OVERS_CAUTION" in codes(run([L(1, balls_bowled=13 * 6)])[0])
    a, _ = run([L(1, balls_bowled=17 * 6)])
    assert "BOWL_DAY_OVERS" in codes(a) and "BOWL_DAY_OVERS_CAUTION" not in codes(a)
    assert not (codes(run([L(1, balls_bowled=12 * 6)])[0]) & {"BOWL_DAY_OVERS", "BOWL_DAY_OVERS_CAUTION"})   # exactly 12 is fine


def test_two_split_sessions_add_up():
    a, _ = run([L(1, balls_bowled=9 * 6), L(1, balls_bowled=9 * 6)])         # 18 overs in one day
    assert "BOWL_DAY_OVERS" in codes(a)


def test_bowling_days_per_week():
    a, _ = run([L(0, balls_bowled=30), L(2, balls_bowled=30), L(4, balls_bowled=30)])
    assert [x.severity for x in a if x.rule_code == "BOWL_DAYS_WEEK"] == ["info"]
    a, _ = run([L(0, balls_bowled=30), L(2, balls_bowled=30), L(4, balls_bowled=30), L(6, balls_bowled=30)])
    assert [x.severity for x in a if x.rule_code == "BOWL_DAYS_WEEK"] == ["stop"]


def test_back_to_back_and_three_in_a_row():
    a, _ = run([L(3, balls_bowled=30), L(2, balls_bowled=30)])
    assert "BOWL_BACK_TO_BACK" in codes(a) and "BOWL_THREE_IN_A_ROW" not in codes(a)
    a, _ = run([L(3, balls_bowled=30), L(2, balls_bowled=30), L(1, balls_bowled=30)])
    assert "BOWL_THREE_IN_A_ROW" in codes(a)


def test_old_bowling_outside_window_ignored():
    assert not (codes(run([L(10, balls_bowled=30 * 4, spells=[{"overs": 9}])])[0]) & {"BOWL_SPELL_OVERS", "BOWL_DAY_OVERS"})


def test_unattended_bowling_does_not_count():
    assert not codes(run([wr.Log(date=d(1), attended=False, balls_bowled=200)])[0])


def test_spin_has_no_automatic_limits_until_set():
    big = [L(1, balls_bowled=20 * 6, spells=[{"overs": 10}, {"overs": 10}])]
    assert not (codes(run(big, role="spin_bowler")[0]) & {"BOWL_SPELL_OVERS", "BOWL_DAY_OVERS", "BOWL_DAYS_WEEK"})
    a, _ = run(big, role="spin_bowler", custom={"max_spell_overs": 4})
    assert "BOWL_SPELL_OVERS" in codes(a)
    for role in ("batter", "all_rounder", "bat_wicketkeeper"):
        assert not (codes(run(big, role=role)[0]) & {"BOWL_SPELL_OVERS", "BOWL_DAY_OVERS"})


# ───────────── wellness and availability ─────────────
def test_pain_flag_is_stop_and_has_no_detail():
    a, _ = run([], wellness=[wr.Wellness(date=d(1), pain_flag=True)])
    x = [i for i in a if i.rule_code == "WELLNESS_PAIN"]
    assert x and x[0].severity == "stop" and "physiotherapist" in x[0].message


def test_high_soreness_and_low_sleep():
    a, _ = run([], wellness=[wr.Wellness(date=d(0), soreness=9)])
    assert "WELLNESS_HIGH" in codes(a)
    a, _ = run([], wellness=[wr.Wellness(date=d(i), sleep_hours=5.5) for i in range(3)])
    assert "WELLNESS_SLEEP" in codes(a)
    a, _ = run([], wellness=[wr.Wellness(date=d(i), sleep_hours=9) for i in range(3)])
    assert "WELLNESS_SLEEP" not in codes(a)


def test_unavailable_with_session_is_stop():
    a, _ = run([L(1)], avail="unavailable")
    assert "UNAVAILABLE_SESSION" in codes(a)
    assert "UNAVAILABLE_SESSION" not in codes(run([L(1)], avail="modified")[0])


# ───────────── progressive overload guidance ─────────────
def test_guidance_variants():
    ok_logs = [L(i, rpe=5, duration_min=40) for i in range(28) if i % 7 != 3]
    alerts, s = run(ok_logs)
    g = wr.overload_guidance(s, alerts, "pre_season")
    assert g["action"] == "build" and g["next_week_load"][0] <= g["next_week_load"][1] <= s["chronic_weekly_load_28d"] * 1.3 + 1
    assert wr.overload_guidance(s, alerts, "transition")["action"] == "reduce"
    assert wr.overload_guidance(s, alerts, "in_season")["action"] == "maintain"
    stop = [wr.Alert("X", "stop", "m")]
    assert wr.overload_guidance(s, stop)["action"] == "reduce"
    assert wr.overload_guidance(s, [wr.Alert("X", "warn", "m")])["action"] == "hold"
    _, s2 = run([L(0)])
    assert wr.overload_guidance(s2, [])["action"] == "insufficient_data"
    assert "proven safe" in g["note"]


def test_guidance_deload_after_four_rising_weeks():
    logs = [L(w * 7 + k, rpe=5, duration_min=20 + (3 - w) * 8) for w in range(4) for k in range(7) if k != 5]   # oldest week lightest
    _, s = run(logs)
    w = s["weekly_loads_oldest_first"]
    assert w[-1] > w[-2] > w[-3] > w[-4] > 0
    g = wr.overload_guidance(s, [])
    assert g["action"] == "deload" and g["next_week_load"][1] < s["acute_load_7d"]


# ───────────── API ─────────────
def post_log(client, w, who, pid, **kw):
    body = {"log_date": str(TODAY), "duration_min": 60, "rpe": 6}
    body.update(kw)
    return client.post(f"/players/{pid}/workload", json=body, headers=H(w, who))


def test_log_derives_balls_and_overs(client, world):
    r = post_log(client, world, "coach_a", world["bob"], overs_bowled=3.2, spells=[{"overs": 3.2, "minutes": 20}])
    assert r.status_code == 201, r.text
    log = r.json()["log"]
    assert log["balls_bowled"] == 20 and log["overs_bowled"] == 3.2 and log["load"] == 360 and log["load_basis"] == "RPE x minutes"
    r = post_log(client, world, "coach_a", world["bob"], balls_bowled=20)
    assert r.json()["log"]["overs_bowled"] == 3.2


@pytest.mark.parametrize("extra", [
    {"overs_bowled": 3.7}, {"overs_bowled": 3.2, "balls_bowled": 21}, {"rpe": 11}, {"duration_min": 0},
    {"balls_bowled": 12, "spells": [{"overs": 3}]}, {"attended": False, "duration_min": 60},
    {"log_date": str(TODAY + timedelta(days=1))}, {"balls_bowled": 5000},
])
def test_log_validation(client, world, extra):
    assert post_log(client, world, "coach_a", world["bob"], **extra).status_code == 422


def test_unattended_log_ok(client, world):
    r = client.post(f"/players/{world['bob']}/workload", json={"log_date": str(TODAY), "attended": False}, headers=H(world, "coach_a"))
    assert r.status_code == 201 and r.json()["log"]["load"] == 0


def test_over_limit_creates_alert_then_resolves_when_log_deleted(client, world):
    r = post_log(client, world, "coach_a", world["bob"], overs_bowled=6.0, spells=[{"overs": 6}])
    assert r.status_code == 201
    assert any(a["rule_code"] == "BOWL_SPELL_OVERS" and a["severity"] == "stop" for a in r.json()["open_alerts"])
    alerts = client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json()
    spell = [a for a in alerts if a["rule_code"] == "BOWL_SPELL_OVERS"]
    assert len(spell) == 1 and spell[0]["player_name"] == "Bob"
    # saving the same facts again does not duplicate the alert
    post_log(client, world, "coach_a", world["bob"], duration_min=30, rpe=3)
    assert len([a for a in client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json() if a["rule_code"] == "BOWL_SPELL_OVERS"]) == 1
    ack = client.post(f"/alerts/{spell[0]['id']}/acknowledge", headers=H(world, "physio_a"))
    assert ack.status_code == 200 and ack.json()["acknowledged_by"] == world["users"]["physio_a"].id
    logid = r.json()["log"]["id"]
    assert client.delete(f"/workload/{logid}", headers=H(world, "coach_a")).status_code == 204
    left = client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json()
    assert not [a for a in left if a["rule_code"] == "BOWL_SPELL_OVERS"]
    allx = client.get(f"/squads/{world['squad_a']}/alerts?include_resolved=true", headers=H(world, "coach_a")).json()
    assert [a for a in allx if a["rule_code"] == "BOWL_SPELL_OVERS" and a["resolved_at"]]


def test_edit_log_rechecks_alerts(client, world):
    r = post_log(client, world, "coach_a", world["bob"], overs_bowled=6.0, spells=[{"overs": 6}])
    lid = r.json()["log"]["id"]
    p = client.patch(f"/workload/{lid}", json={"spells": [{"overs": 5}]}, headers=H(world, "coach_a"))
    assert p.status_code == 200, p.text
    assert not [a for a in p.json()["open_alerts"] if a["rule_code"] == "BOWL_SPELL_OVERS"]
    p = client.patch(f"/workload/{lid}", json={"overs_bowled": 2.0}, headers=H(world, "coach_a"))
    assert p.status_code == 422                                 # spells (5 overs) now exceed the overs bowled
    p = client.patch(f"/workload/{lid}", json={"attended": False}, headers=H(world, "coach_a"))
    assert p.status_code == 422
    assert client.patch("/workload/99999", json={"rpe": 3}, headers=H(world, "coach_a")).status_code == 404


def test_scope_and_roles(client, world):
    bob, ann = world["bob"], world["ann"]
    assert post_log(client, world, "coach_b", bob).status_code == 404                  # other squad's coach: not found
    assert client.get(f"/players/{bob}/workload/summary", headers=H(world, "coach_b")).status_code == 404
    assert client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_b")).status_code == 404
    assert post_log(client, world, "ann_login", ann).status_code == 201                # a player logs their own
    assert post_log(client, world, "ann_login", bob).status_code == 404                # but not someone else's
    assert post_log(client, world, "physio_a", bob).status_code == 403                 # physio does not log sessions
    lid = post_log(client, world, "coach_a", bob).json()["log"]["id"]
    assert client.delete(f"/workload/{lid}", headers=H(world, "ann_login")).status_code == 404
    assert client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "ann_login")).status_code == 403
    assert client.get(f"/squads/{world['squad_a']}/workload/overview", headers=H(world, "ann_login")).status_code == 403
    assert client.get(f"/players/{bob}/workload", headers=H(world, "ann_login")).status_code == 404
    assert client.get(f"/players/{bob}/workload").status_code == 401


def test_player_summary_hides_alerts_and_guidance(client, world):
    post_log(client, world, "ann_login", world["ann"])
    mine = client.get(f"/players/{world['ann']}/workload/summary", headers=H(world, "ann_login")).json()
    assert mine["alerts"] is None and mine["guidance"] is None and mine["summary"]["acute_load_7d"] == 360
    coach = client.get(f"/players/{world['ann']}/workload/summary", headers=H(world, "coach_a")).json()
    assert coach["alerts"] is not None and coach["guidance"]["action"] == "insufficient_data"
    r = post_log(client, world, "ann_login", world["ann"], rpe=7)
    assert r.json()["open_alerts"] is None


def test_check_planned_session(client, world):
    bob = world["bob"]
    r = client.post(f"/players/{bob}/workload/check", json={"log_date": str(TODAY), "overs_bowled": 7.0, "spells": [{"overs": 7}]}, headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["new_alerts"][0]["rule_code"] == "BOWL_SPELL_OVERS"
    r = client.post(f"/players/{bob}/workload/check", json={"log_date": str(TODAY), "overs_bowled": 4.0, "spells": [{"overs": 4}]}, headers=H(world, "coach_a"))
    assert r.json()["ok"] is True
    assert client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json() == []      # nothing was saved
    tomorrow = str(TODAY + timedelta(days=1))
    assert client.post(f"/players/{bob}/workload/check", json={"log_date": tomorrow, "overs_bowled": 4.0}, headers=H(world, "coach_a")).status_code == 200
    far = str(TODAY + timedelta(days=30))
    assert client.post(f"/players/{bob}/workload/check", json={"log_date": far}, headers=H(world, "coach_a")).status_code == 422
    assert client.post(f"/players/{bob}/workload/check", json={"log_date": str(TODAY)}, headers=H(world, "ann_login")).status_code == 403


def test_back_to_back_via_check(client, world):
    bob = world["bob"]
    post_log(client, world, "coach_a", bob, log_date=str(d(1)), balls_bowled=30)
    r = client.post(f"/players/{bob}/workload/check", json={"log_date": str(TODAY), "balls_bowled": 30}, headers=H(world, "coach_a"))
    assert [a["rule_code"] for a in r.json()["new_alerts"]] == ["BOWL_BACK_TO_BACK"]


def test_limits_for_spin_bowler(client, world):
    ann = world["ann"]
    assert "BOWL_SPELL_OVERS" not in [a["rule_code"] for a in post_log(client, world, "coach_a", ann, overs_bowled=8.0, spells=[{"overs": 8}]).json()["open_alerts"]]
    r = client.put(f"/players/{ann}/workload-limits", json={"max_spell_overs": 4}, headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.json()["effective"]["max_spell_overs"] == 4
    alerts = client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json()
    assert any(a["rule_code"] == "BOWL_SPELL_OVERS" for a in alerts)                  # re-checked straight away
    r = client.put(f"/players/{ann}/workload-limits", json={}, headers=H(world, "coach_a"))
    assert r.json()["effective"] is None
    assert not client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json()
    assert client.put(f"/players/{ann}/workload-limits", json={"max_spell_overs": 9, "max_match_day_overs": 5}, headers=H(world, "coach_a")).status_code == 422
    assert client.put(f"/players/{ann}/workload-limits", json={"max_spell_overs": 0}, headers=H(world, "coach_a")).status_code == 422
    assert client.put(f"/players/{ann}/workload-limits", json={"nope": 1}, headers=H(world, "coach_a")).status_code == 422
    for who in ("physio_a", "ann_login", "coach_b"):
        assert client.put(f"/players/{ann}/workload-limits", json={"max_spell_overs": 4}, headers=H(world, who)).status_code in (403, 404)


def test_wellness_upsert_and_pain_alert_without_detail(client, world, db):
    bob = world["bob"]
    db.add(PlayerMedical(player_id=bob, current_health={"note": "SECRET-LUMBAR-STRESS"}))
    db.commit()
    body = {"log_date": str(TODAY), "soreness": 4, "fatigue": 3, "sleep_hours": 8.5}
    a = client.post(f"/players/{bob}/wellness", json=body, headers=H(world, "coach_a"))
    assert a.status_code == 200
    b = client.post(f"/players/{bob}/wellness", json={**body, "pain_flag": True}, headers=H(world, "physio_a"))
    assert b.status_code == 200 and b.json()["id"] == a.json()["id"] and b.json()["pain_flag"] is True      # same day replaced
    assert len(client.get(f"/players/{bob}/wellness", headers=H(world, "coach_a")).json()) == 1
    alerts = client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json()
    pain = [x for x in alerts if x["rule_code"] == "WELLNESS_PAIN"]
    assert pain and pain[0]["severity"] == "stop"
    # clearing the flag resolves the alert
    client.post(f"/players/{bob}/wellness", json=body, headers=H(world, "physio_a"))
    assert not [x for x in client.get(f"/squads/{world['squad_a']}/alerts", headers=H(world, "coach_a")).json() if x["rule_code"] == "WELLNESS_PAIN"]
    assert client.post(f"/players/{bob}/wellness", json={**body, "soreness": 11}, headers=H(world, "coach_a")).status_code == 422
    assert client.post(f"/players/{bob}/wellness", json={**body, "log_date": str(TODAY + timedelta(days=1))}, headers=H(world, "coach_a")).status_code == 422
    assert client.post(f"/players/{bob}/wellness", json=body, headers=H(world, "coach_b")).status_code == 404


def test_no_medical_text_leaks_anywhere(client, world, db):
    bob = world["bob"]
    db.add(PlayerMedical(player_id=bob, current_health={"note": "SECRET-LUMBAR-STRESS"}, injury_history={"x": "SECRET-LUMBAR-STRESS"}))
    db.commit()
    post_log(client, world, "coach_a", bob, overs_bowled=6.0, spells=[{"overs": 6}])
    client.post(f"/players/{bob}/wellness", json={"log_date": str(TODAY), "pain_flag": True}, headers=H(world, "coach_a"))
    sq = world["squad_a"]
    for who in ("admin", "coach_a", "sc_a", "physio_a"):
        for url in (f"/squads/{sq}/alerts?include_resolved=true", f"/squads/{sq}/workload/overview", f"/players/{bob}/workload/summary",
                    f"/players/{bob}/workload", f"/players/{bob}/wellness", "/workload/rules"):
            r = client.get(url, headers=H(world, who))
            assert r.status_code == 200, (who, url)
            assert "SECRET-LUMBAR" not in r.text, (who, url)


def test_overview(client, world):
    post_log(client, world, "coach_a", world["bob"], overs_bowled=6.0, spells=[{"overs": 6}])
    rows = client.get(f"/squads/{world['squad_a']}/workload/overview", headers=H(world, "coach_a")).json()
    by = {r["name"]: r for r in rows}
    assert set(by) == {"Ann", "Bob"}                               # squad B's Cara never appears
    assert by["Bob"]["worst_severity"] == "stop" and by["Bob"]["overs_7d"] == 6.0 and by["Bob"]["bowling_days_7d"] == 1
    assert by["Ann"]["worst_severity"] is None and by["Ann"]["acwr_status"] == "insufficient_data"
    assert client.get(f"/squads/{world['squad_b']}/workload/overview", headers=H(world, "admin")).status_code == 200


def test_unavailable_player_session_alert(client, world, db):
    from app.models import Availability, Player
    p = db.get(Player, world["bob"]); p.availability = Availability.unavailable; db.commit()
    r = post_log(client, world, "coach_a", world["bob"])
    assert any(a["rule_code"] == "UNAVAILABLE_SESSION" for a in r.json()["open_alerts"])


def test_rules_endpoint(client, world):
    r = client.get("/workload/rules", headers=H(world, "ann_login"))
    assert r.status_code == 200 and r.json()["fast_bowler_defaults"]["max_spell_overs"] == 5
    assert client.get("/workload/rules").status_code == 401


def test_history_grows_with_first_log_date(client, world):
    for n in (30, 24, 17, 10, 3):
        post_log(client, world, "coach_a", world["bob"], log_date=str(d(n)))
    s = client.get(f"/players/{world['bob']}/workload/summary", headers=H(world, "coach_a")).json()
    assert s["summary"]["history_days"] == 31 and s["summary"]["acwr"] is not None
