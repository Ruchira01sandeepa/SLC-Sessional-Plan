"""The periodized annual plan (ANNUAL PLAN BUILDER: Zatsiorsky & Kraemer + NSCA), beside the seasonal plan."""
import io
from datetime import date

import openpyxl
import pytest

from app.planning import periodized_plan as pp
from app.exports.excel.periodized_excel import build_workbook
from app.planning.season_phases import suggest_phases

H = lambda w, who: w["h"][who]
TOURNAMENT = ({"name": "Galle", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)},
              [{"phase_type": "in_season", "start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}])
LEAGUE = ({"name": "2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 9, 30)}, suggest_phases(date(2027, 1, 1), date(2027, 9, 30)))


def plan(case=TOURNAMENT, matches=()):
    season, phases = case
    return pp.build(squad="X", age_group="U15", season=season, phases=phases, matches=list(matches), results={}, players=20)


@pytest.mark.parametrize("case", [TOURNAMENT, LEAGUE], ids=["tournament", "league"])
def test_every_rule_passes(case):
    p = plan(case)
    failed = [rule for rule, ok, _ in pp.verify(p) if not ok]
    assert not failed, failed
    assert p["weeks"] == 52 and len(p["codes"]) == 52 and sum(len(m["codes"]) for m in p["mesos"]) == 52


def test_tournament_year_is_built_backward_from_next_years_main_competition():
    p = plan()
    seq = [m["codes"][0] for m in p["mesos"]]
    assert seq[0] == "P" and seq[1] == "T" and seq[-1] == "U"                        # tournament, active rest ... taper at the end
    assert p["mesos"][-1]["codes"] == ["U", "P", "P", "P"] and p["mesos"][-1]["type"] == "Realization"
    sizes = [len(m["codes"]) for m in p["mesos"] if m["codes"][0] in pp.PREP]
    assert sizes == sorted(sizes, reverse=True) and set(sizes) <= {3, 4}             # 3:1 then 2:1, shorter toward competition
    peak = max(range(52), key=lambda w: p["loads"][w])
    assert p["codes"][peak] == "S" and p["loads"][peak] == 1.0
    assert all(0.30 <= p["loads"][w] <= 0.40 for w in range(52) if p["codes"][w] == "T")
    assert next(c for c in p["competitions"] if c.get("next_year"))["start"] == date(2027, 11, 25)


def test_league_final_gets_its_realization_block_and_no_one_week_mesocycles():
    p = plan(LEAGUE)
    assert all(2 <= len(m["codes"]) <= 6 for m in p["mesos"])
    final = next(m for m in p["mesos"] if m.get("mini"))
    assert final["codes"][-1] == "P" and len(final["codes"]) == 3
    assert "U" in p["codes"]                                                          # the first transition before the league


def test_conditioning_never_rises_more_than_10_percent_and_work_rest_fits_the_system():
    for case in (TOURNAMENT, LEAGUE):
        p = plan(case)
        for rows in p["conditioning"]:
            for r in rows:
                assert r["continuous"] or r["wr_lo"] <= r["rest_s"] / r["work_s"] <= r["wr_hi"], r


def test_youth_rules():
    p = plan()
    assert max(p["sessions"][0]) <= 3 and max(p["plyo"]) <= pp.PLYO_MAX_CONTACTS
    assert all(r["pct"] is None or r["pct"] <= 0.80 for r in p["resistance"])          # no maximal loads for U15
    assert all(r["pct"] is None or r["reps"] <= pp.max_reps(r["pct"]) for r in p["resistance"])
    for s in p["session_plans"]:
        assert abs(s["minutes"] - s["duration"]) <= 5


def test_calendar_matches_drive_the_competitions():
    p = plan(LEAGUE, matches=[{"date": date(2027, 6, d), "title": "Cup"} for d in (5, 6, 7)])
    comp = [c for c in p["competitions"] if not c.get("next_year")]
    assert comp[0]["type"] == "MAIN" and comp[0]["start"] == date(2027, 6, 5) and not comp[0]["assumed"]


def test_workbook_sheets_formulas_and_no_text_formulas():
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(plan())))
    assert wb.sheetnames == ["Inputs", "Annual plan", "Week data", "Load chart", "Methods by phase", "Mesocycles", "Microcycles",
                             "Conditioning detail", "Resistance detail", "Session plans", "Checks"]
    assert {"StartDate", "Weeks", "MaxLoad"} <= set(wb.defined_names.keys())
    ap = wb["Annual plan"]
    assert ap["A5"].value == "Month" and ap["A4"].value == "Mesocycle # and type"     # months are never called mesocycles
    assert ap["B7"].value == "=StartDate+7*(B6-1)" and ap["B16"].value.startswith("=IF(B13>=0.75")
    assert "MethodsByPhase" in wb["Methods by phase"].tables
    assert wb["Week data"]["T2"].value.startswith("=SUMPRODUCT(")                       # totals are formulas, never typed
    assert len(wb["Load chart"]._charts) == 2
    checks = [wb["Checks"].cell(row=r, column=3).value for r in range(2, 26)]
    assert all(isinstance(c, str) and c.startswith("=IF") for c in checks)
    assert all(wb["Checks"].cell(row=r, column=5).value in ("PASS", "n/a") for r in range(2, 26))
    for ws in wb:                                                                      # exercise and label text is never a formula
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.data_type != "f":
                    assert not c.value.startswith("="), (ws.title, c.coordinate)


def test_endpoint_and_access(client, world):
    sid = client.post(f"/squads/{world['squad_a']}/seasons", json={"name": "cup", "start_date": "2028-01-01", "end_date": "2028-01-10",
                                                                   "phases": []}, headers=H(world, "admin")).json()["id"]
    url = f"/squads/{world['squad_a']}/seasons/{sid}/periodized-plan.xlsx"
    r = client.get(url, headers=H(world, "coach_a"))
    assert r.status_code == 200 and "Periodized-annual-plan" in r.headers["content-disposition"]
    assert openpyxl.load_workbook(io.BytesIO(r.content))["Checks"]["B2"].value.startswith("Every week")
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    other = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx", headers=H(world, "coach_a"))
    assert other.status_code == 200                                                    # the seasonal plan is still there


# ───────────── each player's own periodized plan ─────────────
ALL_WEAK = [{"area": a, "label": a, "percentile": 10.0} for a in ("endurance", "power", "upper_strength", "speed", "agility", "core")]


def level(p, label):
    return next(v for _, rows in p["factors"] for lab, v in rows if lab == label)


def test_weak_areas_get_more_and_every_rule_still_passes():
    base = plan()
    me = pp.personalize(base, name="Nisal", role="Batter", areas=ALL_WEAK)
    assert not [r for r, ok, _ in pp.verify(me) if not ok]
    assert sum(level(me, "Speed")) > sum(level(base, "Speed")) and sum(level(me, "Trunk / core strength")) > sum(level(base, "Trunk / core strength"))
    assert sum(x["distance"] * x["reps"] for rows in me["conditioning"] for x in rows) > \
        sum(x["distance"] * x["reps"] for rows in base["conditioning"] for x in rows)
    assert max(me["plyo"]) <= pp.PLYO_MAX_CONTACTS and sum(me["plyo"]) > sum(base["plyo"])
    assert any(r.get("extra") for r in me["resistance"]) and me["squad"].startswith("Nisal")
    assert base["squad"] == "X" and not any(r.get("extra") for r in base["resistance"])        # the squad plan is untouched


def test_strong_player_keeps_the_full_squad_work():
    base = plan()
    me = pp.personalize(base, name="Sethuja", role="Batter", areas=[{**a, "percentile": 90.0} for a in ALL_WEAK])
    assert me["factors"] == base["factors"] and me["conditioning"] == base["conditioning"] and me["sessions"] == base["sessions"]
    assert len(me["player"]["strong"]) == 6 and not me["player"]["weak"]


def test_player_endpoint_and_access(client, world):
    sid = client.post(f"/squads/{world['squad_a']}/seasons", json={"name": "cup", "start_date": "2028-01-01", "end_date": "2028-01-10",
                                                                   "phases": []}, headers=H(world, "admin")).json()["id"]
    url = f"/squads/{world['squad_a']}/seasons/{sid}/periodized-plan/{world['ann']}.xlsx"
    r = client.get(url, headers=H(world, "coach_a"))
    assert r.status_code == 200 and "Periodized-plan-" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert any(str(c.value).startswith("PLAYER: ") for c in wb["Inputs"]["A"])
    assert client.get(url).status_code == 401
    assert client.get(url, headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/periodized-plan/999999.xlsx", headers=H(world, "coach_a")).status_code == 404
