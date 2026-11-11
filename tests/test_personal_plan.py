"""Every player gets their OWN plan: built from their strengths, weaknesses, growth, history and ratings."""
from datetime import date

import pytest

from app.annual_grid import build_grid
from app.individual_plan import build_individual_plan
from app.player_profile import build_profile, growth, physical_goal, training_age
from app.season_phases import suggest_phases
from app.test_battery import AREA_LABEL, BY_KEY, SUPER, areas_for
from app.models import PdpRubricItem, Player, PlayerRole, Gender, Screening, NeedsAnalysisItem, UserRole
from .conftest import login, make_user

READY = {"status": "ready", "label": "Ready", "reason": "ok"}
START, END = date(2027, 1, 1), date(2027, 9, 30)


def grid(age="U15"):
    return build_grid(squad_name="W", season={"name": "2027", "start_date": START, "end_date": END}, phases=suggest_phases(START, END),
                      events=[], generated_on=START, age_group=age)


def cat(pcts: dict[str, float], values: dict[str, float] | None = None):
    """A categorisation result with per-test ranks. pcts: {test_key: percentile}; area rank = mean of its tests."""
    values = values or {}
    areas = []
    for area in areas_for(SUPER):
        tests = [{"key": t.key, "label": t.label, "unit": t.unit, "percentile": pcts.get(t.key, 70.0), "value": values.get(t.key, 10.0),
                  "display": str(values.get(t.key, 10.0))} for t in BY_KEY.values() if SUPER in t.levels and t.area == area]
        p = round(sum(t["percentile"] for t in tests) / len(tests), 1)
        areas.append({"area": area, "label": AREA_LABEL[area], "percentile": p, "tests": tests})
    focus = sorted(({"area": a["area"], "label": a["label"], "percentile": a["percentile"]} for a in areas if a["percentile"] < 50), key=lambda f: f["percentile"])
    return {"overall": 50.0, "areas": areas, "focus_areas": focus}


def plan(name="P", role="fast_bowler", pcts=None, **kw):
    player = {"name": name, "role": role, **kw.pop("player", {})}
    return build_individual_plan(player=player, cat=cat(pcts or {}), ready=kw.pop("ready", READY), g=kw.pop("g", grid()), **kw)


def area_ex(p, phase, area):
    ph = next(x for x in p["phases"] if x["phase"] == phase)
    return [e["name"] for e in next(a for a in ph["areas"] if a["area"] == area)["exercises"]]


# ───────────── the weakest TEST decides the movement ─────────────
def test_weak_pull_gets_pulling_work_and_weak_push_gets_pushing_work():
    pull = plan("A", pcts={"inverted_row": 10.0, "pushups": 60.0})
    push = plan("B", pcts={"pushups": 10.0, "inverted_row": 60.0})
    a, b = area_ex(pull, "pre_season", "upper_strength"), area_ex(push, "pre_season", "upper_strength")
    assert a[0] in ("Band row", "Pull-up or assisted pull-up") and b[0] == "Push-up"
    assert a != b
    why = next(e for e in next(x for x in pull["phases"] if x["phase"] == "pre_season")["areas"] if e["area"] == "upper_strength")["exercises"][0]["why"]
    assert "inverted row" in why and "weakest" in why


def test_weak_change_of_direction_gets_pro_agility():
    p = plan(pcts={"shuttle_5_10_5": 12.0})
    assert "Pro-agility drill" in area_ex(p, "pre_competition", "agility")


def test_same_role_different_results_means_different_plans():
    a = plan("A", pcts={"plank": 10.0, "sprint_20m": 15.0})
    b = plan("B", pcts={"broad_jump": 10.0, "run_2km": 15.0})
    pa = [x["area"] for x in a["phases"][0]["areas"] if x["priority"]]
    pb = [x["area"] for x in b["phases"][0]["areas"] if x["priority"]]
    assert set(pa) == {"core", "speed"} and set(pb) == {"power", "endurance"}
    assert [g["label"] for g in a["goals"]] != [g["label"] for g in b["goals"]]


# ───────────── strengths are kept and used ─────────────
def test_strengths_are_maintained_and_explained():
    p = plan(pcts={"plank": 10.0, "sprint_20m": 90.0})
    s = next(a for a in p["profile"]["areas"] if a["area"] == "speed")
    assert s["status"] == "strength" and "run-up" in s["use"]
    assert any(g["kind"] == "maintain" and "Speed" in g["label"] for g in p["goals"])
    pre = next(x for x in p["phases"] if x["phase"] == "pre_competition")
    speed = next(a for a in pre["areas"] if a["area"] == "speed")
    assert speed["exercises"] and "Strength" in speed["note"]


