"""Workload calculation as in the McGawley workshop notes: every worked example, then the API and the Excel report."""
import io
from datetime import date, timedelta

import openpyxl
import pytest

from app import workload_calc as wc
from app.workload_service import today_lk

H = lambda w, who: w["h"][who]
MON = date(2027, 1, 11)
EXAMPLE = [("Soccer", 75, 5), ("HIT/STR", 90, 8), ("Soccer", 75, 5), ("HIT/STR", 90, 7), ("HIT/STR", 90, 8), ("Pilates", 45, 3)]


def example_week():
    return [{"date": MON + timedelta(days=i), "type": t, "minutes": m, "rpe": r} for i, (t, m, r) in enumerate(EXAMPLE)]


# ───────────── the worked examples ─────────────
def test_example_week_matches_the_workshop_numbers():
    w = wc.week_report(example_week(), MON)
    assert [d["load"] for d in w["days"]] == [375, 720, 375, 630, 720, 135, 0]       # Sunday rest = 0
    assert (w["total"], w["mean_daily"], w["sd_daily"], w["monotony"], w["strain"]) == (2955, 422, 285, 1.48, 4384)


def test_formulas_match_the_examples():
    assert wc.srpe(8, 90) == 720
    assert wc.edwards_trimp([0, 10, 0, 6, 9]) == 89                                    # 9 x 5 + 6 x 4 + 10 x 2
    assert wc.banister_trimp(30, 170, 60, 195) == pytest.approx(74.8, abs=0.5)          # about 75 AU
    assert wc.banister_trimp(30, 170, 60, 195, "female") == pytest.approx(82.0, abs=0.5)  # women: 0.86 e^(1.67 HRr)
    assert wc.volume_load(2, 10, 0.75, 99) == pytest.approx(1485)
    assert wc.performance_decrement([7.1, 7.3, 7.4, 7.6, 7.8, 7.9]) == pytest.approx(5.9, abs=0.05)
    assert wc.pct_change(99, 117) == pytest.approx(18.2, abs=0.05)
    assert wc.pct_change(1.78, 1.76) == pytest.approx(-1.1, abs=0.05)                  # faster sprint
    assert wc.effect_label(1.2) == "large" and wc.estimated_hr_max(15) == 198


def test_change_acwr_flags_and_load_percent():
    hist = example_week() + [{**s, "date": s["date"] - timedelta(days=7 * k), "rpe": 4} for k in (1, 2, 3) for s in example_week()]
    w = wc.week_report(example_week(), MON, history=hist)
    prev = sum(m * 4 for _, m, _ in EXAMPLE)                                            # 1,860 AU at RPE 4
    assert w["previous_week"] == prev and w["change_pct"] == pytest.approx((2955 - prev) / prev * 100, abs=0.1)
    assert any("keep under about 10%" in f for f in w["flags"])
    assert w["acwr"] == pytest.approx(2955 / ((2955 + 3 * prev) / 4), abs=0.01) and w["load_pct"] == 100
    early = wc.week_report(example_week(), MON)                                         # one week of data only
    assert early["acwr"] is None and early["acwr_band"] == "needs 3 weeks of data"


def test_test_change_effect_size_and_direction():
    pre, post = {1: 1.78, 2: 1.80, 3: 1.75}, {1: 1.76, 2: 1.77, 3: 1.75}               # 10 m sprint: lower is better
    t = wc.test_change(pre, post, lower_is_better=True)
    assert t["n"] == 3 and t["better"] and t["improved"] == 2 and t["change_pct"] < 0 and t["effect_size"] < 0


# ───────────── API and Excel ─────────────
def log(client, w, pid, who="coach_a", **kw):
    body = {"log_date": str(kw.pop("day", today_lk())), "duration_min": 90, "rpe": 7, **kw}
    return client.post(f"/players/{pid}/workload", json=body, headers=H(w, who))


def test_session_takes_heart_rate_and_external_load(client, world):
    r = log(client, world, world["bob"], hr_avg=162, zone_minutes=[5, 10, 20, 15, 9], sprint_m=450, volume_load_kg=1485,
            foot_contacts=60, sprint_times=[7.1, 7.3, 7.4, 7.6, 7.8, 7.9])
    assert r.status_code == 201 and r.json()["log"]["zone_minutes"] == [5, 10, 20, 15, 9]
    assert log(client, world, world["bob"], zone_minutes=[5, -1]).status_code == 422
    assert log(client, world, world["bob"], sprint_times=[0.2]).status_code == 422
    assert client.put(f"/players/{world['bob']}/heart-rate", json={"hr_max": 200, "hr_rest": 60}, headers=H(world, "coach_a")).status_code == 200
    assert client.put(f"/players/{world['bob']}/heart-rate", json={"hr_max": 160, "hr_rest": 170}, headers=H(world, "coach_a")).status_code == 422
    wk = client.get(f"/players/{world['bob']}/workload/week", headers=H(world, "coach_a")).json()
    assert wk["total"] == 630 and wk["sprint_m"] == 450 and wk["foot_contacts"] == 60 and wk["hit_minutes"] == 9
    assert wk["edwards_trimp"] == 5 + 20 + 60 + 60 + 45 and wk["banister_trimp"] > 0 and wk["sdec"] == pytest.approx(5.9, abs=0.05)
    assert len(wk["days"]) == 7 and wk["days"][0]["day"] == "Mon"


def test_squad_week_and_report(client, world):
    log(client, world, world["bob"])
    sq = client.get(f"/squads/{world['squad_a']}/workload/week", headers=H(world, "coach_a"))
    assert sq.status_code == 200 and {p["name"] for p in sq.json()["players"]} >= {"Bob"} or sq.json()["players"]
    r = client.get(f"/squads/{world['squad_a']}/workload/report.xlsx", headers=H(world, "coach_a"))
    assert r.status_code == 200 and "Workload-report" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Squad week" and wb.sheetnames[-4:] == ["Weekly trend", "Test change", "Formulas", "Process"]
    player = wb[wb.sheetnames[1]]
    labels = [player.cell(row=r_, column=1).value for r_ in range(1, player.max_row + 1)]
    assert "Monotony = mean / SD" in labels and "Strain = weekly load x monotony" in labels
    assert [player.cell(row=3, column=c).value for c in range(1, 7)] == ["Day", "Date", "Session", "Minutes", "RPE (0-10)", "Load (AU)"]
    assert player["F4"].value == "=N(D4)*N(E4)"                                       # load = minutes x RPE, by formula
    assert client.get(f"/squads/{world['squad_a']}/workload/report.xlsx").status_code == 401
    assert client.get(f"/squads/{world['squad_a']}/workload/week", headers=H(world, "coach_b")).status_code in (403, 404)


def test_overview_has_batting_and_fast_bowler_limit_data(client, world):
    log(client, world, world["bob"], balls_faced=120, keeping_minutes=30)
    log(client, world, world["bob"], balls_faced=60)
    row = next(r for r in client.get(f"/squads/{world['squad_a']}/workload/overview", headers=H(world, "coach_a")).json()
               if r["player_id"] == world["bob"])
    assert row["balls_faced_7d"] == 180 and row["batting_days_7d"] == 1 and row["keeping_minutes_7d"] == 30
    assert {"max_day_overs_7d", "max_spell_7d", "bowling_limits"} <= set(row)
