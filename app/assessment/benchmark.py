"""SLC U15 points benchmark: the men's / U19 points scoring system, adapted to the U15 Super Provincial test battery. Pure module.

The source (SLC "Men's proposed testing standards", points scoring system)
    Skinfolds /7 · 2 km run /7 · CMJ /5 · IMTP relative /7 · 20 m sprint /5 · 5-10-5 pro agility /5 = 36 points
    Totals: 32-36 green · 27-31 light green · 21-26 amber · under 21 red. A result outside the lowest band scores 0.

How the U15 version was made (a PROPOSAL for SLC's coaches; replace with SLC's own U15 data once a few squads are tested)
  1. Same test in both batteries (2 km run, 20 m sprint, 5-10-5): the U19 cut-offs are multiplied by one age factor, 1.08
     (U15 boys are about 8% slower than 18-year-olds over sprint and running distances):
       - pooled adolescent rugby-league data: 20 m sprint 3.37 s at 14 vs 3.10 s at 18 (8.7% slower);
       - track and field development (Tonnessen et al. 2015, PLOS ONE): boys gain about 2-3% a year in running events
         after 14, tapering towards 18 (sum about 8% from 14 to 18);
       - SLC's senior 2 km standard (8:10-8:35) and the 1-point U19 limit (8:30) give a U15 1-point limit of about 9:11,
         consistent with "under 10 minutes" teenage cricket targets.
     The 5-10-5 uses the same factor: change-of-direction speed develops with sprint speed. (The source sheet labels the column
     505 but its times, 4.80-5.50 s, are 5-10-5 pro-agility times.)
  2. Tests the U15 battery does not have are replaced by the U15 test of the same quality:
       - CMJ (power) -> standing broad jump /5. Jump height grows with the square of take-off velocity and jump distance roughly
         with velocity, so the U19 CMJ steps (25, 30, 35, 40, 45 cm) become distance steps of sqrt(h/45): 74.5%, 81.6%,
         88.2%, 94.3%, 100% of the top cut-off. The top is 235 cm, about the 90th-95th percentile of 15-year-old boys
         (FitBack European norms: median 187 cm at 14, 197 cm at 15). 1 point starts at 175 cm, near the age median.
       - IMTP relative strength /7 -> push-ups /7 and inverted row /7, averaged (rounded half up). Push-ups: 1 point at 20
         (the U15 expected value), 7 points at 44 (90th percentile at 15, President's Council norms), steps of 4.
         Inverted row: 1 point at 12, 7 points at 24, steps of 2 - an ESTIMATE (no published youth norms were found).
       - Skinfolds /7 -> NOT USED. Body-fat measurement is not an appropriate target for 14-15-year-olds (the app already
         leaves skinfolds out of minors' plans). Its place is taken by the U15 core test:
       - Standard plank /5: 1 point at 90 s (US National Youth Fitness Survey, boys 12-15: median about 83 s, 75th percentile
         about 122 s), then 120, 150, 180 and 240 s.
  3. Maximum: 7 + 5 + 7 + 5 + 5 + 5 = 34 points. The colour bands keep the source's proportions of the maximum:
     green from 88.9% (32/36), light green from 75% (27/36), amber from 58.3% (21/36), red below.
     When a test is missing, the bands use the maximum of the tests done (never estimated), and the result says so.
Only Super Provincial players are scored (Provincial players do the Bronco only).

Girls and women (U15 girls, U17 girls, U19 women): the same tests, maximum points and colour bands, with the cut-offs built from
the women's age references (age_norms.FEMALE_REFERENCE) by one rule, because no SLC women's standard exists yet:
  1 point at the age group's EXPECTED value (about the median, as the U15 boys' 1-point marks are), the maximum at
  expected + 2.2 x (strong - expected) (strong is about the 75th percentile = +0.67 SD, so this is about +1.5 SD, the 93rd
  percentile, like the boys' top marks), equal steps in between. A PROPOSAL, to be replaced by SLC's women's standards.
"""
from __future__ import annotations

from app.assessment.age_norms import AGE_GROUPS, _ag, is_female, reference
from app.assessment.test_battery import BY_KEY, SUPER, display

AGE_FACTOR = 1.08
# test -> (area, max points, [(cut-off, points), best first]). Lower-is-better tests: result <= cut-off. Others: result >= cut-off.
U15: dict[str, tuple[str, int, list[tuple[float, int]]]] = {
    # 2 km in seconds. U19: <7:30 7 · 7:37 6 · 7:44 5 · 7:52 4 · 8:00 3 · 8:15 2 · 8:30 1  (x 1.08, rounded to the second)
    "run_2km": ("endurance", 7, [(485, 7), (494, 6), (501, 5), (510, 4), (518, 3), (535, 2), (551, 1)]),
    "broad_jump": ("power", 5, [(235, 5), (222, 4), (207, 3), (192, 2), (175, 1)]),
    "pushups": ("strength", 7, [(44, 7), (40, 6), (36, 5), (32, 4), (28, 3), (24, 2), (20, 1)]),
    "inverted_row": ("strength", 7, [(24, 7), (22, 6), (20, 5), (18, 4), (16, 3), (14, 2), (12, 1)]),
    # U19: <=3.00 5 · 3.05 4 · 3.10 3 · 3.15 2 · 3.20 1  (x 1.08)
    "sprint_20m": ("speed", 5, [(3.24, 5), (3.29, 4), (3.35, 3), (3.40, 2), (3.46, 1)]),
    # U19: <4.80 5 · 4.99 4 · 5.15 3 · 5.20 2 · 5.50 1  (x 1.08)
    "shuttle_5_10_5": ("agility", 5, [(5.17, 5), (5.39, 4), (5.56, 3), (5.62, 2), (5.94, 1)]),
    "plank": ("core", 5, [(240, 5), (180, 4), (150, 3), (120, 2), (90, 1)]),
}
# the six scored qualities, in the source sheet's order (strength = push-ups and inverted row together)
AREAS = [("endurance", "Endurance", 7), ("power", "Power", 5), ("strength", "Strength", 7), ("speed", "Speed", 5),
         ("agility", "Agility", 5), ("core", "Core", 5)]