# ───────────── importance from the needs analysis ─────────────
def test_needs_analysis_shifts_work_to_what_matters_for_the_player():
    pcts = {"plank": 20.0, "inverted_row": 20.0, "pushups": 20.0}
    core_high = plan(pcts=pcts, extra={"needs": {("Muscular strength", "Core"): "HIGH", ("Muscular strength", "Upper body"): "LOW"}})
    upper_high = plan(pcts=pcts, extra={"needs": {("Muscular strength", "Core"): "LOW", ("Muscular strength", "Upper body"): "HIGH"}})
    slots = lambda p, a: next(x for x in p["phases"][0]["areas"] if x["area"] == a)["slots"]
    assert slots(core_high, "core") > slots(core_high, "upper_strength")
    assert slots(upper_high, "upper_strength") > slots(upper_high, "core")
    assert core_high["profile"]["importance_source"] == "screening needs analysis"


# ───────────── growth ─────────────
def test_growth_rate_detects_the_spurt():
    g = growth([(date(2026, 9, 1), 150.0), (date(2027, 3, 1), 155.0)], "unknown", "batter")
    assert g["velocity_cm_yr"] == pytest.approx(10.1, abs=0.2) and g["stage"] == "circa" and g["source"] == "growth rate"
    assert growth([(date(2026, 9, 1), 150.0), (date(2026, 10, 1), 152.0)], None, "batter")["velocity_cm_yr"] is None    # too close together
    assert growth([], "post_phv", "fast_bowler")["bowling_window"]
    assert not growth([], "pre_phv", "fast_bowler")["bowling_window"]


def test_growth_spurt_changes_exercises_doses_load_and_bowling():
    spurt = [(date(2026, 6, 1), 150.0), (date(2027, 1, 1), 156.0)]
    normal = plan("N", pcts={"broad_jump": 10.0})
    grow = plan("N", pcts={"broad_jump": 10.0}, extra={"heights": spurt})
    assert grow["profile"]["growth"]["in_spurt"] and not normal["profile"]["growth"]["in_spurt"]
    # fewer jumps in the power work, and any jump stays at the low end of its range
    kinds = lambda p: [e["kind"] for e in next(a for a in next(x for x in p["phases"] if x["phase"] == "pre_competition")["areas"] if a["area"] == "power")["exercises"]]
    assert kinds(grow).count("plyometric_power") < kinds(normal).count("plyometric_power")
    for ph in grow["phases"]:
        for a in ph["areas"]:
            for e in a["exercises"]:
                if e["kind"] in ("plyometric_power", "repeat_sprint") and e["rep_start"] is not None:
                    assert e["rep_target"] == e["rep_start"]
    # a lower season peak and one over fewer per bowling day for a fast bowler
    assert max(w["planned_load"] for w in grow["weeks"]) < max(w["planned_load"] for w in normal["weeks"])
    od = lambda p: max(w["overs_per_day"] for w in p["weeks"])
    assert od(grow) == od(normal) - 1
    assert any("Growth window" in f for w in grow["weeks"] for f in w["flags"])
    assert grow["load_violations"] == []


# ───────────── training age ─────────────
def test_new_player_gets_smaller_targets_and_simpler_exercises():
    dob = date(2013, 1, 1)
    new = plan("X", pcts={"broad_jump": 10.0}, player={"age": 14}, extra={"screening": {"start_age": 13}})
    exp = plan("X", pcts={"broad_jump": 10.0}, player={"age": 14}, extra={"screening": {"start_age": 7}})
    assert training_age(14, 13)["band"] == "new" and training_age(14, 7)["band"] == "experienced"
    pick = lambda p: [e for a in next(x for x in p["phases"] if x["phase"] == "pre_season")["areas"] if a["area"] == "power" for e in a["exercises"]]
    assert sum(e["rep_target"] or 0 for e in pick(new)) <= sum(e["rep_target"] or 0 for e in pick(exp))
    assert not any(w in e["name"].lower() for e in pick(new) for w in ("bulgarian", "nordic"))


# ───────────── goals ─────────────
def test_goal_targets_come_from_the_players_own_group():
    a = {"area": "upper_strength", "label": "Upper-body strength", "percentile": 20.0,
         "tests": [{"key": "pushups", "label": "Push-ups", "percentile": 20.0, "value": 12.0}]}
    g = physical_goal(a, "pushups", [8, 12, 14, 15, 16, 18, 20, 25], "Mid-season test")
    assert g["target"] > 12 and g["target"] <= 12 * 1.08 + 1 and g["by"] == "Mid-season test"
    t = physical_goal({**a, "tests": [{"key": "sprint_20m", "label": "20 m sprint", "percentile": 20.0, "value": 3.6}]}, "sprint_20m",
                      [3.2, 3.3, 3.4, 3.5, 3.6, 3.7], None)
    assert 3.6 * 0.92 - 1e-9 <= t["target"] < 3.6                                    # faster, but not more than 8% in one window


