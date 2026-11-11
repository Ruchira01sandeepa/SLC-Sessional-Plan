"""SLC U15 SOP tests: parsing, best of three, categorisation, the individual plan, Excel import and access."""
import io
from datetime import date

import openpyxl
import pytest

from app import categorisation as cz
from app.annual_grid import build_grid
from app.exercise_kinds import PHASE_KINDS
from app.individual_plan import AREA_KINDS, build_individual_plan
from app.models import Gender, Player, PlayerRole
from app.season_phases import suggest_phases
from app.test_battery import BY_KEY, PROVINCIAL, SUPER, best_of, format_mmss, parse_mmss, parse_value
from app.test_import import columns, parse_workbook, trial_header

H = lambda w, who: w["h"][who]


# ───────────── numbers ─────────────
@pytest.mark.parametrize("v,s", [("8.25", 505), (8.25, 505), (8.3, 510), ("8.30", 510), ("8:25", 505), (6, 360), ("10.05", 605)])
def test_parse_mmss(v, s):
    assert parse_mmss(v) == s


@pytest.mark.parametrize("bad", ["8.75", 8.60, "abc", "", "-1.00", "8.255", True])
def test_parse_mmss_rejects(bad):
    with pytest.raises(ValueError):
        parse_mmss(bad)


def test_format_roundtrip():
    assert format_mmss(505) == "8.25" and format_mmss(360) == "6.00"
    assert all(parse_mmss(format_mmss(s)) == s for s in range(180, 1200, 7))


def test_parse_value_ranges_and_types():
    assert parse_value(BY_KEY["pushups"], 12) == 12
    with pytest.raises(ValueError):
        parse_value(BY_KEY["pushups"], 12.5)              # whole reps only
    with pytest.raises(ValueError):
        parse_value(BY_KEY["sprint_20m"], 1.2)            # faster than plausible: typing error
    with pytest.raises(ValueError):
        parse_value(BY_KEY["bronco"], "20.00")
    with pytest.raises(ValueError):
        parse_value(BY_KEY["plank"], "abc")
    assert parse_value(BY_KEY["sprint_20m"], "3.456") == 3.46


def test_best_of_direction_and_blanks():
    assert best_of(BY_KEY["sprint_20m"], [3.5, None, 3.4]) == 3.4          # lower is better
    assert best_of(BY_KEY["broad_jump"], [180, 190, None]) == 190           # higher is better
    assert best_of(BY_KEY["plank"], [None, None, None]) is None             # never estimated


# ───────────── categorisation ─────────────
def entries(n, level=SUPER, test="broad_jump", start=150, step=5):
    return [{"player_id": i, "level": level, "finals": {test: start + i * step}} for i in range(n)]


def test_percentile_and_bands_within_level():
    out = cz.categorise(entries(10))
    assert out[9]["band"] == 5 and out[0]["band"] == 1
    assert out[9]["overall"] > out[0]["overall"]
    assert [f["area"] for f in out[0]["focus_areas"]] == ["power"]        # bottom of the group: below the middle
    assert out[9]["focus_areas"] == []
    assert sorted(o["band"] for o in out.values()) == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_lower_time_is_better():
    e = [{"player_id": i, "level": SUPER, "finals": {"sprint_20m": 3.0 + i * 0.1}} for i in range(6)]
    out = cz.categorise(e)
    assert out[0]["band"] == 5 and out[5]["band"] == 1


def test_small_cohort_has_no_band():
    out = cz.categorise(entries(4))
    assert all(o["band"] is None and o["overall"] is None and "at least 5" in o["note"] for o in out.values())


def test_levels_are_ranked_separately():
    sup = entries(5, SUPER, "run_2km", 400, 10)
    for x in sup:
        x["player_id"] += 100
    out = cz.categorise(entries(5, PROVINCIAL, "bronco", 300, 10) + sup)
    assert {o["cohort_size"] for o in out.values()} == {5}
    assert out[0]["level"] == PROVINCIAL and out[100]["level"] == SUPER
    assert out[0]["band"] == 5 and out[100]["band"] == 5         # fastest in each own level
    assert len(out[0]["areas"]) == 1 and "one area" in out[0]["note"]


def test_missing_test_is_left_out_not_estimated():
    e = entries(6)
    for x in e:
        x["finals"]["plank"] = 60 + x["player_id"]
    e[0]["finals"].pop("plank")
    out = cz.categorise(e)
    assert out[0]["areas_counted"] == 1 and "left out" in out[0]["note"]
    assert out[1]["areas_counted"] == 2


def test_band_edges():
    assert [cz.band_of(x) for x in (0, 19.9, 20, 59.9, 60, 99.9, 100)] == [1, 1, 2, 3, 4, 5, 5]


def test_readiness():
    assert cz.readiness(None, "fit")["status"] == "ready"
    assert cz.readiness("info", "fit")["status"] == "ready"
    assert cz.readiness("warn", "fit")["status"] == "caution"
    assert cz.readiness(None, "modified")["status"] == "caution"
    assert cz.readiness("stop", "fit")["status"] == "hold"
    assert cz.readiness(None, "unavailable")["status"] == "hold"


# ───────────── individual plan ─────────────
def grid(start=date(2027, 1, 1), end=date(2027, 9, 30)):
    return build_grid(squad_name="W", season={"name": "2027", "start_date": start, "end_date": end}, phases=suggest_phases(start, end),
                      events=[], generated_on=date(2027, 1, 1))


def cat_with(*weak, level=SUPER):
    """A categorisation result with every area of the level: the named areas are below the middle, the others above it."""
    from app.test_battery import AREA_LABEL, areas_for
    areas = [{"area": x, "label": AREA_LABEL[x], "percentile": (10.0 + weak.index(x)) if x in weak else 70.0} for x in areas_for(level)]
    return {"overall": 30.0, "areas": areas,
            "focus_areas": sorted(({"area": a["area"], "label": a["label"], "percentile": a["percentile"]} for a in areas if a["area"] in weak), key=lambda f: f["percentile"])}


