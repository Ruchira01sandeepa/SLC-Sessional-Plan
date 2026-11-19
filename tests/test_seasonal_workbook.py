"""Load distribution, component distribution, session plans and the combined seasonal workbook."""
import io
from datetime import date

import openpyxl
import pytest

from app.annual_grid import COMP, GENERAL, PRECOMP, SEASON_PHASE_OF, SPECIAL, TRANS, build_grid
from app.component_distribution import COLUMNS, build_components
from app.exercise_kinds import PHASE_KINDS
from app.exercises import library
from app.load_distribution import BOWL_OVERS_CAP, MAX_BOWL_DAYS, REPS_MAX, REPS_MIN, SPELL_MAX, build_interval_loads, build_loads, split_spells
from app.season_phases import suggest_phases
from app.seasonal_workbook import SHEETS, build_seasonal_workbook, season_phases_of, session_sheet_name
from app.session_plans import DOSE, ROLE_LABEL, build_session
from app.workload_rules import DEFAULT_FAST_LIMITS

H = lambda w, who: w["h"][who]
ROLES = list(ROLE_LABEL)
PHASES = list(PHASE_KINDS)


def grid(start=date(2027, 1, 1), end=date(2027, 9, 30), matches=()):
    ev = [{"event_type": "match", "date": d, "hours": 6.0} for d in matches]
    return build_grid(squad_name="Western U15", season={"name": "2027", "start_date": start, "end_date": end},
                      phases=suggest_phases(start, end), events=ev, generated_on=date(2027, 1, 1))


# ───────────── load distribution ─────────────
def test_split_spells():
    assert split_spells(0) == [] and split_spells(5) == [5] and split_spells(6) == [3, 3] and split_spells(8) == [4, 4] and split_spells(7) == [4, 3]
    assert all(max(split_spells(o)) <= SPELL_MAX and sum(split_spells(o)) == o for o in range(1, 40))


@pytest.mark.parametrize("matches", [(), (date(2027, 6, 12),), (date(2027, 6, 12), date(2027, 6, 13), date(2027, 6, 14), date(2027, 6, 15))])
def test_bowling_plan_respects_limits(matches):
    g = grid(matches=matches)
    ld = build_loads(g)
    for w in range(g["weeks"]):
        k = g["kinds"][w]
        days, o = ld["bowl_days"][w], ld["overs_per_day"][w]
        assert days + ld["matches"][w] <= MAX_BOWL_DAYS or days == 0, w                 # a match is a bowling day
        if o:
            assert o <= BOWL_OVERS_CAP[k] and o < DEFAULT_FAST_LIMITS["caution_match_day_overs"]
            assert max(map(int, ld["spells"][w].split("+"))) <= DEFAULT_FAST_LIMITS["max_spell_overs"]
            assert sum(map(int, ld["spells"][w].split("+"))) == o
            assert ld["overs_per_week"][w] == days * o
        else:
            assert ld["spells"][w] is None and ld["overs_per_week"][w] is None
    assert all(ld["overs_per_day"][w] is None for w in range(g["weeks"]) if g["kinds"][w] == TRANS)      # no structured bowling in transition


def test_match_weeks_reduce_training_bowling_days():
    g = grid(matches=(date(2027, 6, 12), date(2027, 6, 13)))
    w = (date(2027, 6, 12) - date(2027, 1, 1)).days // 7
    assert g["match_counts"][w] == 2 and build_loads(g)["bowl_days"][w] == 1
    quiet = (date(2027, 6, 26) - date(2027, 1, 1)).days // 7
    assert build_loads(g)["bowl_days"][quiet] == 3


def test_running_loads_follow_phase_rules():
    g = grid()
    ld = build_loads(g)
    for w, k in enumerate(g["kinds"]):
        assert (ld["sprint_reps"][w] is not None) == (k in (PRECOMP, COMP))
        assert (ld["shuttle_reps"][w] is not None) == (k == PRECOMP)
        assert (ld["aerobic_min"][w] is not None) == (k in (GENERAL, SPECIAL, TRANS))
        assert (ld["effort"][w] is not None) == (k in (PRECOMP, COMP))
        if ld["sprint_reps"][w]:
            assert REPS_MIN <= ld["sprint_reps"][w] <= REPS_MAX and ld["metres"][w] == (ld["sprint_reps"][w] + (ld["shuttle_reps"][w] or 0) * 2) * 20
        if ld["effort"][w]:
            assert 0.8 <= ld["effort"][w] <= 0.9
        if ld["aerobic_min"][w]:
            assert 10 <= ld["aerobic_min"][w] <= 30
    assert ld["percentage"] == g["percentage"]