def test_plan_has_goals_reviews_typical_week_and_explains_missing_inputs():
    p = plan(pcts={"plank": 10.0}, extra={"window": "baseline", "cohort_values": {"plank": [30, 40, 50, 60, 70, 80]}})
    assert any(g["kind"] == "test" and g["by"] == "Mid-season test" for g in p["goals"])
    assert p["reviews"] and all("date" in r for r in p["reviews"])
    week = next(x for x in p["phases"] if x["phase"] == "in_season")["typical_week"]
    assert [d["day"] for d in week] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert "Match" in next(d for d in week if d["day"] == "Sat")["items"]
    assert any("PDP ratings" in m for m in p["profile"]["missing"])


# ───────────── cricket skills and habits from the coach's ratings ─────────────
def test_low_pdp_ratings_become_skill_drills_goals_and_habits():
    pdp = {("Pace Bowl", "Control"): 2, ("Field", "Outfield catching"): 1, ("Pace Bowl", "Ball Speed"): 5,
           ("Nutrition", "Hydration"): 2, ("Nutrition", "Alcohol intake"): 1, ("Batting to Pace", "Rotate strike"): 1}
    p = plan(pcts={"plank": 10.0}, extra={"pdp": pdp})
    pre = next(x for x in p["phases"] if x["phase"] == "pre_season")
    ctl = next(s for s in pre["skills"] if s["skill"] == "Control")
    assert ctl["drills"] and any(w in ctl["drills"][0]["name"].lower() for w in ("target", "single-stump", "cone"))
    assert any(s["skill"] == "Outfield catching" and s["drills"] for s in pre["skills"])
    assert not any(s["skill"] == "Rotate strike" for s in pre["skills"])          # batting group is not a fast bowler's PDP group
    assert any(g["kind"] == "skill" and "Control" in g["label"] for g in p["goals"])
    assert any(h["item"] == "Hydration" for h in p["habits"])
    assert not any("Alcohol" in str(x) for x in (p["habits"], p["goals"], p["profile"]["skills"]))
    assert any("Ball Speed" in s["label"] for s in p["strengths"])


def test_pdp_rating_fills_an_untested_area():
    prof = build_profile(player={"name": "P", "role": "batter"}, cat=None, pdp={("Physical", "Agility"): 2})
    a = next(x for x in prof["areas"] if x["area"] == "agility")
    assert a["status"] == "priority" and a["source"] == "coach rating"


# ───────────── the player's own bowling limits ─────────────
def test_custom_bowling_limits_are_used_in_the_plan():
    p = plan(player={"custom_limits": {"max_spell_overs": 3, "max_bowling_days_week": 2}})
    assert all(int(o) <= 3 for w in p["weeks"] if w["spells"] for o in w["spells"].split("+"))
    assert all(w["bowl_days"] + w["matches"] <= 2 or w["match_over_limit"] for w in p["weeks"])
    assert p["limits"]["max_spell_overs"] == 3 and p["load_violations"] == []


def test_u17_start_load_is_higher_without_history():
    assert plan(g=grid("U17"))["load_summary"]["start_load"] > plan(g=grid("U15"))["load_summary"]["start_load"]


def test_plan_is_stable_for_the_same_player():
    assert plan("Same", pcts={"plank": 10.0})["phases"] == plan("Same", pcts={"plank": 10.0})["phases"]


# ───────────── API: PDP ratings feed the plan ─────────────
def test_pdp_api_ratings_and_permissions(client, world, db, seeded):
    w = world
    r = client.get(f"/players/{w['bob']}/pdp", headers=w["h"]["coach_a"])
    assert r.status_code == 200
    groups = {g["group"]: g["items"] for g in r.json()["groups"]}
    assert "Pace Bowl" in groups and "Batting to Pace" not in groups                   # Bob is a fast bowler
    assert all(i["skill"] not in ("Alcohol intake", "Skinfolds") for i in groups["Nutrition"])
    control = next(i for i in groups["Pace Bowl"] if i["skill"] == "Control")
    put = client.put(f"/players/{w['bob']}/pdp", headers=w["h"]["coach_a"], json={"rated_on": "2026-10-01", "ratings": {str(control["id"]): 2}})
    assert put.status_code == 200
    assert next(i for g in put.json()["groups"] for i in g["items"] if i["id"] == control["id"])["rating"] == 2
    assert client.put(f"/players/{w['bob']}/pdp", headers=w["h"]["coach_a"], json={"ratings": {str(control["id"]): 6}}).status_code == 422
    wk = db.query(PdpRubricItem).filter_by(group_name="Wk").first()
    assert client.put(f"/players/{w['bob']}/pdp", headers=w["h"]["coach_a"], json={"ratings": {str(wk.id): 3}}).status_code == 422
    assert client.put(f"/players/{w['bob']}/pdp", headers=w["h"]["physio_a"], json={"ratings": {}}).status_code == 403
    assert client.get(f"/players/{w['cara']}/pdp", headers=w["h"]["coach_a"]).status_code == 404        # other squad
    assert client.get(f"/players/{w['bob']}/pdp", headers=w["h"]["bob_login"]).status_code in (403, 404)