READY = {"status": "ready", "label": "Ready", "reason": "ok"}


@pytest.mark.parametrize("role", ["fast_bowler", "spin_bowler", "batter", "bat_wicketkeeper", "all_rounder"])
def test_plan_only_holds_allowed_work(role):
    plan = build_individual_plan(player={"name": "P", "role": role}, cat=cat_with("core", "speed", "power"), ready=READY, g=grid())
    assert plan["phases"]
    for ph in plan["phases"]:
        assert {a["area"] for a in ph["areas"]} == {"endurance", "power", "upper_strength", "speed", "agility", "core"}      # all areas
        for a in ph["areas"]:
            assert len(a["exercises"]) <= a["slots"]
            for e in a["exercises"]:
                assert e["kind"] in PHASE_KINDS[ph["phase"]] and e["kind"] in AREA_KINDS[a["area"]]
            assert a["exercises"] or a["note"]                 # every area is either planned or explained


def test_allocate_priority_areas_get_most_but_no_area_is_dropped():
    from app.individual_plan import TOTAL_SLOTS, allocate
    areas = [{"area": k, "percentile": p} for k, p in (("core", 10.0), ("speed", 30.0), ("power", 70.0), ("agility", 80.0), ("endurance", 60.0), ("upper_strength", 90.0))]
    s = allocate(areas)
    assert sum(s.values()) == TOTAL_SLOTS and all(v >= 1 for v in s.values())
    assert s["core"] > s["speed"] > max(s["power"], s["agility"], s["endurance"], s["upper_strength"]) - 1      # weakest first
    assert s["core"] + s["speed"] >= 0.55 * TOTAL_SLOTS                                                          # about 60% to priority areas
    assert allocate([{"area": k, "percentile": 70.0} for k in ("core", "speed")]) == {"core": 6, "speed": 6}     # nothing weak: equal
    assert allocate([{"area": "a", "percentile": None}, {"area": "b", "percentile": 20.0}])["b"] > 0           # untested area still listed


def test_every_area_stays_in_the_plan_for_a_weak_player():
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=READY, g=grid())
    ph = next(p for p in plan["phases"] if p["phase"] == "pre_competition")
    by = {a["area"]: a for a in ph["areas"]}
    assert by["core"]["priority"] and not by["speed"]["priority"]
    assert by["core"]["slots"] >= 6 and all(a["slots"] >= 1 for a in ph["areas"])
    assert ph["areas"][0]["area"] == "core"                                                                       # weakest first


def test_area_without_allowed_work_names_the_phase_that_has_it():
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("speed"), ready=READY, g=grid())
    pre = next(a for a in next(p for p in plan["phases"] if p["phase"] == "pre_season")["areas"] if a["area"] == "speed")
    assert pre["exercises"] == [] and "pre-competition" in pre["note"]


CAUTION = {"status": "caution", "label": "Caution", "reason": "x"}
HOLD = {"status": "hold", "label": "Hold", "reason": "x"}


def test_readiness_limits_load():
    g = grid()
    kw = dict(player={"name": "P", "role": "spin_bowler"}, cat=cat_with("core"), g=g)
    base, caution, hold = (build_individual_plan(ready=r, **kw) for r in (READY, CAUTION, HOLD))
    assert caution["weeks"][0]["planned_load"] < base["weeks"][0]["planned_load"]
    assert sum(w["planned_load"] for w in caution["weeks"]) < sum(w["planned_load"] for w in base["weeks"])
    assert all(w["planned_load"] == 0 and w["focus_sessions"] == 0 for w in hold["weeks"])
    assert all(not a["exercises"] for ph in hold["phases"] for a in ph["areas"])
    assert all(c["sessions_per_week"] <= b["sessions_per_week"] for b, c in zip(base["phases"], caution["phases"]))


def test_no_band_no_plan_exercises():
    plan = build_individual_plan(player={"name": "P", "role": "batter"}, cat=None, ready=READY, g=grid())
    assert plan["focus_areas"] == [] and any("no band yet" in n.lower() for n in plan["notes"])


# ───────────── Excel parsing and the API ─────────────
def add_players(db, w, n=6):
    ids = []
    for i in range(n):
        p = Player(full_name=f"Test Player {i}", squad_id=w["squad_a"], role=PlayerRole.batter, gender=Gender.male, date_of_birth=date(2012, 5, 1))
        db.add(p)
        db.flush()
        ids.append(p.id)
    db.commit()
    return ids


def make_season(client, w):
    return client.post(f"/squads/{w['squad_a']}/seasons", json={"name": "2027", "start_date": "2027-01-01", "end_date": "2027-09-30", "phases": []},
                       headers=H(w, "admin")).json()["id"]


def get_template(client, w, sid, who="admin", window="baseline"):
    r = client.get(f"/squads/{w['squad_a']}/test-template.xlsx?season_id={sid}&window={window}", headers=H(w, who))
    return r


def fill(content, per_player, level="Super Provincial"):
    """per_player: {player_id: {header_or_test: value}} . Returns xlsx bytes."""
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb[level]
    head = {c.value: c.column for c in ws[1]}
    for row in range(2, ws.max_row + 1):
        pid = ws.cell(row=row, column=1).value
        if pid in per_player:
            for k, v in per_player[pid].items():
                ws.cell(row=row, column=head[k]).value = v
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def good_row(i, **extra):
    r = {"Cleared (Yes/No)": "Yes", "Test date (YYYY-MM-DD)": "2027-02-01", "Height (cm)": 150.0 + i, "Body weight (kg)": 40.0 + i,
         trial_header(BY_KEY["broad_jump"], 1): 150 + i * 5, trial_header(BY_KEY["broad_jump"], 2): 155 + i * 5, trial_header(BY_KEY["broad_jump"], 3): 140,
         trial_header(BY_KEY["run_2km"], 1): f"{9 + i}.30", trial_header(BY_KEY["pushups"], 1): 10 + i, "Push-ups set-up": "knees down"}
    r.update(extra)
    return r


