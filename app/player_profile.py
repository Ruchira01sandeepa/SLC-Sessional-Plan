"""One player's development profile: what is strong, what needs work, and what shapes the plan. Pure module.

The individual plan (individual_plan.py) is built from this profile, so two players of the same role get different plans when
their results, ratings, growth or history differ. Every input is optional; the profile says which ones it rests on.

Inputs and how they are used
  * SOP test results (categorisation.py): rank inside the player's own level and window, per test and per area. The weakest
    single test of an area decides WHICH exercises are chosen (e.g. weak inverted row -> pulling work, weak push-ups -> pushing).
    The change since the previous window gives a trend (improving / declining).
  * PDP ratings (coach, 1-5; workbook legend: 1-2 area to improve, 3 average, 4-5 strength): physical qualities, cricket skills
    and habits. Used for areas without a test result and for the cricket-skill goals.
  * Screening needs analysis (LOW / MOD / HIGH per physical quality): how much that quality MATTERS for this player. It weights
    the priorities; without it, a role default is used (e.g. trunk and leg power matter most for a fast bowler).
  * Growth: the coach's maturity status, or the height gain between test sessions (cm per year). Growth of about 7 cm a year or
    more is treated as the growth spurt (reported spurt velocities are roughly 7.5-9.7 cm a year). Re-measure every 3-4 months.
  * Training age: years playing, from the screening's starting age. New players get easier exercises and smaller targets.

Evidence used for the growth and bowling rules (summarised; the rules are conservative proposals for the coach):
  * NSCA position statement on long-term athletic development (Lloyd et al., J Strength Cond Res 2016; 30(6):1491-1509):
    individualised, non-linear pathways; integrated neuromuscular training; monitor and progress systematically.
  * Injury risk rises around peak height velocity, and strength and power develop unevenly during it; maturity should be
    re-estimated every 3-4 months in season (reviews of youth athletes around PHV).
  * Cricket Australia junior pace-bowling guidelines: the 18 months after peak height velocity carry the highest risk of lumbar
    bone stress injury; taller bowlers and bowling more often in a week raise the risk. Low-back pain -> stop bowling, see a
    doctor or physiotherapist.
Nothing here is a diagnosis. Medical detail is never used: readiness comes only from the workload alerts and availability.
"""
from __future__ import annotations

from datetime import date

from .test_battery import AREA_LABEL, BY_KEY, display

MIDDLE = 50.0
STRENGTH_AT = 70.0
TREND_STEP = 8.0                      # change in rank (0-100) between windows that counts as a real change
GROWTH_SPURT_CM_YR = 7.0
MIN_GROWTH_DAYS = 90                  # height measures closer than this are too noisy to give a rate
PDP_SCORE = {1: 10.0, 2: 30.0, 3: 50.0, 4: 70.0, 5: 90.0}
NEED_WEIGHT = {"LOW": 0.8, "MOD": 1.0, "HIGH": 1.3}

