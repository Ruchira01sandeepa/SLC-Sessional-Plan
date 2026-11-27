"""SLC U15 points benchmark (the men's / U19 points system adapted to the U15 tests)."""
import pytest

from app.assessment import benchmark as bm
from app.assessment import categorisation as cz
from app.assessment.test_battery import PROVINCIAL, SUPER

H = lambda w, who: w["h"][who]
BEST = {"run_2km": 480, "broad_jump": 240, "pushups": 50, "inverted_row": 30, "sprint_20m": 3.0, "shuttle_5_10_5": 5.0, "plank": 300}


def test_shared_tests_are_the_u19_cut_offs_times_the_age_factor():
    u19 = {"run_2km": [449, 457, 464, 472, 480, 495, 510], "sprint_20m": [3.00, 3.05, 3.10, 3.15, 3.20],
           "shuttle_5_10_5": [4.79, 4.99, 5.15, 5.20, 5.50]}
    for key, cuts in u19.items():
        ours = [c for c, _ in bm.U15[key][2]]
        assert ours == pytest.approx([c * bm.AGE_FACTOR for c in cuts], abs=0.6 if key == "run_2km" else 0.006), key


@pytest.mark.parametrize("key,value,pts", [
    ("run_2km", 485, 7), ("run_2km", 486, 6), ("run_2km", 551, 1), ("run_2km", 552, 0),        # lower is better, cut-off included
    ("sprint_20m", 3.04, 5), ("sprint_20m", 3.46, 1), ("sprint_20m", 3.47, 0),
    ("broad_jump", 235, 5), ("broad_jump", 234.9, 4), ("broad_jump", 174, 0),                   # higher is better
    ("pushups", 25, 2), ("inverted_row", 6, 0), ("plank", 88, 0), ("plank", 600, 5), ("shuttle_5_10_5", 5.85, 1)])
def test_points(key, value, pts):
    assert bm.points(key, value) == pts


def test_full_marks_and_bands():
    s = bm.score(SUPER, BEST)
    assert (s["total"], s["max"], s["band"]) == (34, 34, "green") and s["note"] is None
    assert [a["max"] for a in s["areas"]] == [7, 5, 7, 5, 5, 5] and bm.MAX == 34
    assert all(t["next"] is None for t in s["tests"])


def test_strength_is_the_mean_of_push_ups_and_inverted_row():
    s = bm.score(SUPER, {**BEST, "pushups": 25, "inverted_row": 6})            # 2 and 0 points -> 1
    assert next(a for a in s["areas"] if a["area"] == "strength")["points"] == 1
    s = bm.score(SUPER, {**BEST, "pushups": 28, "inverted_row": 18})           # 3 and 4 -> 3.5 -> 4 (half up)
    assert next(a for a in s["areas"] if a["area"] == "strength")["points"] == 4


def test_real_player_from_the_galle_sheet():
    # Maheesha Dissanayake, 13/11/2026: 8.15, 2.50 m, 25 push-ups, 6 rows, 3.04 s, 5.85 s, plank 1.28
    s = bm.score(SUPER, {"run_2km": 495, "broad_jump": 250, "pushups": 25, "inverted_row": 6, "sprint_20m": 3.04,
                         "shuttle_5_10_5": 5.85, "plank": 88})
    assert [a["points"] for a in s["areas"]] == [5, 5, 1, 5, 1, 0] and s["total"] == 17 and s["band"] == "red"
    plank = next(t for t in s["tests"] if t["key"] == "plank")
    assert plank["next"] == {"points": 1, "value": 90, "display": "90.00", "unit": "s"}


def test_missing_tests_are_never_estimated_and_bands_use_what_was_done():
    s = bm.score(SUPER, {"run_2km": 485, "sprint_20m": 3.0})
    assert (s["total"], s["max"], s["band"]) == (12, 12, "green") and "Power" in s["note"]


def test_not_scored_for_provincial_girls_or_other_ages():
    assert bm.score(PROVINCIAL, {"bronco": 300}) is None
    assert bm.score(SUPER, BEST, "U17") is None and bm.score(SUPER, BEST, "U15", "female") is not None


def test_band_cut_offs_keep_the_source_proportions():
    assert [b["from"] for b in bm.table()["bands"]] == [31, 26, 20, 0]
    for total, band in ((31, "green"), (30, "light_green"), (26, "light_green"), (25, "amber"), (20, "amber"), (19, "red")):
        assert next(b for c, b, _ in bm.BANDS if total / 34 >= c - 1e-9) == band, total


def test_categorisation_carries_the_benchmark():
    out = cz.categorise([{"player_id": i, "level": SUPER, "finals": {**BEST, "pushups": 20 + i}} for i in range(6)])
    # 20 push-ups (1) with 30 rows (7) -> strength 4 -> 31; 25 push-ups (2) with 7 -> 4.5 -> 5
    assert out[0]["benchmark"]["total"] == 31 and out[5]["benchmark"]["areas"][2]["points"] == 5


def test_benchmark_endpoint(client, world):
    r = client.get("/meta/benchmark", headers=H(world, "coach_a"))
    assert r.status_code == 200 and r.json()["max"] == 34 and len(r.json()["tests"]) == 7