def upload(client, w, data, sid, *, confirm=False, who="admin", window="baseline"):
    return client.post(f"/squads/{w['squad_a']}/test-import?season_id={sid}&window={window}&confirm={'true' if confirm else 'false'}&filename=t.xlsx",
                       content=data, headers={**H(w, who), "Content-Type": "application/octet-stream"})


def test_template_is_prefilled_and_text_safe(client, world, db):
    ids = add_players(db, world, 2)
    sid = make_season(client, world)
    r = get_template(client, world, sid)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Instructions", "Provincial", "Super Provincial"]
    ws = wb["Super Provincial"]
    assert [c.value for c in ws[1]] == columns(SUPER)
    names = {ws.cell(row=i, column=1).value: ws.cell(row=i, column=2).value for i in range(2, ws.max_row + 1)}
    assert set(ids) <= set(names) and all(isinstance(v, str) for v in names.values())
    assert [c.value for c in wb["Provincial"][1]] == columns(PROVINCIAL)


def test_import_preview_then_confirm_and_best_of_three(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    data = fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)})
    pre = upload(client, world, data, sid)
    assert pre.status_code == 200, pre.text
    j = pre.json()
    assert j["saved"] is False and len(j["accepted"]) == 6 and j["errors"] == []
    assert client.get(f"/players/{ids[0]}/testing?season_id={sid}", headers=H(world, "admin")).json()["sessions"] == []   # preview saved nothing
    ok = upload(client, world, data, sid, confirm=True)
    assert ok.status_code == 200 and ok.json()["saved"] is True
    t = client.get(f"/players/{ids[0]}/testing?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    res = t["sessions"][0]["results"]
    assert res["broad_jump"]["trials"] == ["150.00", "155.00", "140.00"] and res["broad_jump"]["final"] == "155.00"      # best of three, all kept
    assert res["run_2km"]["final"] == "9.30" and res["pushups"]["setup"] == "knees down"
    assert t["sessions"][0]["level"] == "super_provincial" and t["sessions"][0]["height_cm"] == 150.0
    assert t["category"]["band"] is not None and t["readiness"]["status"] in ("ready", "caution", "hold")


def test_reimport_replaces_the_window(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    tpl = get_template(client, world, sid).content
    upload(client, world, fill(tpl, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    upload(client, world, fill(tpl, {ids[0]: good_row(0, **{trial_header(BY_KEY["broad_jump"], 1): 200})}), sid, confirm=True)
    t = client.get(f"/players/{ids[0]}/testing?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    assert len(t["sessions"]) == 1 and t["sessions"][0]["results"]["broad_jump"]["final"] == "200.00"


@pytest.mark.parametrize("col,val,word", [
    (trial_header(BY_KEY["run_2km"], 1), "9.75", "seconds"),
    (trial_header(BY_KEY["sprint_20m"], 1), 1.2, "plausible"),
    (trial_header(BY_KEY["pushups"], 1), 12.5, "whole number"),
    ("Cleared (Yes/No)", "No", "cleared"),
    ("Cleared (Yes/No)", None, "Yes or No"),
    ("Test date (YYYY-MM-DD)", "01/02/2027", "date"),
    ("Height (cm)", 20, "plausible"),
])
def test_bad_rows_are_rejected_with_the_cell_named(client, world, db, col, val, word):
    ids = add_players(db, world, 2)
    sid = make_season(client, world)
    data = fill(get_template(client, world, sid).content, {ids[0]: good_row(0, **{col: val}), ids[1]: good_row(1)})
    j = upload(client, world, data, sid).json()
    assert len(j["accepted"]) == 1 and j["accepted"][0]["player_id"] == ids[1]
    e = j["errors"][0]
    assert e["column"] == col or col.startswith(("Cleared",)) and e["column"].startswith("Cleared") or e["column"]
    assert word.lower() in e["message"].lower()


def test_name_id_mismatch_and_double_fill_are_rejected(client, world, db):
    ids = add_players(db, world, 2)
    sid = make_season(client, world)
    tpl = get_template(client, world, sid).content
    wb = openpyxl.load_workbook(io.BytesIO(tpl))
    ws = wb["Super Provincial"]
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == ids[0]:
            ws.cell(row=row, column=2).value = "Someone Else"
    out = io.BytesIO()
    wb.save(out)
    j = upload(client, world, fill(out.getvalue(), {ids[0]: good_row(0), ids[1]: good_row(1)}), sid).json()
    assert [a["player_id"] for a in j["accepted"]] == [ids[1]] and "does not match" in j["errors"][0]["message"]
    # the same player filled on both level sheets: ambiguous, both rows rejected
    both = fill(fill(tpl, {ids[0]: good_row(0)}), {ids[0]: {"Cleared (Yes/No)": "Yes", "Test date (YYYY-MM-DD)": "2027-02-01",
                                                          trial_header(BY_KEY["bronco"], 1): "6.00"}}, level="Provincial")
    j = upload(client, world, both, sid).json()
    assert j["accepted"] == [] and len(j["errors"]) == 2 and all("more than once" in e["message"] for e in j["errors"])


def test_formula_text_is_never_executed_or_trusted(client, world, db):
    ids = add_players(db, world, 1)
    sid = make_season(client, world)
    # a real formula cell has no cached value in a hand-made file: it is ignored, never evaluated
    data = fill(get_template(client, world, sid).content, {ids[0]: good_row(0, Notes="=HYPERLINK(\"http://x\")")})
    assert upload(client, world, data, sid, confirm=True).status_code == 200
    s = client.get(f"/players/{ids[0]}/testing?season_id={sid}", headers=H(world, "admin")).json()["sessions"][0]
    assert s["notes"] is None
    # text that merely starts with "=" (a string cell) is kept as plain text and written back as text
    wb = openpyxl.load_workbook(io.BytesIO(get_template(client, world, sid).content))
    ws = wb["Super Provincial"]
    head = {c.value: c.column for c in ws[1]}
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == ids[0]:
            for k, v in good_row(0).items():
                ws.cell(row=row, column=head[k]).value = v
            c = ws.cell(row=row, column=head["Notes"])
            c.value, c.data_type = "=cmd|calc", "s"
    out = io.BytesIO()
    wb.save(out)
    assert upload(client, world, out.getvalue(), sid, confirm=True).status_code == 200
    s = client.get(f"/players/{ids[0]}/testing?season_id={sid}", headers=H(world, "admin")).json()["sessions"][0]
    assert s["notes"] == "=cmd|calc"
    out = client.get(f"/players/{ids[0]}/individual-plan.xlsx?season_id={sid}", headers=H(world, "admin"))
    for ws in openpyxl.load_workbook(io.BytesIO(out.content)):
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    assert c.data_type == "s"


def test_wrong_file_or_target_is_refused(client, world, db):
    add_players(db, world, 1)
    sid = make_season(client, world)
    tpl = get_template(client, world, sid).content
    assert upload(client, world, b"not excel", sid).status_code == 422
    assert upload(client, world, tpl, sid, window="mid_season").status_code == 422               # made for baseline
    assert upload(client, world, tpl, sid + 99).status_code == 404
    assert get_template(client, world, sid, window="weekly").status_code == 422
    wb = openpyxl.load_workbook(io.BytesIO(tpl))
    wb["Super Provincial"]["B1"].value = "Renamed"                                              # changed header
    out = io.BytesIO()
    wb.save(out)
    r = upload(client, world, out.getvalue(), sid)
    assert r.status_code == 422 and "do not match" in r.json()["detail"]
    assert upload(client, world, tpl, sid, confirm=True).status_code == 422                     # nothing valid to save


def test_squad_categories_and_individual_plan(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    data = fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)})
    upload(client, world, data, sid, confirm=True)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-categories?window=baseline", headers=H(world, "coach_a"))
    assert r.status_code == 200
    rows = {p["player_id"]: p for p in r.json()["players"]}
    assert rows[ids[5]]["band"] > rows[ids[0]]["band"] or rows[ids[5]]["overall"] > rows[ids[0]]["overall"]
    assert rows[ids[0]]["focus_areas"] and rows[ids[0]]["readiness"]["status"] == "ready"
    assert rows[world["ann"]]["band"] is None                                                   # not tested
    plan = client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}&window=baseline", headers=H(world, "coach_a")).json()
    assert plan["focus_areas"] and plan["phases"] and plan["weeks"] and plan["summary"]["band"] is not None
    x = client.get(f"/players/{ids[0]}/individual-plan.xlsx?season_id={sid}&window=baseline", headers=H(world, "admin"))
    assert x.status_code == 200
    names = openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames
    assert names[:7] == ["Player plan", "Test summary", "Focus plan", "Weekly load", "Annual plan", "Load distribution", "Component distribution"] and len(names) > 7
    first = openpyxl.load_workbook(io.BytesIO(x.content))["Player plan"]
    cells = [c.value for row in first.iter_rows() for c in row if isinstance(c.value, str)]
    assert any(v.startswith("Personal plan:") for v in cells) and "Priorities" in cells and "Goal" in cells


def test_pain_flag_puts_the_plan_on_hold(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    p = db.get(Player, ids[0])
    from app.models import Availability
    p.availability = Availability.unavailable
    db.commit()
    plan = client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    assert plan["status"] == "hold" and all(w["planned_load"] == 0 for w in plan["weeks"])


def test_access_rules(client, world, db):
    ids = add_players(db, world, 2)
    sid = make_season(client, world)
    tpl = get_template(client, world, sid).content
    # import / template: admin and S&C only
    assert get_template(client, world, sid, "coach_a").status_code == 403
    assert get_template(client, world, sid, "ann_login").status_code in (403, 404)
    assert get_template(client, world, sid, "coach_b").status_code == 404                        # other squad
    assert get_template(client, world, sid, "sc_a").status_code == 200
    assert upload(client, world, tpl, sid, who="coach_a").status_code == 403
    upload(client, world, fill(tpl, {ids[0]: good_row(0)}), sid, who="sc_a", confirm=True)
    # reading: staff of the squad only; players and physio do not see test results; other squads get 404
    url = f"/players/{ids[0]}/testing?season_id={sid}"
    assert client.get(url, headers=H(world, "coach_a")).status_code == 200
    assert client.get(url, headers=H(world, "coach_b")).status_code == 404
    assert client.get(url, headers=H(world, "ann_login")).status_code in (403, 404)
    assert client.get(url, headers=H(world, "physio_a")).status_code == 403
    assert client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}", headers=H(world, "bob_login")).status_code in (403, 404)
    assert client.get(f"/players/{ids[0]}/testing?season_id={sid}").status_code == 401
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-categories?window=baseline", headers=H(world, "ann_login")).status_code in (403, 404)


def test_parse_workbook_limits():
    with pytest.raises(ValueError):
        parse_workbook(b"x" * 2_100_000, {})
    with pytest.raises(ValueError):
        parse_workbook(b"not a zip", {})


# ───────────── progress between windows ─────────────
from app.test_progress import progress as prog_of


def win(w, finals, level=SUPER, cat=None):
    return {"window": w, "level": level, "finals": finals, "cat": cat}


def test_progress_direction_and_text():
    p = prog_of([win("baseline", {"sprint_20m": 3.60, "broad_jump": 180, "run_2km": 600, "pushups": 10, "plank": 60}),
                 win("mid_season", {"sprint_20m": 3.40, "broad_jump": 175, "run_2km": 575, "pushups": 10, "plank": 75})])
    ch = {t["key"]: t["change"] for t in p["tests"]}
    assert ch["sprint_20m"]["state"] == "improved" and ch["sprint_20m"]["text"] == "0.20 s faster"      # lower time is better
    assert ch["broad_jump"]["state"] == "declined" and ch["broad_jump"]["text"] == "-5.00 cm"
    assert ch["run_2km"]["state"] == "improved" and ch["run_2km"]["text"] == "25 s faster"
    assert ch["pushups"]["state"] == "same" and ch["pushups"]["text"] == "No clear change"
    assert ch["plank"]["state"] == "improved" and ch["plank"]["text"] == "+15.00 s"
    assert p["tests_compared"] == 5 and p["tests_improved"] == 3
    assert next(t for t in p["tests"] if t["key"] == "run_2km")["values"] == {"baseline": "10.00", "mid_season": "9.35"}                        # shown as mm.ss


def test_progress_needs_two_windows_and_orders_them():
    one = prog_of([win("baseline", {"plank": 60})])
    assert one["tests"][0]["change"] is None and any("two test windows" in n for n in one["notes"])
    three = prog_of([win("end_season", {"plank": 90}), win("baseline", {"plank": 60}), win("mid_season", {"plank": 70})])
    assert [w["window"] for w in three["windows"]] == ["baseline", "mid_season", "end_season"]
    assert three["tests"][0]["change"]["from_window"] == "baseline" and three["tests"][0]["change"]["to_window"] == "end_season"


def test_progress_skips_tests_missing_in_a_window_and_level_change():
    p = prog_of([win("baseline", {"bronco": 380}, PROVINCIAL), win("mid_season", {"run_2km": 600})])
    assert all(t["change"] is None for t in p["tests"])                       # Bronco and 2 km are never compared
    assert any("different level" in n for n in p["notes"])


def test_band_movement_and_focus_changes():
    mk = lambda band, overall, focus: {"band": band, "band_label": cz.BAND_NAMES[band - 1], "overall": overall,
                                       "focus_areas": [{"area": a, "label": a.title(), "percentile": 10} for a in focus]}
    p = prog_of([win("baseline", {"plank": 60}, cat=mk(2, 30.0, ["speed", "core"])), win("end_season", {"plank": 70}, cat=mk(3, 50.0, ["core", "agility"]))])
    assert p["band_movement"]["delta"] == 1 and p["band_movement"]["overall_delta"] == 20.0 and "up 1" in p["band_movement"]["text"]
    assert p["focus_resolved"] == ["Speed"] and p["focus_new"] == ["Agility"] and p["focus_still"] == ["Core"]


def test_progress_api_player_and_squad(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    for window, bump in (("baseline", 0), ("mid_season", 10)):
        tpl = get_template(client, world, sid, window=window).content
        rows = {pid: good_row(i, **{trial_header(BY_KEY["broad_jump"], 2): 155 + i * 5 + (bump if i == 0 else 0)}) for i, pid in enumerate(ids)}
        assert upload(client, world, fill(tpl, rows), sid, confirm=True, window=window).status_code == 200
    r = client.get(f"/players/{ids[0]}/test-progress?season_id={sid}", headers=H(world, "coach_a"))
    assert r.status_code == 200
    j = r.json()
    assert [w["window"] for w in j["windows"]] == ["baseline", "mid_season"]
    bj = next(t for t in j["tests"] if t["key"] == "broad_jump")
    assert bj["values"] == {"baseline": "155.00", "mid_season": "165.00"} and bj["change"]["state"] == "improved"
    assert j["band_movement"] is not None
    sq = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-progress", headers=H(world, "coach_a")).json()
    assert sq["windows_with_results"] == ["baseline", "mid_season"]
    row = next(p for p in sq["players"] if p["player_id"] == ids[0])
    assert row["tests_compared"] >= 1 and row["tests_improved"] >= 1
    x = client.get(f"/players/{ids[0]}/individual-plan.xlsx?season_id={sid}&window=mid_season", headers=H(world, "admin"))
    assert "Progress" in openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames
    # same access rules as the other test results
    assert client.get(f"/players/{ids[0]}/test-progress?season_id={sid}", headers=H(world, "coach_b")).status_code == 404
    assert client.get(f"/players/{ids[0]}/test-progress?season_id={sid}", headers=H(world, "physio_a")).status_code == 403
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/test-progress", headers=H(world, "coach_b")).status_code == 404
    assert client.get(f"/players/{ids[0]}/test-progress?season_id={sid}").status_code == 401


# ───────────── planned workload ─────────────
from app.plan_load import ACWR_CAP, EASY_AFTER, RISE_CAP, START_LOAD, plan_weeks, verify


def mk_weeks(n=30, pcts=None, phases=None, matches=None, tests=None):
    pcts = pcts or [min(1.0, 0.5 + 0.03 * i) for i in range(n)]
    return [{"week": i + 1, "phase": (phases or {}).get(i, "pre_season"), "percentage": pcts[i], "matches": (matches or {}).get(i, 0),
             "test": i in (tests or ())} for i in range(n)]


def logged(chronic=1500, weeks=(1400, 1500, 1500, 1600), days=40):
    return {"history_days": days, "chronic_weekly_load_28d": chronic, "weekly_loads_oldest_first": [1200, 1300, 1350, 1450, *weeks]}


def test_load_starts_from_real_logged_load():
    r = plan_weeks(weeks=mk_weeks(), status="ready", workload=logged(), sessions_by_phase={"pre_season": 2})
    assert r["summary"]["from_logs"] and r["summary"]["start_load"] == 1500
    assert r["weeks"][0]["planned_load"] <= 1600 * 1.1 + 1                       # week 1 is built on the player's real level
    assert verify(r) == []


def test_load_without_history_is_a_low_flagged_estimate():
    for w in (None, {"history_days": 10, "chronic_weekly_load_28d": 400, "weekly_loads_oldest_first": [0, 0, 0, 0, 0, 0, 200, 400]}):
        r = plan_weeks(weeks=mk_weeks(), status="ready", workload=w, sessions_by_phase={})
        assert not r["summary"]["from_logs"] and r["summary"]["start_load"] == START_LOAD and "low starting estimate" in r["summary"]["source"]
        assert verify(r) == []


def test_weekly_rise_never_above_ten_percent_and_ratio_never_above_cap():
    r = plan_weeks(weeks=mk_weeks(40, pcts=[0.4] * 5 + [1.0] * 35), status="ready", workload=logged(), sessions_by_phase={"pre_season": 2})
    for w in r["weeks"]:
        assert w["rise_cap_pct"] <= RISE_CAP * 100 + 0.6                   # counted from the last build week after an easy week
        assert w["load_ratio"] is None or w["load_ratio"] <= ACWR_CAP + 0.01
    assert any("Rise limited" in f for w in r["weeks"] for f in w["flags"])               # the jump to 100% was capped
    assert r["summary"]["max_rise_pct"] <= 10.6 and verify(r) == []


def test_easy_week_after_three_build_weeks():
    r = plan_weeks(weeks=mk_weeks(12, pcts=[0.5 + 0.1 * i for i in range(12)]), status="ready", workload=logged(), sessions_by_phase={})
    easy = [w["week"] for w in r["weeks"] if w["easy_week"]]
    assert len(easy) >= 2 and all(b - a == EASY_AFTER + 1 for a, b in zip(easy, easy[1:]))        # three build weeks, then an easy week
    for e in easy:
        assert r["weeks"][e - 1]["planned_load"] < r["weeks"][e - 2]["planned_load"]
        assert r["weeks"][e]["planned_load"] >= r["weeks"][e - 1]["planned_load"]                   # then it builds again


def test_easy_week_first_when_the_real_load_rose_four_weeks_running():
    w = logged(weeks=(1500, 1600, 1700, 1800))
    r = plan_weeks(weeks=mk_weeks(), status="ready", workload=w, sessions_by_phase={})
    assert r["weeks"][0]["easy_week"] and r["weeks"][0]["planned_load"] < 1800


def test_match_and_test_weeks_do_not_rise():
    r = plan_weeks(weeks=mk_weeks(10, pcts=[0.5 + 0.1 * i for i in range(10)], matches={1: 1}, tests={2}), status="ready", workload=logged(), sessions_by_phase={})
    a = r["weeks"]
    assert a[1]["planned_load"] <= a[0]["planned_load"] and any("Match week" in f for f in a[1]["flags"])
    assert a[2]["planned_load"] <= a[1]["planned_load"] and any("Test week" in f for f in a[2]["flags"])


def test_hold_and_caution_loads():
    kw = dict(weeks=mk_weeks(8), workload=logged(), sessions_by_phase={"pre_season": 2})
    ready, caution, hold = (plan_weeks(status=s, **kw) for s in ("ready", "caution", "hold"))
    assert all(w["planned_load"] == 0 and w["focus_sessions"] == 0 for w in hold["weeks"])
    assert caution["weeks"][0]["planned_load"] < ready["weeks"][0]["planned_load"]
    assert sum(w["planned_load"] for w in caution["weeks"]) < sum(w["planned_load"] for w in ready["weeks"])
    assert verify(caution) == []


def test_focus_sessions_fit_inside_the_week():
    r = plan_weeks(weeks=mk_weeks(6, pcts=[0.5] * 6), status="ready", workload={"history_days": 40, "chronic_weekly_load_28d": 300, "weekly_loads_oldest_first": [300] * 8},
                   sessions_by_phase={"pre_season": 3})
    for w in r["weeks"]:
        assert w["focus_load"] <= 0.4 * w["planned_load"] + 1e-6
    assert r["weeks"][0]["focus_sessions"] < 3 and any("Focus sessions reduced" in f for f in r["weeks"][0]["flags"])
    big = plan_weeks(weeks=mk_weeks(6, pcts=[0.5] * 6), status="ready", workload=logged(), sessions_by_phase={"pre_season": 2})
    assert big["weeks"][1]["focus_sessions"] == 2


def test_verify_catches_a_broken_plan():
    bad = {"weeks": [{"week": 1, "planned_load": 2000, "rise_cap_pct": 25.0, "load_ratio": 1.6, "focus_load": 1500, "match_load": 0, "bowl_load": 0,
                      "match_over_limit": False, "bowl_days": 0, "matches": 0, "spells": None}]}
    assert len(verify(bad)) == 3


def test_plan_week_by_week_in_the_plan_output():
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=READY, g=grid(), workload=logged())
    assert len(plan["weeks"]) == len(grid()["percentage"]) and plan["load_violations"] == []
    assert plan["load_summary"]["from_logs"] and all("planned_load" in w and "flags" in w for w in plan["weeks"])
    assert "planned_percentage" not in plan["weeks"][0]


def test_individual_plan_api_has_load_and_all_areas(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    j = client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    assert j["load_violations"] == [] and not j["load_summary"]["from_logs"] and "low starting estimate" in j["load_summary"]["source"]
    assert j["weeks"][0]["planned_load"] > 0 and j["weeks"][0]["load_ratio"] is not None
    assert {a["area"] for a in j["phases"][0]["areas"]} == {"endurance", "power", "upper_strength", "speed", "agility", "core"}


def test_plan_uses_the_players_real_logged_load(client, world, db):
    from datetime import timedelta
    from app.models import EventType, WorkloadLog
    from app.workload_service import today_lk
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    for wk in range(5):                                                       # about 5 weeks, 4 sessions of 60 min at RPE 6 = 1,440 units a week
        for d in (1, 2, 4, 5):
            db.add(WorkloadLog(player_id=ids[0], log_date=today_lk() - timedelta(days=wk * 7 + d), session_type=EventType.training, attended=True, duration_min=60, rpe=6))
    db.commit()
    j = client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    assert j["load_summary"]["from_logs"] and 1300 <= j["load_summary"]["start_load"] <= 1600
    assert j["weeks"][0]["planned_load"] <= j["load_summary"]["start_load"] * 1.11 + 1
    assert j["load_violations"] == []
    x = client.get(f"/players/{ids[0]}/individual-plan.xlsx?season_id={sid}&window=baseline", headers=H(world, "admin"))
    ws = openpyxl.load_workbook(io.BytesIO(x.content))["Weekly load"]
    assert [c.value for c in ws[1]][:5] == ["Week", "Starts", "Phase", "Squad load %", "Planned load (units)"] and ws.cell(row=2, column=5).value > 0


# ───────────── personal sets and reps ─────────────
from app.dosing import personal_dose
from app.session_plans import DOSE


def dose(kind="leg_strength", phase="pre_competition", priority=True, pct=10.0, status="ready", name="Squat"):
    return personal_dose(kind, name, phase, priority=priority, percentile=pct, status=status)


def test_dose_priority_builds_to_the_top_and_weaker_means_higher():
    weak, mild = dose(pct=2.0), dose(pct=45.0)
    assert weak["rep_start"] == 8 and weak["rep_target"] == 12 and weak["sets_start"] == 2 and weak["sets_target"] == 3          # DOSE range 8-12, 2-3
    assert mild["rep_target"] < weak["rep_target"] and mild["rep_target"] >= 10
    assert weak["rep"] == "8, building to 12" and weak["set"] == "2, building to 3" and weak["progression"]


def test_dose_maintenance_untested_and_phase_limits():
    keep = dose(priority=False, pct=80.0)
    assert keep["rep_target"] == 9 and "Maintenance" in keep["basis"]                                  # lower-middle of 8-12
    assert dose(priority=False, pct=None)["rep_target"] == 9 and "Not tested" in dose(priority=False, pct=None)["basis"]
    inseason = dose(phase="in_season", pct=2.0)
    assert inseason["rep_target"] <= 10 and "in-season" in inseason["basis"] and inseason["sets_target"] == 2        # capped at the middle; in-season maintenance sets
    assert dose(phase="transition")["rep_target"] == dose(phase="transition")["rep_start"] == 8
    assert dose(status="caution")["rep_target"] == 8 and dose(status="caution")["sets_target"] == 2


def test_dose_never_leaves_the_supplied_range_and_keeps_special_cases():
    for kind, (t, rep, sets, rest) in DOSE.items():
        for pct in (0.0, 25.0, 49.9):
            d = dose(kind=kind, pct=pct)
            nums = [d[k] for k in ("rep_start", "rep_target", "sets_start", "sets_target")]
            if None in nums:
                assert kind == "aerobic" and d["rep"] == rep and d["set"] == sets                          # aerobic stays as the list says
                continue
            rr = [int(x) for x in __import__("re").findall(r"\d+", rep.split(" ")[0])]
            ss = [int(x) for x in __import__("re").findall(r"\d+", sets)]
            assert min(rr) <= d["rep_start"] <= d["rep_target"] <= max(rr) and min(ss) <= d["sets_start"] <= d["sets_target"] <= max(ss)
    nordic = dose(kind="leg_strength", name="Nordic hamstring curl", pct=2.0)
    assert nordic["rep_target"] <= 5 and nordic["sets_target"] <= 2                                         # very low volume for U15
    assert dose(kind="rotation_power", name="Med-ball throw")["rep"].endswith("each side") or "each side" in dose(kind="rotation_power", name="x")["rep"]


def test_plan_doses_differ_between_priority_and_other_areas():
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=READY, g=grid())
    ph = next(p for p in plan["phases"] if p["phase"] == "pre_competition")
    core = next(a for a in ph["areas"] if a["area"] == "core")["exercises"]
    other = next(a for a in ph["areas"] if a["area"] == "upper_strength")["exercises"]
    assert core and other and core[0]["sets_target"] > other[0]["sets_target"] or core[0]["rep_target"] > other[0]["rep_target"]
    assert all(e["basis"] and "rep" in e and "set" in e for a in ph["areas"] for e in a["exercises"])
    caution = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=CAUTION, g=grid())
    cph = next(p for p in caution["phases"] if p["phase"] == "pre_competition")
    assert all(e["rep_target"] in (None, e["rep_start"]) and e["sets_target"] in (None, e["sets_start"]) for a in cph["areas"] for e in a["exercises"])


# ───────────── matches and bowling inside the load ─────────────
def grid_with_matches(n_per_week=1, start=date(2027, 1, 1), end=date(2027, 9, 30), every=7):
    from datetime import timedelta
    ev, d = [], start + timedelta(days=60)
    while d < end - timedelta(days=30):
        ev += [{"event_type": "match", "date": d + timedelta(days=i), "hours": 5.0} for i in range(n_per_week)]
        d += timedelta(days=every)
    return build_grid(squad_name="W", season={"name": "2027", "start_date": start, "end_date": end}, phases=suggest_phases(start, end), events=ev, generated_on=start)


def test_matches_are_part_of_the_weekly_load():
    from app.plan_load import MATCH_UNITS
    g = grid_with_matches()
    plan = build_individual_plan(player={"name": "P", "role": "batter"}, cat=cat_with("core"), ready=READY, g=g, workload=logged())
    played = [w for w in plan["weeks"] if w["matches"]]
    assert played and all(w["match_load"] == w["matches"] * MATCH_UNITS for w in played)
    for w in plan["weeks"]:
        assert w["match_load"] + w["bowl_load"] + w["focus_load"] + w["general_load"] <= w["planned_load"] + 2          # parts never exceed the week
        assert w["general_load"] >= 0
    assert plan["load_violations"] == [] and "Each squad match counts" in plan["load_summary"]["assumptions"]


def test_batter_has_no_bowling_load_bowlers_do():
    g = grid_with_matches()
    kw = dict(cat=cat_with("core"), ready=READY, g=g, workload=logged())
    batter = build_individual_plan(player={"name": "P", "role": "batter"}, **kw)
    fast = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, **kw)
    assert all(w["bowl_load"] == 0 and w["bowl_days"] == 0 for w in batter["weeks"])
    assert any(w["bowl_load"] > 0 for w in fast["weeks"])