MAX = sum(m for _, _, m in AREAS)                                      # 34
BANDS = [(32 / 36, "green", "Green"), (27 / 36, "light_green", "Light green"), (21 / 36, "amber", "Amber"), (0.0, "red", "Red")]


TOP_FACTOR = 2.2


def _female_table(age_group: str) -> dict[str, tuple[str, int, list[tuple[float, int]]]]:
    out = {}
    for key, (area, mx, _) in U15.items():
        ref = reference(key, age_group, "female")
        if ref is None:
            continue
        t = BY_KEY[key]
        exp, strong = ref[1], ref[2]
        top = exp + TOP_FACTOR * (strong - exp)
        cuts = []
        for pts in range(mx, 0, -1):
            v = exp + (top - exp) * (pts - 1) / (mx - 1)
            cuts.append((round(v, 2) if t.kind == "decimal" and abs(v) < 20 else float(round(v)), pts))
        out[key] = (area, mx, cuts)
    return out


FEMALE = {ag: _female_table(ag) for ag in AGE_GROUPS}


def cut_table(age_group: str | None = "U15", gender: str | None = "male") -> dict | None:
    """The cut-offs that apply: the U15 boys' table, a women's table for female players (U15 / U17 / U19; any other age group
    falls back to U15 girls, as the age references do), else None."""
    if is_female(gender):
        return FEMALE[_ag(age_group)]
    return U15 if (age_group or "U15").upper() == "U15" else None


def points(test_key: str, value: float | None, tbl: dict | None = None) -> int | None:
    tbl = U15 if tbl is None else tbl
    if value is None or test_key not in tbl:
        return None
    t = BY_KEY[test_key]
    for cut, pts in tbl[test_key][2]:
        if (value >= cut) if t.higher_is_better else (value <= cut):
            return pts
    return 0


def next_point(test_key: str, value: float | None, tbl: dict | None = None) -> dict | None:
    """The result that earns the next point (None at the maximum)."""
    tbl = U15 if tbl is None else tbl
    if value is None or test_key not in tbl:
        return None
    t, have = BY_KEY[test_key], points(test_key, value, tbl)
    for cut, pts in reversed(tbl[test_key][2]):
        if pts > have:
            return {"points": pts, "value": cut, "display": display(t, cut), "unit": t.unit}
    return None


def score(level: str, finals: dict, age_group: str | None = "U15", gender: str | None = "male") -> dict | None:
    """The player's benchmark from final (best) results. None when no benchmark applies (Provincial level, boys outside U15)."""
    tbl = cut_table(age_group, gender)
    if level != SUPER or tbl is None:
        return None
    tests = []
    for key, (area, mx, _) in tbl.items():
        v = finals.get(key)
        tests.append({"key": key, "label": BY_KEY[key].label, "area": area, "max": mx, "value": v,
                      "display": display(BY_KEY[key], v), "points": points(key, v, tbl), "next": next_point(key, v, tbl)})
    areas, got, possible = [], 0, 0
    for area, label, mx in AREAS:
        pts = [t["points"] for t in tests if t["area"] == area and t["points"] is not None]
        p = int(sum(pts) / len(pts) + 0.5) if pts else None              # strength: mean of push-ups and inverted row
        areas.append({"area": area, "label": label, "points": p, "max": mx})
        if p is not None:
            got, possible = got + p, possible + mx
    if not possible:
        return None
    share = got / possible
    band, band_label = next((b, lab) for cut, b, lab in BANDS if share >= cut - 1e-9)
    missing = [a["label"] for a in areas if a["points"] is None]
    return {"total": got, "max": possible, "full_max": MAX, "percent": round(100 * share, 1), "band": band, "band_label": band_label,
            "areas": areas, "tests": tests,
            "note": (f"Scored on {possible} of {MAX} points: {', '.join(missing)} not tested (never estimated)." if missing else None)}


def table(age_group: str | None = "U15", gender: str | None = "male") -> dict:
    """The whole benchmark, for the screen (the U15 boys' one, or a women's one for gender='female')."""
    rows = []
    for key, (area, mx, cuts) in (cut_table(age_group, gender) or U15).items():
        t = BY_KEY[key]
        rows.append({"key": key, "label": t.label, "unit": t.unit, "area": area, "max": mx, "better": "higher" if t.higher_is_better else "lower",
                     "cuts": [{"points": p, "value": display(t, c)} for c, p in cuts]})
    return {"tests": rows, "max": MAX, "bands": [{"band": b, "label": lab, "from": int(cut * MAX + 0.999)} for cut, b, lab in BANDS],
            "age_factor": AGE_FACTOR}