# PDP items not used for minors' plans (body-fat measurement and alcohol are not appropriate goals at U15 / U17)
PDP_EXCLUDED = {("Nutrition", "Skinfolds"), ("Nutrition", "Alcohol intake")}
# Which PDP groups belong to which player role
PDP_GROUPS = {
    "fast_bowler": ["Physical", "Nutrition", "Pace Bowl", "Tactical - Bowling", "Field"],
    "spin_bowler": ["Physical", "Nutrition", "Spin Bowl", "Tactical - Bowling", "Field"],
    "batter": ["Physical", "Nutrition", "Batting to Pace", "Batting to Spin", "Tactical - Batting", "Field"],
    "bat_wicketkeeper": ["Physical", "Nutrition", "Wk", "Batting to Pace", "Batting to Spin", "Tactical - Batting", "Field"],
    "all_rounder": ["Physical", "Nutrition", "Batting to Pace", "Batting to Spin", "Tactical - Batting", "Pace Bowl", "Spin Bowl",
                    "Tactical - Bowling", "Field"],
}
# PDP physical items -> test areas (used when an area has no test result, and as supporting evidence)
PDP_AREA = {"Speed": ["speed"], "Endurance": ["endurance"], "Functional Strength": ["power", "upper_strength", "core"], "Agility": ["agility"]}
# Needs-analysis items -> test areas
NEED_AREA = {
    ("Muscular strength", "Upper body"): ["upper_strength"], ("Muscular strength", "Lower"): ["power"], ("Muscular strength", "Core"): ["core"],
    ("Muscular power", "Upper body"): ["upper_strength"], ("Muscular power", "Lower body"): ["power"], ("Muscular power", "Core"): ["core"],
    ("Reactive strength", "Lower body"): ["agility", "power"],
    ("Speed", "Acceleration"): ["speed"], ("Speed", "Maximum"): ["speed"], ("Speed", "Repeat sprint ability"): ["endurance"],
    ("Energy systems", "ATP-PC"): ["speed"], ("Energy systems", "Anaerobic glycolysis"): ["endurance"],
    ("Energy systems", "Oxidative metabolism"): ["endurance"],
}
# When there is no needs analysis: what matters most for the role (1.0 = normal)
ROLE_IMPORTANCE = {
    "fast_bowler": {"power": 1.2, "core": 1.2, "speed": 1.1},
    "spin_bowler": {"core": 1.2, "upper_strength": 1.1, "agility": 1.05},
    "batter": {"speed": 1.15, "agility": 1.1, "power": 1.1},
    "bat_wicketkeeper": {"agility": 1.25, "power": 1.1, "core": 1.1},
    "all_rounder": {"power": 1.1, "core": 1.1, "speed": 1.1, "endurance": 1.05},
}
# How a strength helps in the player's role (shown so the player knows what to build on)
STRENGTH_USE = {
    "speed": {"fast_bowler": "a fast, rhythmical run-up", "batter": "quick singles and turning ones into twos", "default": "running between the wickets and chasing in the field"},
    "power": {"fast_bowler": "ball speed, if landing and the front-foot brace stay sound", "batter": "range hitting and bat speed", "default": "explosive fielding and throwing"},
    "endurance": {"fast_bowler": "keeping pace and accuracy in the last overs of a spell", "default": "keeping quality late in a long innings or day"},
    "agility": {"bat_wicketkeeper": "quick footwork standing up to the stumps", "default": "fielding: quick turns, dives and recovery"},
    "core": {"fast_bowler": "protecting the back through the delivery stride", "spin_bowler": "a repeatable, balanced action", "default": "balance and control in every skill"},
    "upper_strength": {"spin_bowler": "a strong pivot and spin through the shoulder", "batter": "bat control and power", "default": "throwing strength and shoulder health"},
}


def _age(dob: date | None, today: date) -> int | None:
    if not dob:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def growth(heights: list[tuple[date, float]] | None, maturity_status: str | None, role: str) -> dict:
    """Growth stage from the coach's status, otherwise from the measured growth rate."""
    pts = sorted((d, h) for d, h in (heights or []) if d and h)
    velocity = None
    if len(pts) >= 2:
        last_d, last_h = pts[-1]
        base = next(((d, h) for d, h in reversed(pts[:-1]) if (last_d - d).days >= MIN_GROWTH_DAYS), None)
        if base:
            velocity = round((last_h - base[1]) / ((last_d - base[0]).days / 365.25), 1)
    status = maturity_status if maturity_status in ("pre_phv", "circa_phv", "post_phv") else None
    rapid = velocity is not None and velocity >= GROWTH_SPURT_CM_YR
    if status:
        stage, source = status.replace("_phv", ""), "coach"
    elif rapid:
        stage, source = "circa", "growth rate"
    else:
        stage, source = "unknown", "not known"
    in_spurt = stage == "circa" or rapid
    label = {"pre": "Before the growth spurt", "circa": "In the growth spurt", "post": "After the growth spurt", "unknown": "Growth stage not known"}[stage]
    notes = []
    if in_spurt:
        notes.append("Growth spurt: jumps, hops and sprint volume are kept low, landing, mobility, trunk and calf / hamstring work is emphasised and "
                     "the season's load peak is lower. Watch for knee or heel pain during growth and refer to the physiotherapist.")
    elif stage == "pre":
        notes.append("Before the growth spurt: emphasis on speed, agility and movement skill; strength with bodyweight and good technique.")
    elif stage == "post":
        notes.append("After the growth spurt: strength targets can progress further when technique is sound.")
    else:
        notes.append("Growth stage not known: record height at every test (every 3-4 months) or set the maturity status on the player's profile.")
    bowling_window = role in ("fast_bowler", "all_rounder") and (in_spurt or stage == "post")
    if bowling_window:
        notes.append("Fast bowling in or soon after the growth spurt: Cricket Australia reports the highest risk of lumbar bone stress injury in the "
                     "18 months after peak growth. Training overs are one fewer per bowling day. Any low-back pain: stop bowling and refer.")
    return {"stage": stage, "label": label, "source": source, "velocity_cm_yr": velocity, "rapid": rapid, "in_spurt": in_spurt,
            "bowling_window": bowling_window, "measures": len(pts), "latest_height_cm": pts[-1][1] if pts else None, "notes": notes}


