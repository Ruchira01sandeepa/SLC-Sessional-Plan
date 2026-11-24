"""Sit and reach and the ISAK 8-site skinfolds: the rules, typed entry, the squad record and the Excel template."""
import io

import openpyxl
import pytest

from app.test_battery import BY_KEY, SIT_REACH, SUPER, parse_skinfold, skinfold_final, skinfold_sum
from app.test_import import columns, parse_workbook, skinfold_header, trial_header
from tests.test_testing import H, fill, get_template, make_season, upload


def test_skinfold_rules():
    assert skinfold_final([8.6, 8.8, None]) == (8.7, False)          # within 5%: mean of two
    assert skinfold_final([8.0, 9.0, None]) == (8.5, True)           # 12.5% apart: a third is needed
    assert skinfold_final([8.0, 9.0, 8.4]) == (8.4, False)           # median of three
    assert skinfold_final([7.2, None, None]) == (7.2, False) and skinfold_final([None] * 3) == (None, False)
    sites = dict(zip(["sf_triceps", "sf_subscapular", "sf_biceps", "sf_iliac_crest", "sf_supraspinale", "sf_abdominal", "sf_front_thigh",
                      "sf_medial_calf"], (8.6, 9.2, 4.4, 8.8, 9.0, 9.0, 8.1, 8.8)))
    assert skinfold_sum(sites) == 65.9                               # the sheet's total for Sethuja
    assert skinfold_sum({**sites, "sf_biceps": None}) is None        # a partial sum would look leaner
    with pytest.raises(ValueError):
        parse_skinfold(95)