def test_running_kinds_are_allowed_in_the_phase():
    for kind, phases in {"speed": (PRECOMP, COMP), "repeat_sprint": (PRECOMP,), "aerobic": (GENERAL, SPECIAL, TRANS)}.items():
        for ph in phases:
            assert kind in PHASE_KINDS[SEASON_PHASE_OF[ph]], (kind, ph)


# ───────────── component distribution ─────────────
def test_components_cover_the_library_and_follow_phase_kinds():
    c = build_components(ROLES, {"fast", "spin"})
    lib = library()["groups"]
    sizes = {b["label"]: len(b["rows"]) for b in c["blocks"]}
    assert sizes == {"Spin bowling - Physical": len(lib["spin"]["physical"]), "Spin bowling - Skill": len(lib["spin"]["skill"]),
                     "Fast bowling - Physical": len(lib["fast"]["physical"]), "Fast bowling - Skill": len(lib["fast"]["skill"]),
                     "Batting (added drills) - Skill": len(lib["batting"]["skill"]), "Wicketkeeping (added drills) - Skill": len(lib["keeping"]["skill"]),
                     "Fielding and general - Physical": len(lib["fielding"]["physical"]), "Fielding and general - Skill": len(lib["fielding"]["skill"])}
    for b in c["blocks"]:
        for r in b["rows"]:
            assert r["marks"] == [r["kind"] in PHASE_KINDS[SEASON_PHASE_OF[p]] for p in COLUMNS]
            assert r["marks"][0] == r["marks"][1]                                   # pre-season is under both preparation columns
    assert all(not r["marks"][4] for b in c["blocks"] for r in b["rows"] if r["kind"] in ("leg_strength", "plyometric_power", "variation", "match_prep"))


def test_components_only_include_the_lists_the_roles_need():
    assert [b["label"] for b in build_components(["batter"])["blocks"]] == ["Batting (added drills) - Skill", "Fielding and general - Physical", "Fielding and general - Skill"]
    assert any(b["label"].startswith("Wicketkeeping") for b in build_components(["bat_wicketkeeper"])["blocks"])
    labels = [b["label"] for b in build_components(["spin_bowler"])["blocks"]]
    assert labels[0].startswith("Spin") and not any(l.startswith("Fast") for l in labels)


# ───────────── session plans ─────────────
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("phase", PHASES)
def test_every_session_is_60_minutes_and_phase_safe(role, phase):
    s = build_session(role, phase)
    assert s["minutes"] == 60 and [p["minutes"] for p in s["parts"]] == [10, 15, 10, 15, 5, 5]
    for p in s["parts"]:
        assert p["items"], (role, phase, p["name"])
        for it in p["items"]:
            if it["kind"]:
                assert it["kind"] in PHASE_KINDS[phase], (role, phase, it["desc"], it["kind"])      # nothing the plan does not allow in the phase
    names = [it["desc"] for p in s["parts"] for it in p["items"]]
    assert len(names) == len(set(names))                                                           # no exercise twice in one session
    assert s["title"].startswith("SESSION PLAN FOR") and PHASE_KINDS and s["header"][0][0] == "TOPIC" and len(s["header"]) == 8


def test_transition_has_no_strength_power_or_bowling():
    banned = {"leg_strength", "upper_strength", "plyometric_power", "rotation_power", "speed", "repeat_sprint", "variation", "tactical", "match_prep", "foundation"}
    for role in ROLES:
        kinds = {it["kind"] for p in build_session(role, "transition")["parts"] for it in p["items"]}
        assert not (kinds & banned), (role, kinds & banned)


def test_doses_are_conservative():
    for kind, (t, rep, sets, rest) in DOSE.items():
        assert "%" not in (t + rep + sets) or "effort" in t, kind                                  # no percentage-of-maximum loading
        top = int(sets.split("-")[-1])
        assert top <= 3, kind
    s = build_session("fast_bowler", "pre_season")
    for p in s["parts"]:
        for it in p["items"]:
            assert "1RM" not in it["desc"] and "max weight" not in (it["time"] + it["rest"])
            if "nordic" in it["desc"].lower():
                assert it["rep"] == "3-5" and it["set"] == "2"
    assert "max weight" not in " ".join(v for _, v in s["header"]).lower() and "Body weight or light bands" in dict(s["header"])["TRAINING UNIT"]
    assert build_session("fast_bowler", "in_season")["parts"][1]["items"][0]["set"] == "2"          # maintenance volume in season