def test_api_plan_uses_growth_screening_and_ratings(client, world, db, seeded):
    """End to end: two test windows (height grows), a screening needs analysis and a PDP rating all reach the player's plan."""
    from .test_testing import add_players, fill, get_template, good_row, make_season, upload
    w = world
    ids = add_players(db, w)
    sid = make_season(client, w)
    upload(client, w, fill(get_template(client, w, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    mid = {pid: good_row(i, **{"Test date (YYYY-MM-DD)": "2027-06-01", "Height (cm)": 150.0 + i + (4.0 if i == 0 else 0.5)}) for i, pid in enumerate(ids)}
    upload(client, w, fill(get_template(client, w, sid, window="mid_season").content, mid), sid, confirm=True, window="mid_season")
    pid = ids[0]
    scr = client.post(f"/players/{pid}/screenings", headers=w["h"]["coach_a"], json={
        "screening_date": "2027-01-10", "start_age": 13, "this_year_objective": "Make the provincial squad",
        "needs": [{"category": "Muscular strength", "item": "Upper body", "level": "HIGH"}]})
    assert scr.status_code == 201, scr.text
    field = client.get(f"/players/{pid}/pdp", headers=w["h"]["coach_a"]).json()
    catching = next(i for g in field["groups"] for i in g["items"] if g["group"] == "Field" and i["skill"] == "Outfield catching")
    assert client.put(f"/players/{pid}/pdp", headers=w["h"]["coach_a"], json={"rated_on": "2026-10-15", "ratings": {str(catching["id"]): 2}}).status_code == 200

    j = client.get(f"/players/{pid}/individual-plan?season_id={sid}&window=mid_season", headers=w["h"]["coach_a"]).json()
    pr = j["profile"]
    assert pr["growth"]["velocity_cm_yr"] and pr["growth"]["velocity_cm_yr"] >= 7 and pr["growth"]["in_spurt"]       # 4 cm in 4 months
    assert pr["importance_source"] == "screening needs analysis" and pr["objective"] == "Make the provincial squad"
    assert pr["training_age"]["years"] is not None
    assert pr["inputs"]["previous_window"] and pr["inputs"]["coach_ratings"]
    assert any(g["kind"] == "skill" and "Outfield catching" in g["label"] for g in j["goals"])
    other = client.get(f"/players/{ids[3]}/individual-plan?season_id={sid}&window=mid_season", headers=w["h"]["coach_a"]).json()
    assert not other["profile"]["growth"]["in_spurt"]
    assert j["goals"] != other["goals"] or j["phases"] != other["phases"]                                           # not the same plan


# ───────────── every weak area is worked in every phase ─────────────
WEAKEST_TEST = {"endurance": "run_2km", "power": "broad_jump", "upper_strength": "pushups", "speed": "sprint_20m",
                "agility": "shuttle_5_10_5", "core": "plank"}


@pytest.mark.parametrize("area", list(WEAKEST_TEST))
def test_every_weak_area_gets_work_in_every_phase(area):
    from app.individual_plan import AREA_KINDS, MAIN_KINDS
    p = plan(pcts={WEAKEST_TEST[area]: 8.0})
    for ph in p["phases"]:
        a = next(x for x in ph["areas"] if x["area"] == area)
        assert a["priority"] and a["exercises"], (area, ph["phase"])                         # never left without work
        assert all(e["kind"] in AREA_KINDS[area] for e in a["exercises"])
        if ph["phase"] != "transition":
            assert len(a["exercises"]) >= 4, (area, ph["phase"])                            # a real share of the programme
        if not any(e["kind"] in MAIN_KINDS[area] for e in a["exercises"]):
            assert a["note"] and ("foundation" in a["note"] or "base" in a["note"]), (area, ph["phase"])   # and it says why
        names = [e["name"] for x in ph["areas"] for e in x["exercises"]]
        assert len(names) == len(set(names)), ph["phase"]                                    # no exercise counted twice
    comp = next(x for x in p["phases"] if x["phase"] == "pre_competition")
    assert any(e["kind"] in MAIN_KINDS[area] for e in next(x for x in comp["areas"] if x["area"] == area)["exercises"])
