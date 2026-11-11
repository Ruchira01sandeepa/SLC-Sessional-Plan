"""Age-group reference values for the SLC SOP physical tests (U15, U17, U19). Pure module.

Why: a player's result is ranked against squad peers of the same level (categorisation.py). That says nothing when the group
is small, and it does not say whether the result is typical FOR THE PLAYER'S AGE. These references add that second view and
give each age group its own typo-catching range instead of one range for every age.

Each test has three reference points per age group (boys):
    developing ~ 25th percentile   expected ~ 50th percentile   strong ~ 75th percentile
A result is labelled Below reference / Developing / On track / Strong for age. They are REFERENCES, not pass/fail standards,
and they are PROVISIONAL: SLC should replace them with percentiles from its own tested players as data builds up.

Sources (summarised; values were set conservatively for junior cricketers, who are usually not specialist sprinters or jumpers)
  * Standing broad jump: Saint-Maurice et al. 2015 (Hungarian youth norms, boys' medians 175 cm at 13, 195 cm at 15,
    207 cm at 17); Thomas et al. 2020, Eur J Transl Myol (European youth percentiles; lower medians at 17-18).
  * 20 m sprint: pooled data on adolescent male rugby league players (weighted means 3.37 s at 14, 3.11 s at 16,
    3.10 s at 18, SD 0.10-0.17 s; PMC article table). Cricketers are set a little slower.
  * Push-ups: FitnessGram Healthy Fitness Zone, boys (12-25 at 13, 14-30 at 14, 16-35 at 15, 18-35 at 16-17);
    NCA-BCCI U19 male cricketers, North Zone (p10 20, p50 28 reps).
  * Plank: US NHANES National Youth Fitness Survey 2012, boys 12-15 mean about 91 s.
  * 2 km run: BCCI senior standard 8:15 (fast bowlers) to 8:30; junior values set slower and stepped by age.
  * 5-10-5 shuttle, inverted row, Bronco: no usable published youth tables were found. ESTIMATES from adult/athlete
    benchmarks scaled for age, flagged as estimates in the app.
Girls: no reference values are set (none were found for these tests); results of girls are shown without an age label.
"""
from __future__ import annotations

from .test_battery import BY_KEY, display

AGE_GROUPS = ("U15", "U17", "U19")
# test -> age group -> (developing, expected, strong), in STORED units (seconds for mm.ss tests)
REFERENCE: dict[str, dict[str, tuple[float, float, float]]] = {
    "broad_jump":     {"U15": (165, 185, 205), "U17": (180, 200, 220), "U19": (190, 210, 230)},
    "sprint_20m":     {"U15": (3.65, 3.45, 3.25), "U17": (3.45, 3.25, 3.10), "U19": (3.35, 3.18, 3.05)},
    "pushups":        {"U15": (14, 20, 28), "U17": (18, 25, 33), "U19": (20, 28, 36)},
    "inverted_row":   {"U15": (8, 12, 17), "U17": (10, 15, 20), "U19": (12, 17, 23)},
    "shuttle_5_10_5": {"U15": (5.40, 5.10, 4.85), "U17": (5.15, 4.90, 4.65), "U19": (5.00, 4.75, 4.55)},
    "plank":          {"U15": (60, 90, 130), "U17": (75, 110, 150), "U19": (90, 120, 170)},
    "run_2km":        {"U15": (570, 530, 495), "U17": (540, 505, 475), "U19": (525, 490, 460)},
    "bronco":         {"U15": (375, 350, 325), "U17": (360, 335, 310), "U19": (350, 325, 300)},
}
QUALITY = {"broad_jump": "published youth norms", "sprint_20m": "published youth athlete data", "pushups": "published youth norms",
           "plank": "published youth survey (means)", "run_2km": "senior standard, scaled for age",
           "inverted_row": "estimate", "shuttle_5_10_5": "estimate", "bronco": "estimate"}
# typo-catching ranges per age group (stored units). Wider than any real result; outside them the entry is almost certainly a mistake.
PLAUSIBLE: dict[str, dict[str, tuple[float, float]]] = {
    "broad_jump":     {"U15": (80, 290), "U17": (90, 310), "U19": (100, 330)},
    "sprint_20m":     {"U15": (2.7, 6.0), "U17": (2.6, 6.0), "U19": (2.5, 6.0)},
    "pushups":        {"U15": (0, 80), "U17": (0, 90), "U19": (0, 100)},
    "inverted_row":   {"U15": (0, 60), "U17": (0, 70), "U19": (0, 80)},
    "shuttle_5_10_5": {"U15": (4.0, 10.0), "U17": (3.8, 10.0), "U19": (3.6, 10.0)},
    "plank":          {"U15": (5, 480), "U17": (5, 540), "U19": (5, 600)},
    "run_2km":        {"U15": (380, 1200), "U17": (360, 1200), "U19": (340, 1200)},
    "bronco":         {"U15": (240, 900), "U17": (225, 900), "U19": (210, 900)},
}
LABELS = {"below": "Below reference", "developing": "Developing", "on_track": "On track", "strong": "Strong for age"}


def _ag(age_group: str | None) -> str:
    g = (age_group or "U15").upper()
    return g if g in AGE_GROUPS else "U15"


def plausible(test_key: str, age_group: str | None) -> tuple[float, float]:
    t = BY_KEY[test_key]
    return PLAUSIBLE.get(test_key, {}).get(_ag(age_group), (t.lo, t.hi))


def reference(test_key: str, age_group: str | None, gender: str | None = "male") -> tuple[float, float, float] | None:
    if gender not in (None, "male"):
        return None
    return REFERENCE.get(test_key, {}).get(_ag(age_group))


def age_band(test_key: str, value: float | None, age_group: str | None, gender: str | None = "male") -> dict | None:
    """Where a result sits for the player's age group: below / developing / on_track / strong, plus a 0-100 age score
    (25 = developing point, 50 = expected, 75 = strong; straight lines between, clamped to 5-95)."""
    ref = reference(test_key, age_group, gender)
    if ref is None or value is None:
        return None
    t = BY_KEY[test_key]
    dev, exp, strong = ref
    # turn "lower is better" tests round so that bigger always means better
    v, d, e, s = (value, dev, exp, strong) if t.higher_is_better else (-value, -dev, -exp, -strong)
    if v < d:
        score = 25 - 25 * (d - v) / max(e - d, 1e-9)
    elif v < e:
        score = 25 + 25 * (v - d) / (e - d)
    elif v < s:
        score = 50 + 25 * (v - e) / (s - e)
    else:
        score = 75 + 25 * (v - s) / max(s - e, 1e-9)
    score = round(max(5.0, min(95.0, score)), 1)
    band = "below" if v < d else "developing" if v < e else "on_track" if v < s else "strong"
    return {"band": band, "label": LABELS[band], "score": score, "age_group": _ag(age_group), "quality": QUALITY.get(test_key),
            "developing": display(t, dev), "expected": display(t, exp), "strong": display(t, strong), "unit": t.unit}


def table() -> list[dict]:
    """Every reference, for the screen and the documentation."""
    out = []
    for key, by_age in REFERENCE.items():
        t = BY_KEY[key]
        out.append({"test": key, "label": t.label, "unit": t.unit, "higher_is_better": t.higher_is_better, "quality": QUALITY[key],
                    "ages": {ag: {"developing": display(t, v[0]), "expected": display(t, v[1]), "strong": display(t, v[2]),
                                  "plausible": [display(t, x) for x in PLAUSIBLE[key][ag]]} for ag, v in by_age.items()}})
    return out