def training_age(age: int | None, start_age: int | None) -> dict:
    if age is None or start_age is None or start_age > age:
        return {"years": None, "band": "unknown", "label": "Years playing not recorded (add the starting age in the screening)"}
    yrs = age - start_age
    band = "new" if yrs < 2 else "developing" if yrs < 5 else "experienced"
    return {"years": yrs, "band": band, "label": f"{yrs} year(s) playing ({band})"}


def _importance(role: str, needs: dict | None) -> tuple[dict, str]:
    if needs:
        imp: dict[str, float] = {}
        for (cat, item), level in needs.items():
            for area in NEED_AREA.get((cat, item), []):
                imp[area] = max(imp.get(area, 0), NEED_WEIGHT.get(level, 1.0))
        if imp:
            return imp, "screening needs analysis"
    return dict(ROLE_IMPORTANCE.get(role, {})), "role default"


def build_profile(*, player: dict, cat: dict | None, prev_cat: dict | None = None, pdp: dict | None = None, needs: dict | None = None,
                  heights: list | None = None, screening: dict | None = None, today: date | None = None) -> dict:
    """player: {name, role, date_of_birth?, maturity_status?}. cat / prev_cat: categorisation results (this and the previous window).
    pdp: {(group, skill): rating 1-5} latest ratings. needs: {(category, item): LOW|MOD|HIGH}. heights: [(date, cm)].
    screening: {start_age, this_year_objective, strong_areas, dislike_areas}."""
    today = today or date.today()
    role = player["role"]
    age = player.get("age", _age(player.get("date_of_birth"), today))
    pdp = {k: v for k, v in (pdp or {}).items() if k not in PDP_EXCLUDED and v}
    importance, importance_source = _importance(role, needs)
    prev_areas = {a["area"]: a["percentile"] for a in (prev_cat or {}).get("areas", []) if a.get("percentile") is not None}

    areas = []
    cat_areas = (cat or {}).get("areas", []) if cat and cat.get("overall") is not None else []
    known = {a["area"] for a in cat_areas}
    pdp_area: dict[str, list[int]] = {}
    for (group, skill), r in pdp.items():
        if group == "Physical":
            for a in PDP_AREA.get(skill, []):
                pdp_area.setdefault(a, []).append(r)
    for a in cat_areas:
        tests = [t for t in a.get("tests", []) if t.get("percentile") is not None]
        weakest = min(tests, key=lambda t: t["percentile"]) if tests else None
        areas.append({"area": a["area"], "label": a["label"], "percentile": a["percentile"], "source": "test",
                      "tests": [{"key": t["key"], "label": t["label"], "percentile": t.get("percentile"), "value": t.get("value"), "display": t.get("display")} for t in a.get("tests", [])],
                      "weakest_test": weakest["key"] if weakest else None})
    for area, ratings in pdp_area.items():                          # areas with no test result: use the coach's rating
        if area not in known:
            r = min(ratings)
            areas.append({"area": area, "label": AREA_LABEL[area], "percentile": PDP_SCORE[r], "source": "coach rating", "tests": [], "weakest_test": None})
    for a in areas:
        p, prev = a["percentile"], prev_areas.get(a["area"])
        a["importance"] = round(importance.get(a["area"], 1.0), 2)
        a["trend"] = None if p is None or prev is None else ("improving" if p - prev >= TREND_STEP else "declining" if prev - p >= TREND_STEP else "stable")
        a["previous_percentile"] = prev
        coach = pdp_area.get(a["area"])
        a["coach_rating"] = min(coach) if coach else None
        if p is None:
            a["status"] = "untested"
        elif p < MIDDLE:
            a["status"] = "priority"
        elif p >= STRENGTH_AT and a["trend"] != "declining":
            a["status"] = "strength"
        else:
            a["status"] = "solid"
        if a["status"] in ("solid", "strength") and a["coach_rating"] is not None and a["coach_rating"] <= 2:
            a["status"] = "solid"
            a["note"] = "Tests well, but the coach rates it low: check technique and how it transfers to cricket."
        elif a["trend"] == "declining":
            a["note"] = f"Dropped since the last test (rank {prev:g} to {p:g}); watch it."
        else:
            a["note"] = None
        # priority weight: the bigger the gap below the middle and the more it matters for this player, the more work
        gap = (MIDDLE - p + 10) if p is not None and p < MIDDLE else 0
        a["weight"] = round(gap * a["importance"] * (1.15 if a["trend"] == "declining" else 1.0), 1)
        if a["status"] == "strength":
            uses = STRENGTH_USE.get(a["area"], {})
            a["use"] = uses.get(role) or uses.get("default")
    order = {"priority": 0, "solid": 1, "untested": 2, "strength": 3}
    areas.sort(key=lambda a: (order[a["status"]], -(a["weight"] or 0), a["percentile"] if a["percentile"] is not None else 101))

    skills = []
    for group in PDP_GROUPS.get(role, []):
        if group == "Physical":
            continue
        for (g, skill), r in pdp.items():
            if g != group or (g == "Physical"):
                continue
            status = "priority" if r <= 2 else "strength" if r >= 4 else "solid"
            skills.append({"group": group, "skill": skill, "rating": r, "status": status,
                           "domain": "habits" if group == "Nutrition" else "cricket"})
    for (g, skill), r in pdp.items():                                  # recovery habits sit in the Physical group
        if g == "Physical" and skill == "Recovery practices":
            skills.append({"group": g, "skill": skill, "rating": r, "status": "priority" if r <= 2 else "strength" if r >= 4 else "solid", "domain": "habits"})
    skills.sort(key=lambda s: (s["rating"], s["group"], s["skill"]))

    gr = growth(heights, player.get("maturity_status"), role)
    ta = training_age(age, (screening or {}).get("start_age"))
    strengths = [a for a in areas if a["status"] == "strength"] + [s for s in skills if s["status"] == "strength"]
    priorities = [a for a in areas if a["status"] == "priority"] + [s for s in skills if s["status"] == "priority"]
    inputs = {"tests": bool(cat_areas), "previous_window": bool(prev_areas), "coach_ratings": bool(pdp), "needs_analysis": importance_source != "role default",
              "growth": gr["measures"] >= 2 or gr["source"] == "coach", "training_age": ta["years"] is not None}
    missing = [label for key, label in (("tests", "test results for this window"), ("coach_ratings", "PDP ratings (Development ratings card)"),
                                        ("needs_analysis", "a screening needs analysis"), ("growth", "height at two tests at least 3 months apart, or the maturity status"),
                                        ("training_age", "the age the player started (screening)")) if not inputs[key]]
    return {"player": player["name"], "role": role, "age": age, "areas": areas, "skills": skills, "strengths": strengths, "priorities": priorities,
            "importance_source": importance_source, "growth": gr, "training_age": ta,
            "objective": (screening or {}).get("this_year_objective"), "inputs": inputs, "missing": missing}


