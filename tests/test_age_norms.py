"""Age-group references for the physical tests (U15 / U17 / U19): labels, typo ranges, and how they personalise the plan."""
import pytest

from app.age_norms import AGE_GROUPS, PLAUSIBLE, REFERENCE, age_band, plausible, reference
from app.player_profile import build_profile, physical_goal
from app.test_battery import BY_KEY, AREA_LABEL, SUPER, areas_for, parse_value
from .test_personal_plan import grid, plan as make_plan


def test_every_test_has_sensible_references_for_every_age_group():
    assert set(REFERENCE) == set(BY_KEY) and set(PLAUSIBLE) == set(BY_KEY)
    for key, by_age in REFERENCE.items():
        better = (lambda a, b: a > b) if BY_KEY[key].higher_is_better else (lambda a, b: a < b)
        assert set(by_age) == set(AGE_GROUPS)
        for ag, (dev, exp, strong) in by_age.items():
            assert better(exp, dev) and better(strong, exp), (key, ag)                    # developing < expected < strong
            lo, hi = PLAUSIBLE[key][ag]
            assert lo < min(dev, strong) and max(dev, strong) < hi, (key, ag)             # the typo range is far wider
        assert better(by_age["U17"][1], by_age["U15"][1]) and better(by_age["U19"][1], by_age["U17"][1]), key   # older = better expected


@pytest.mark.parametrize("key,value,age,band", [
    ("broad_jump", 150, "U15", "below"), ("broad_jump", 175, "U15", "developing"), ("broad_jump", 190, "U15", "on_track"),
    ("broad_jump", 210, "U15", "strong"), ("broad_jump", 185, "U19", "below"),           # the same jump is weak at U19
    ("sprint_20m", 3.20, "U15", "strong"), ("sprint_20m", 3.15, "U19", "on_track"), ("sprint_20m", 3.70, "U17", "below"),
    ("run_2km", 540, "U15", "developing"), ("run_2km", 540, "U19", "below"),
])
def test_bands_follow_the_age_group(key, value, age, band):
    b = age_band(key, value, age)
    assert b["band"] == band and 5 <= b["score"] <= 95 and b["age_group"] == age


def test_scores_and_unknowns():
    assert age_band("pushups", 20, "U15")["score"] == 50.0 and age_band("pushups", 28, "U15")["score"] == 75.0
    assert age_band("pushups", 20, "U15", "female") is None and reference("pushups", "U15", "female") is None   # no girls' references set
    assert age_band("pushups", None, "U15") is None
    assert age_band("pushups", 20, "U99")["age_group"] == "U15"                                                   # unknown -> U15
    assert age_band("bronco", 300, "U19")["quality"] == "estimate"


def test_typo_ranges_depend_on_the_age_group():
    plank = BY_KEY["plank"]
    with pytest.raises(ValueError, match="outside the plausible range"):
        parse_value(plank, 500, plausible("plank", "U15"))
    assert parse_value(plank, 500, plausible("plank", "U19")) == 500.0
    assert plausible("sprint_20m", "U15")[0] > plausible("sprint_20m", "U19")[0]


def _unranked(values):
    """A categorisation result for a player whose level group is too small to rank (no percentiles, overall None)."""
    areas = []
    for area in areas_for(SUPER):
        tests = [{"key": t.key, "label": t.label, "unit": t.unit, "percentile": None, "value": values.get(t.key), "display": str(values.get(t.key))}
                 for t in BY_KEY.values() if SUPER in t.levels and t.area == area]
        areas.append({"area": area, "label": AREA_LABEL[area], "percentile": None, "tests": tests})
    return {"overall": None, "areas": areas, "focus_areas": []}


GOOD_U15 = {"run_2km": 500, "broad_jump": 200, "pushups": 26, "inverted_row": 15, "sprint_20m": 3.30, "shuttle_5_10_5": 4.90, "plank": 70}


def test_small_squad_still_gets_a_personal_profile_from_age_references():
    prof = build_profile(player={"name": "P", "role": "batter", "age_group": "U15", "gender": "male"}, cat=_unranked(GOOD_U15))
    by = {a["area"]: a for a in prof["areas"]}
    assert all(a["source"] == "age reference" for a in prof["areas"])
    assert by["core"]["status"] == "priority" and by["core"]["age_label"] == "Developing"      # plank 70 s: below expected for U15
    assert by["power"]["status"] in ("solid", "strength") and by["power"]["weakest_test"] == "broad_jump"
    older = build_profile(player={"name": "P", "role": "batter", "age_group": "U19", "gender": "male"}, cat=_unranked(GOOD_U15))
    assert len([a for a in older["areas"] if a["status"] == "priority"]) > len([a for a in prof["areas"] if a["status"] == "priority"])


def test_unranked_player_now_gets_exercises_goals_and_a_note():
    from app.individual_plan import build_individual_plan
    p = build_individual_plan(player={"name": "P", "role": "batter", "gender": "male"}, cat=_unranked(GOOD_U15),
                              ready={"status": "ready", "label": "Ready", "reason": ""}, g=grid("U15"), extra={"window": "baseline"})
    core = next(a for a in p["phases"][0]["areas"] if a["area"] == "core")
    assert core["priority"] and core["exercises"]
    goal = next(g for g in p["goals"] if g["kind"] == "test" and g["test"] == "plank")
    assert goal["target"] > 70 and goal["target"] <= 70 * 1.08 + 1e-6 and "U15" in goal["why"]
    assert any("age references" in n for n in p["notes"])


def test_goal_aims_for_the_age_expected_value_when_the_group_is_behind():
    area = {"area": "upper_strength", "label": "Upper-body strength", "percentile": 30.0, "source": "test",
            "tests": [{"key": "pushups", "label": "Push-ups", "percentile": 30.0, "value": 19.0}]}
    weak_group = [8, 10, 12, 14, 15, 16, 19, 20]                                   # rank-based target would be about 15-16
    g = physical_goal(area, "pushups", weak_group, "Mid-season test", "U15")
    assert g["target"] >= 20 and "expected 20" in g["why"]                         # expected for U15 is 20; capped at +8%


def test_age_norms_endpoint(client, world):
    j = client.get("/meta/age-norms", headers=world["h"]["coach_a"]).json()
    assert j["groups"] == ["U15", "U17", "U19"] and len(j["tests"]) == len(BY_KEY)
    jump = next(t for t in j["tests"] if t["test"] == "broad_jump")
    assert jump["ages"]["U17"]["expected"] == "200.00" and jump["quality"] == "published youth norms"