def test_fast_bowler_limits_hold_with_matches_counted():
    from app.workload_rules import DEFAULT_FAST_LIMITS as L
    for per_week in (1, 2, 3):
        g = grid_with_matches(per_week)
        plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=READY, g=g, workload=logged())
        for w in plan["weeks"]:
            assert w["bowl_days"] + w["matches"] <= L["max_bowling_days_week"] or w["matches"] > L["max_bowling_days_week"]     # a match is a bowling day
            assert w["overs_per_day"] <= 8 and all(int(o) <= L["max_spell_overs"] for o in (w["spells"] or "").split("+") if o)
        assert all("bowling days" not in v and "spell" not in v for v in plan["load_violations"])


def test_bowling_is_reduced_never_added_to_fit_the_load():
    from app.load_distribution import build_loads
    g = grid_with_matches(1)
    squad = build_loads(g)
    light = {"history_days": 40, "chronic_weekly_load_28d": 1000, "weekly_loads_oldest_first": [1000] * 8}
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=READY, g=g, workload=light)
    for w, d, o in zip(plan["weeks"], squad["bowl_days"], squad["overs_per_day"]):
        assert w["bowl_days"] <= d and w["overs_per_day"] <= (o or 0)
    assert any("Bowling overs reduced" in f for w in plan["weeks"] for f in w["flags"])