def test_enter_by_hand_and_squad_record(client, world):
    sid = make_season(client, world)
    url = f"/players/{world['bob']}/tests/{sid}/baseline"
    body = {"level": "super_provincial", "test_date": "2027-02-01", "weight_kg": 41.5,
            "results": {"broad_jump": ["180", "190", None], "run_2km": ["9.30", "", ""], "sit_reach": ["21", "24.5", "23"],
                        "sf_triceps": ["8.0", "9.0", None], "sf_biceps": ["4.4", "4.4", None]}}
    r = client.put(url, json=body, headers=H(world, "sc_a"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["results"]["broad_jump"]["final"] == "190.00" and out["results"]["run_2km"]["final"] == "9.30"
    ex = out["extras"]
    assert ex["sit_reach"]["final"] == 24.5 and ex["third_needed"] == 1 and ex["skinfold_sum"] is None
    assert client.put(url, json={"results": {"sf_triceps": ["99", None, None]}}, headers=H(world, "sc_a")).status_code == 422
    assert client.put(url, json={"results": {"bronco": ["6.00"]}}, headers=H(world, "sc_a")).status_code == 422     # not a Super Provincial test
    assert client.put(url, json=body, headers=H(world, "coach_a")).status_code == 403                              # S&C and admin only
    sq = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/body-tests?window=baseline", headers=H(world, "coach_a")).json()
    bob = next(p for p in sq["players"] if p["player_id"] == world["bob"])
    assert bob["weight_kg"] == 41.5 and len(bob["skinfolds"]) == 8 and sq["squad_mean_sit_reach"] == 24.5
    cats = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-categories?window=baseline", headers=H(world, "coach_a")).json()
    assert cats["players"]                                           # the extra measures never break the categories


def test_template_has_the_extra_columns_and_imports_them(client, world, db):
    sid = make_season(client, world)
    t = get_template(client, world, sid)
    ws = openpyxl.load_workbook(io.BytesIO(t.content))["Super Provincial"]
    head = [c.value for c in ws[1]]
    assert head == columns(SUPER) and trial_header(SIT_REACH, 1) in head and skinfold_header("Medial calf", 3) in head
    row = {"Cleared (Yes/No)": "Yes", "Test date (YYYY-MM-DD)": "2027-02-01", trial_header(BY_KEY["broad_jump"], 1): 180,
           trial_header(SIT_REACH, 1): 20, trial_header(SIT_REACH, 2): 22.5, skinfold_header("Triceps", 1): 6.4, skinfold_header("Triceps", 2): 6.4}
    data = fill(t.content, {world["bob"]: row})
    r = upload(client, world, data, sid, confirm=True)
    assert r.status_code == 200 and r.json()["saved"], r.text
    ex = client.get(f"/players/{world['bob']}/testing?season_id={sid}&window=baseline", headers=H(world, "coach_a")).json()["sessions"][0]["extras"]
    assert ex["sit_reach"]["final"] == 22.5 and ex["skinfolds"][0]["final"] == 6.4


def test_an_older_template_without_the_extra_columns_still_imports():
    wb = openpyxl.Workbook()
    ins = wb.active
    ins.title = "Instructions"
    ws = wb.create_sheet("Super Provincial")
    cols = columns(SUPER, extras=False)
    ws.append(cols)
    vals = {"Player ID": 1, "Player name": "Bob", "Cleared (Yes/No)": "Yes", "Test date (YYYY-MM-DD)": "2027-02-01",
            trial_header(BY_KEY["broad_jump"], 1): 180}
    ws.append([vals.get(c) for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    out = parse_workbook(buf.getvalue(), {1: "Bob"})
    assert not out["errors"] and out["rows"][0]["results"]["broad_jump"]["final"] == 180


def test_fitness_page_lists_every_result(client, world):
    sid = make_season(client, world)
    client.put(f"/players/{world['bob']}/tests/{sid}/baseline", headers=H(world, "sc_a"),
               json={"test_date": "2027-02-01", "results": {"sprint_20m": ["3.50", "3.41"], "sit_reach": ["18"], "sf_triceps": ["6.4"]}})
    d = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline", headers=H(world, "coach_a")).json()
    bob = next(r for r in d["players"] if r["player_id"] == world["bob"])
    assert bob["results"]["sprint_20m"] == "3.41" and bob["sit_reach"] == 18 and bob["skinfolds"]["sf_triceps"] == 6.4
    assert bob["level_label"] == "Super Provincial" and len(d["tests"]) == 8 and len(d["sites"]) == 8
    ann = next(r for r in d["players"] if r["player_id"] == world["ann"])
    assert ann["level"] is None and ann["results"] == {}
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline", headers=H(world, "physio_a")).status_code == 403


def test_fitness_page_has_bmi_trials_and_a_long_plank(client, world):
    sid = make_season(client, world)
    r = client.put(f"/players/{world['bob']}/tests/{sid}/baseline", headers=H(world, "sc_a"),
                   json={"height_cm": 170, "weight_kg": 46, "results": {"plank": ["605"], "sprint_20m": ["3.66", "3.52", "3.53"]}})
    assert r.status_code == 200, r.text                               # a 10:05 hold is accepted (limit 12:00)
    d = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline", headers=H(world, "coach_a")).json()
    bob = next(x for x in d["players"] if x["player_id"] == world["bob"])
    assert bob["bmi"] == 15.9 and bob["trials"]["sprint_20m"] == ["3.66", "3.52", "3.53"] and bob["results"]["plank"] == "605.00"


def test_fitness_report_has_references_past_tests_and_change(client, world):
    sid = make_season(client, world)
    put = lambda w, jump: client.put(f"/players/{world['bob']}/tests/{sid}/{w}", headers=H(world, "sc_a"),
                                     json={"test_date": "2027-02-01" if w == "baseline" else "2027-05-01", "results": {"broad_jump": [jump], "sprint_20m": ["3.50"]}})
    assert put("baseline", "180").status_code == 200 and put("mid_season", "196").status_code == 200
    d = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=mid_season", headers=H(world, "coach_a")).json()
    jump = next(t for t in d["tests"] if t["key"] == "broad_jump")
    assert jump["higher_is_better"] and jump["reference"]["expected_display"] == "185.00" and d["age_group"] == "U15"
    assert [(w["window"], w["current"], w["tested"]) for w in d["history"]] == [("baseline", False, 1), ("mid_season", True, 1)]
    assert d["history"][0]["means"]["broad_jump"]["display"] == "180.00"
    bob = next(x for x in d["players"] if x["player_id"] == world["bob"])
    assert bob["values"]["broad_jump"] == 196 and bob["age"]["broad_jump"] == "on_track"
    ch = bob["change"]["tests"]["broad_jump"]
    assert ch["state"] == "improved" and ch["from"] == "180.00" and bob["change"]["tests"]["sprint_20m"]["state"] == "same"
    base = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-results?window=baseline", headers=H(world, "coach_a")).json()
    assert next(x for x in base["players"] if x["player_id"] == world["bob"])["change"] is None     # nothing earlier to compare with