def test_roles_without_own_lists_get_coach_rows_and_notes():
    from app.exercises import library
    batting = {e["name"] for e in library()["groups"]["batting"]["skill"]}
    keeping = {e["name"] for e in library()["groups"]["keeping"]["skill"]}
    s = build_session("batter", "pre_season")
    role_items = [it["desc"] for it in s["parts"][3]["items"]]
    assert any(d in batting for d in role_items) and not any("Coach to add batting" in d for d in role_items)     # real batting drills now
    assert any("ADDED" in n for n in s["notes"]) and any("general strength exercises" in n for n in s["notes"])
    wk = [it["desc"] for it in build_session("bat_wicketkeeper", "pre_competition")["parts"][3]["items"]]
    assert any(d in keeping for d in wk) and any(d in batting for d in wk)                          # a keeper gets both
    assert [it["desc"] for it in build_session("batter", "transition")["parts"][3]["items"]] == ["Batting video review"]
    with pytest.raises(ValueError):
        build_session("batter", "winter")


def test_bowlers_get_bowling_skill_work_in_season():
    fast = build_session("fast_bowler", "in_season")["parts"][3]["items"]
    assert any("bowling" in it["desc"].lower() or "yorker" in it["desc"].lower() or "slower" in it["desc"].lower() for it in fast)


# ───────────── workbook ─────────────
def test_workbook_sheets():
    """Exactly the supplied workbook: four sheets in its order, one column per week."""
    g = grid()
    wb = openpyxl.load_workbook(io.BytesIO(build_seasonal_workbook(g, ROLES)))
    assert wb.sheetnames == SHEETS == ["Annual plan", "Load distribution", "Component distribution", "Session plan"]
    a = wb["Annual plan"]
    assert a.max_column == g["weeks"] + 1 and a["A6"].value == "Mesos" and a["A7"].value == "Macros" and a["A60"].value == "Performance index"
    assert a.max_row == 60                                              # ends at Performance index, as the supplied sheet does
    ws = wb["Session plan"]
    assert ws["A2"].value == "SESSION PLAN FOR LOWER BODY" and "A2:G3" in {str(m) for m in ws.merged_cells.ranges}
    assert [ws.cell(row=r, column=1).value for r in range(7, 15)] == ["TOPIC", "PERIOD", "STAGE", "MESO", "MICRO", "EQUIPMENTS", "DURATION", "TRAINING UNIT"]
    assert [ws[c].value for c in ("A15", "B15", "C15", "F15", "G15", "C16", "D16", "E16")] == ["PART", "DESCRIPTION", "DOSIFICATION", "ORGANIZATION", "REST", "TIME", "REP", "SET"]
    assert {"C15:E15", "A15:A16", "F15:F16"} <= {str(m) for m in ws.merged_cells.ranges}
    col_a = [ws.cell(row=r, column=1).value for r in range(17, ws.max_row + 1)]
    assert [x for x in col_a if x] == ["INITIAL PART", "MAIN PART", "FINAL PART"]
    desc = [ws.cell(row=r, column=2).value for r in range(17, ws.max_row + 1)]
    for x in ("WARM UP", "Stretch", "Neck Stretch(R/L)", "Hypertrophy program", "Back Squat", "MACRO REST 3 MIN", "Crunches", "Left Plank", "WARM DOWN", "Ice bath"):
        assert x in desc, x
    assert desc.index("Stretch") < desc.index("Hypertrophy program") < desc.index("Crunches") < desc.index("WARM DOWN")
    squat = 17 + desc.index("Back Squat")
    assert [ws.cell(row=squat, column=c).value for c in (4, 5)] == ["12,10,10,8,8", "5"]
    load = wb["Load distribution"]
    assert [load.cell(row=r, column=1).value for r in (10, 12, 13, 15, 17, 19, 22)] == [
        "Session(Percentage)", "100m", "Anaerobic endurance(speed)", "Interval run 120m", "Interval run 150m", "Interval run 300m", "Total meter"]
    assert load.max_column == g["weeks"] + 1 and load["B9"].value == 1                     # week by week
    assert load["B10"].value == "='Annual plan'!B10"                     # one load row: the two sheets cannot disagree
    totals = [c for c in load[22][1:] if c.value is not None]
    assert totals and all(str(c.value).startswith("=N(") for c in totals)  # Total meter is a formula, not a typed sum
    for c in totals:
        runs = [load[f"{c.column_letter}{r}"] for r in (15, 17, 19) if load[f"{c.column_letter}{r}"].value is not None]
        assert runs and all(isinstance(x.value, int) and x.number_format.endswith('m*"0') for x in runs)   # numbers shown as 120m*8
    comp = wb["Component distribution"]
    assert [comp.cell(row=1, column=c).value for c in range(1, 8)] == ["Quality", "Method", "General", "Special", "Precompetition", "Competition", "Transition"]
    assert "ComponentDistribution" in comp.tables
    rows = {r[1]: r for r in comp.iter_rows(min_row=2, values_only=True) if r[1]}
    assert rows["Continue slow run"][2:] == ("x", None, None, None, "x") and rows["400m interval"][2:] == ("x", "x", "x", None, None)
    assert rows["Speed games"][2:] == (None,) * 5 and rows["120m"][2:] == ("x", "x", "x", None, None)


