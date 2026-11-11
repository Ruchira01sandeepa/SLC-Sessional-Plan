"""Categorise players from their SOP test results. Pure module (no database, no Excel).

How it works
  * Players are compared ONLY with other players of the same level (Provincial or Super Provincial) in the same test window.
    There are no adult or international standards, and Bronco and 2 km are never compared with each other.
  * Each test gives a percentile inside the cohort: 100 = best, direction-aware (a faster time or more reps is better), mid-rank for ties.
    A test needs at least MIN_COHORT players with a result, otherwise it has no percentile and is not used.
  * Tests are grouped into areas (endurance, leg power, upper-body strength, speed, agility, core). An area is the average of its tests.
  * The overall score is the average of the areas the player has. It maps to 5 equal bands (20 points each).
    A missing test is left out, never estimated, and the profile says how many areas the band rests on.
  * Focus areas are every area below the middle (percentile under 50), weakest first.
  * Readiness (ready / caution / hold) comes from the workload alerts. It is separate from the band and never changes it;
    it only limits how much load the player's plan may carry.
Everything here is a PROPOSAL for the coaches. Nothing is a pass or fail mark.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .test_battery import AREA_LABEL, BY_KEY, areas_for, display

MIN_COHORT = 5                          # same minimum as fitness_metrics.MIN_SQUAD_FOR_PERCENTILE
BAND_NAMES = ("Developing", "Emerging", "Competent", "Advanced", "Elite")      # placeholder names; relative to the cohort only
BANDS = len(BAND_NAMES)
MIDDLE = 50.0


def percentile(value: float, values: list[float], higher_is_better: bool) -> float | None:
    if value is None or len(values) < MIN_COHORT:
        return None
    worse = sum(1 for v in values if (v < value if higher_is_better else v > value))
    equal = sum(1 for v in values if v == value)
    return round(100 * (worse + 0.5 * equal) / len(values), 1)


def band_of(overall: float) -> int:
    """1 (lowest) to 5. Equal 20-point slices; 100 belongs to band 5."""
    return min(BANDS, int(overall // (100 / BANDS)) + 1)


def categorise(entries: list[dict]) -> dict[int, dict]:
    """entries: [{player_id, level, finals: {test_key: value}}] for ONE season and window. Returns {player_id: result}."""
    by_level: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_level[e["level"]].append(e)

    out: dict[int, dict] = {}
    for level, cohort in by_level.items():
        values = {k: [e["finals"][k] for e in cohort if e["finals"].get(k) is not None] for k in BY_KEY}
        for e in cohort:
            areas = []
            for area in areas_for(level):
                tests = []
                for t in (t for t in BY_KEY.values() if level in t.levels and t.area == area):
                    v = e["finals"].get(t.key)
                    tests.append({"key": t.key, "label": t.label, "unit": t.unit, "value": v, "display": display(t, v),
                                  "percentile": percentile(v, values[t.key], t.higher_is_better) if v is not None else None})
                got = [x["percentile"] for x in tests if x["percentile"] is not None]
                areas.append({"area": area, "label": AREA_LABEL[area], "percentile": round(mean(got), 1) if got else None, "tests": tests})
            scored = [a for a in areas if a["percentile"] is not None]
            overall = round(mean(a["percentile"] for a in scored), 1) if scored else None
            band = band_of(overall) if overall is not None else None
            focus = sorted((a for a in scored if a["percentile"] < MIDDLE), key=lambda a: a["percentile"])
            note = None
            if overall is None:
                note = (f"No band yet: a test needs results from at least {MIN_COHORT} {level.replace('_', ' ')} players "
                        f"in this window, and this player's results are missing or the group is too small.")
            elif len(scored) < len(areas):
                note = f"Band rests on {len(scored)} of {len(areas)} areas; the missing tests were left out, not estimated."
            elif len(areas) == 1:
                note = "Only one area is ranked at this level, so the band shows that area only."
            out[e["player_id"]] = {
                "player_id": e["player_id"], "level": level, "areas": areas, "overall": overall,
                "band": band, "band_label": BAND_NAMES[band - 1] if band else None,
                "areas_counted": len(scored), "areas_total": len(areas),
                "focus_areas": [{"area": a["area"], "label": a["label"], "percentile": a["percentile"]} for a in focus],
                "note": note, "cohort_size": len(cohort),
            }
    return out


def readiness(alerts_worst: str | None, availability: str) -> dict:
    """Ready / caution / hold from the workload alerts and the coarse availability. Never contains medical detail."""
    if availability == "unavailable" or alerts_worst == "stop":
        return {"status": "hold", "label": "Hold",
                "reason": "A stop alert is open or the player is unavailable. No new load is planned until a coach or physiotherapist clears the player."}
    if availability == "modified" or alerts_worst == "warn":
        return {"status": "caution", "label": "Caution",
                "reason": "A warning is open or the player is on modified training. The plan carries a lower load."}
    return {"status": "ready", "label": "Ready", "reason": "No open workload warnings. The plan carries the normal load."}