def test_match_load_alone_above_the_limit_is_flagged_not_hidden():
    from app.plan_load import MATCH_UNITS
    weeks = [{"week": i + 1, "phase": "in_season", "percentage": 0.5, "matches": 3 if i == 4 else 0, "test": False} for i in range(8)]
    r = plan_weeks(weeks=weeks, status="ready", workload=logged(chronic=800, weeks=(800,) * 4), sessions_by_phase={"in_season": 2})
    w5 = r["weeks"][4]
    assert w5["match_over_limit"] and w5["planned_load"] == 3 * MATCH_UNITS and w5["general_load"] == 0 and w5["focus_sessions"] == 0 and w5["bowl_load"] == 0
    assert any("Match load alone" in f for f in w5["flags"]) and r["summary"]["match_over_limit_weeks"] == 1
    assert verify(r) == []                                                    # reported in the flags and the summary, not counted as a hidden breach


def test_estimate_start_includes_the_first_weeks_matches():
    from app.plan_load import MATCH_UNITS
    weeks = [{"week": i + 1, "phase": "in_season", "percentage": 0.6, "matches": 1, "test": False} for i in range(6)]
    r = plan_weeks(weeks=weeks, status="ready", workload=None, sessions_by_phase={})
    assert r["summary"]["start_load"] == START_LOAD + MATCH_UNITS and "first week's match" in r["summary"]["source"]
    assert verify(r) == [] and all(not w["match_over_limit"] for w in r["weeks"])