def test_running_block_follows_the_phases():
    g = grid()
    k, n = g["kinds"], g["weeks"]
    ld = build_interval_loads(g)
    gen = [w for w in range(n) if k[w] == GENERAL]
    on = [w for w in range(n) if ld["total"][w]]
    assert on[0] == gen[-2] and not any(k[w] == TRANS for w in on)                     # last 2 general weeks to competition
    assert not any(ld["runs"][300][w] for w in range(n) if k[w] == COMP)                 # no 300 m in competition
    assert ld["speed_100m"][gen[-1]] == 0.80 and max(v or 0 for v in ld["speed_100m"]) == 1.0
    spec = [ld["total"][w] for w in range(n) if k[w] == SPECIAL]
    comp = [ld["total"][w] for w in range(n) if k[w] == COMP]
    assert max(spec) > max(comp)                                                          # volume falls toward competition


def test_sheet_names_are_unique_even_when_clashing():
    used = set()
    assert [session_sheet_name("fast_bowler", "pre_season", used) for _ in range(3)] == ["Fast Pre-season", "Fast Pre-season 2", "Fast Pre-season 3"]


def test_exercise_text_is_never_a_formula():
    import re
    wb = openpyxl.load_workbook(io.BytesIO(build_seasonal_workbook(grid(), ["fast_bowler"])))
    # the only formulas are the load sheet's own arithmetic (linked % row, total metres), in fixed shapes
    allowed = {10: r"='Annual plan'!([A-Z]+)10", 22: r"=N\([A-Z]+15\)\*120\+N\([A-Z]+17\)\*150\+N\([A-Z]+19\)\*300"}
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    if ws.title == "Load distribution" and c.row in allowed and c.column > 1 and c.data_type == "f":
                        assert re.fullmatch(allowed[c.row], c.value), (c.coordinate, c.value)
                        continue
                    assert c.data_type == "s", (ws.title, c.coordinate)


# ───────────── API ─────────────
def make_season(client, w, **kw):
    body = {"name": "2027", "start_date": "2027-01-01", "end_date": "2027-09-30", "phases": []}
    body.update(kw)
    return client.post(f"/squads/{w['squad_a']}/seasons", json=body, headers=H(w, "admin")).json()["id"]


def test_endpoint_uses_squad_roles(client, world):
    sid = make_season(client, world)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx", headers=H(world, "coach_a"))
    assert r.status_code == 200 and "seasonal-plan-workbook-Western-U15-2027.xlsx" in r.headers["content-disposition"]
    assert openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames == SHEETS
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx?roles=batter,all_rounder", headers=H(world, "admin"))
    assert r.status_code == 200 and openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames == SHEETS
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx?roles=captain", headers=H(world, "admin")).status_code == 422


def test_endpoint_access_and_errors(client, world):
    sid = make_season(client, world)
    url = f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx"
    for who in ("admin", "coach_a", "sc_a", "physio_a"):
        assert client.get(url, headers=H(world, who)).status_code == 200, who
    for who in ("coach_b", "ann_login"):
        assert client.get(url, headers=H(world, who)).status_code in (403, 404), who
    assert client.get(url).status_code == 401
    short = make_season(client, world, name="short", start_date="2028-01-01", end_date="2028-01-20")
    r = client.get(f"/squads/{world['squad_a']}/seasons/{short}/seasonal-workbook.xlsx", headers=H(world, "admin"))
    assert r.status_code == 200                                  # short seasons (tournaments) are supported


def test_endpoint_includes_calendar_matches_and_no_medical_text(client, world, db):
    from app.models import PlayerMedical
    db.add(PlayerMedical(player_id=world["bob"], current_health={"note": "SECRET-LUMBAR-STRESS"}))
    db.commit()
    sid = make_season(client, world)
    for d in ("2027-06-12", "2027-06-13"):
        assert client.post(f"/squads/{world['squad_a']}/events", json={"event_type": "match", "title": "Match", "start_at": f"{d}T09:00:00+05:30", "end_at": f"{d}T16:00:00+05:30"}, headers=H(world, "admin")).status_code in (200, 201)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/seasonal-workbook.xlsx", headers=H(world, "coach_a"))
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    w = (date(2027, 6, 12) - date(2027, 1, 1)).days // 7            # week by week: one column per week
    assert wb["Annual plan"].cell(row=12, column=w + 2).value == "*"
    text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    assert "SECRET" not in text