def physical_goal(area: dict, test_key: str, cohort_values: list[float] | None, next_window: str | None) -> dict | None:
    """A measurable target for the weakest test of a priority area: the result that would place the player about 15 rank points
    higher in today's group (at least the middle, at most rank 75), and never more than an 8% change in one window."""
    t = BY_KEY.get(test_key)
    cur = next((x for x in area["tests"] if x["key"] == test_key), None)
    if not t or not cur or cur.get("value") is None:
        return None
    value, pct = cur["value"], cur.get("percentile") or 0
    goal_pct = min(75.0, max(MIDDLE, pct + 15))
    target = None
    vals = sorted(v for v in (cohort_values or []) if v is not None)
    if len(vals) >= 5:
        ranked = vals if t.higher_is_better else list(reversed(vals))          # worst -> best
        idx = min(len(ranked) - 1, max(0, int(round(goal_pct / 100 * len(ranked))) - 1))
        target = ranked[idx]
    step = 0.08 * value
    better = (lambda a, b: a > b) if t.higher_is_better else (lambda a, b: a < b)
    if target is None or not better(target, value):
        target = value * (1.03 if t.higher_is_better else 0.97)
    if abs(target - value) > step:
        target = value + step if t.higher_is_better else value - step
    if t.kind == "count":
        target = float(int(target) + (1 if t.higher_is_better and int(target) <= value else 0))
    return {"kind": "test", "area": area["area"], "label": f"{t.label}: {display(t, value)} to {display(t, target)} {t.unit}",
            "test": t.key, "current": value, "target": round(target, 2), "unit": t.unit, "current_display": display(t, value),
            "target_display": display(t, target), "by": next_window,
            "why": f"{area['label']} is a priority (rank {area['percentile']:g} of 100); {t.label.lower()} is its weakest test."}