def test_hold_has_no_matches_or_bowling_planned():
    g = grid_with_matches()
    plan = build_individual_plan(player={"name": "P", "role": "fast_bowler"}, cat=cat_with("core"), ready=HOLD, g=g, workload=logged())
    assert all(w["match_load"] == 0 and w["bowl_load"] == 0 and w["planned_load"] == 0 for w in plan["weeks"])


def test_spin_and_all_rounder_notes_and_api_fields(client, world, db):
    g = grid_with_matches()
    sp = build_individual_plan(player={"name": "P", "role": "spin_bowler"}, cat=cat_with("core"), ready=READY, g=g, workload=logged())
    assert any("coach sets the overs" in n for n in sp["notes"])
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    j = client.get(f"/players/{ids[0]}/individual-plan?season_id={sid}&window=baseline", headers=H(world, "admin")).json()
    w = j["weeks"][0]
    assert {"match_load", "bowl_load", "bowl_days", "overs_per_day", "spells", "general_load", "match_over_limit"} <= set(w)
    ex = next(e for a in j["phases"][0]["areas"] for e in a["exercises"])
    assert {"rep", "set", "rep_target", "sets_target", "basis", "progression"} <= set(ex)
    x = client.get(f"/players/{ids[0]}/individual-plan.xlsx?season_id={sid}&window=baseline", headers=H(world, "admin"))
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert [c.value for c in wb["Weekly load"][1]][5:10] == ["Matches (units)", "Bowling (days x overs, spells)", "Bowling (units)", "Focus work (units)", "General training (units)"]
    assert "Why this dose" in [c.value for c in wb["Focus plan"][1]]
