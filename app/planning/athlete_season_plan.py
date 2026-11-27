"""Individual seasonal (macrocycle) plan for ONE athlete, built step by step on Zatsiorsky & Kraemer, Science and Practice of
Strength Training (2nd ed.): ch. 1 (overload, accommodation, specificity, individualization; the two-factor fitness-fatigue model)
and ch. 5 (timing: structural units, mesocycle types, periodization, rule of 60%, taper), with ch. 10 for young athletes.

The coach answers STEP 0 first (prefilled from the app where it can be); every later step shows its work, STEP 15 is the output in
the order the method asks for, and STEP 16 is a self-check the code really evaluates. Pure module: no database.
Every number is a PROPOSAL for the coach.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.reference.exercise_kinds import PHASE_KINDS
from app.planning.individual_plan import _pick

SOURCE = "Zatsiorsky & Kraemer, Science and Practice of Strength Training, 2nd ed., ch. 1 and ch. 5 (with ch. 10, young athletes)"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ───────────── STEP 0: the questions ─────────────
QUESTIONS = [
    (1, "Sport and event/position."),
    (2, "Athlete's age, sex, body weight, training age (years of serious training), level (beginner / qualified / elite)."),
    (3, "Competition calendar: dates of ALL competitions; mark which are MAIN (must peak), which are secondary (used as tests), "
        "and how long each competition lasts (days)."),
    (4, "Start date of the plan and total weeks available."),
    (5, "Training days per week and sessions per day available."),
    (6, "Current test results and the competition result in the main sport exercise."),
    (7, "Which motor abilities limit performance (max strength, explosive strength/power, hypertrophy, anaerobic, aerobic, speed, "
        "flexibility, technique)."),
    (8, "Injuries, recovery problems, equipment limits, school/work/exam periods."),
    (9, "How last season went (did the athlete peak on time? what loads were used?) and how much the load will rise this season."),
]
LEVELS = {"beginner": "Beginner", "qualified": "Qualified", "elite": "Elite"}
ABILITY = {"max_strength": "Maximal strength", "power": "Explosive strength / power", "hypertrophy": "Hypertrophy (muscle size)",
           "anaerobic": "Anaerobic capacity", "aerobic": "Aerobic endurance", "speed": "Speed", "flexibility": "Flexibility",
           "technique": "Technique"}
# Superposition (ch. 5): strength-type abilities first, aerobic endurance last (strength work harms endurance more than the reverse).
SUPERPOSITION = ["hypertrophy", "max_strength", "power", "speed", "anaerobic", "aerobic", "flexibility"]
INCREASE = {"mild": ("Mild", 2), "normal": ("Normal", 4), "sharp": ("Sharp / stress microcycles used", 6)}
# Test area (the app's battery) -> the ability a low rank points to.
AREA_ABILITY = {"power": "power", "upper_strength": "max_strength", "speed": "speed", "agility": "speed", "endurance": "aerobic", "core": "max_strength"}
ABILITY_TESTS = {"max_strength": "Push-ups and inverted row (valid reps), standard plank", "hypertrophy": "Body weight, arm and thigh girths",
                 "power": "Standing broad jump", "speed": "20 m sprint, 5-10-5 shuttle", "anaerobic": "5-10-5 shuttle repeated, repeated 20 m sprints",
                 "aerobic": "Bronco / 2 km run", "flexibility": "Screening mobility checks (hips, thoracic spine, shoulders)",
                 "technique": "Video rating of the technique feature"}
# Kinds of exercise that develop each ability; FALLBACK when the period does not allow them (e.g. no plyometrics in accumulation).
ABILITY_KINDS = {"max_strength": ["leg_strength", "upper_strength"], "hypertrophy": ["upper_strength", "leg_strength"],
                 "power": ["plyometric_power", "rotation_power"], "speed": ["speed", "agility"], "anaerobic": ["repeat_sprint", "agility"],
                 "aerobic": ["aerobic", "repeat_sprint"], "flexibility": ["mobility_balance"]}
FALLBACK = {"power": ["landing", "leg_strength"], "speed": ["agility", "landing"], "anaerobic": ["agility", "aerobic"],
            "aerobic": ["agility"], "flexibility": ["mobility_balance", "trunk_stability"]}
KIND_AREA = {"leg_strength": "power", "plyometric_power": "power", "landing": "agility", "mobility_balance": "agility", "upper_strength": "upper_strength",
             "shoulder_prehab": "upper_strength", "grip_wrist": "upper_strength", "rotation_power": "core", "trunk_stability": "core",
             "speed": "speed", "agility": "agility", "repeat_sprint": "endurance", "aerobic": "endurance", "lower_limb_resilience": "power"}
KIND_ORDER = {"speed": 0, "plyometric_power": 0, "rotation_power": 1, "agility": 1, "repeat_sprint": 2, "leg_strength": 3, "upper_strength": 3,
              "landing": 4, "aerobic": 5, "trunk_stability": 6, "lower_limb_resilience": 7, "shoulder_prehab": 7, "grip_wrist": 7, "mobility_balance": 8}
HEAVY = {"leg_strength", "upper_strength"}
EXPLOSIVE = {"plyometric_power", "rotation_power", "speed"}
HEAVY_LEGS = {"leg_strength", "plyometric_power", "speed", "repeat_sprint"}
ENDURANCE = {"aerobic"}
EX_PHASE = {"accumulation": "pre_season", "transmutation": "pre_competition", "realization": "pre_competition",
            "competition": "in_season", "transition": "transition"}
MESO_LABEL = {"accumulation": "Accumulation", "transmutation": "Transmutation", "realization": "Realization (precompetition)",
              "competition": "Competition", "transition": "Transition"}
PERIOD = {"accumulation": "Preparation", "transmutation": "Preparation", "realization": "Preparation (taper)", "competition": "Competition",
          "transition": "Transition"}
MESO_VOLUME = {"accumulation": 100, "transmutation": 85, "realization": 65, "competition": 60, "transition": 60}
WAVES = {1: [1.0], 2: [1.0, 0.6], 3: [0.85, 1.0, 0.6], 4: [0.8, 0.9, 1.0, 0.6], 5: [0.8, 0.9, 1.0, 0.85, 0.6], 6: [0.8, 0.9, 1.0, 0.85, 0.95, 0.6]}
DAY_WAVE = {1: [1.0], 2: [1.0, 0.6], 3: [1.0, 0.6, 0.8], 4: [1.0, 0.8, 0.6, 0.9], 5: [1.0, 0.7, 0.85, 0.6, 0.9],
            6: [1.0, 0.7, 0.9, 0.6, 0.85, 0.75], 7: [1.0, 0.7, 0.9, 0.6, 0.85, 0.75, 0.65]}
PATTERNS = {1: ["Wed"], 2: ["Mon", "Thu"], 3: ["Mon", "Wed", "Fri"], 4: ["Mon", "Tue", "Thu", "Fri"], 5: ["Mon", "Tue", "Wed", "Fri", "Sat"],
            6: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], 7: DAYS}
RESTORATION = [("Extreme", "72 h or more"), ("Large", "48-72 h"), ("Substantial", "24-48 h"), ("Medium", "12-24 h"), ("Small", "under 12 h")]
TECHNIQUE = {
    "fast_bowler": "bowling action: braced front leg and tall trunk at front-foot contact",
    "spin_bowler": "bowling action: pivot over a firm front leg and full hip-shoulder rotation",
    "batter": "hip-shoulder separation and a stable base in drives and pulls",
    "all_rounder": "bowling action at front-foot contact, then hip-shoulder separation when batting",
    "bat_wicketkeeper": "low crouch, lateral footwork and rise with the ball when keeping; a stable base when batting",
}


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _d(v) -> date | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _blocks(n: int) -> list[int]:
    """n weeks -> mesocycles of about 4 weeks (2-6), never a single week left alone."""
    if n <= 6:
        return [n] if n else []
    out, left = [], n
    while left > 6:
        out.append(4)
        left -= 4
    if left == 1:
        out[-1] += 1
    elif left:
        out.append(left)
    return out


# ───────────── STEP 0: answers + assumptions ─────────────
def resolve_inputs(answers: dict, prefill: dict, today: date) -> tuple[dict, list[str]]:
    """The coach's answers on top of what the app knows; every missing item becomes a stated assumption."""
    a = {**prefill, **{k: v for k, v in (answers or {}).items() if v not in (None, "", [])}}
    assume: list[str] = []
    a.setdefault("sport", "Cricket")
    if not a.get("position"):
        a["position"] = "Cricket player"
        assume.append("Position not given: a general cricket profile is used.")
    if a.get("age") is None:
        a["age"] = 14
        assume.append("Age not given: 14 years (U15) is assumed.")
    if not a.get("sex"):
        a["sex"] = "male"
        assume.append("Sex not given: male is assumed.")
    if not a.get("body_weight_kg"):
        assume.append("Body weight not recorded: body-weight limits in the transition use the next weigh-in.")
    if a.get("training_age_years") in (None, ""):
        a["training_age_years"] = 0.5 if a["age"] < 16 else 1.0
        assume.append(f"Training age not given: {a['training_age_years']:g} year(s) of serious strength training is assumed.")
    if a.get("level") not in LEVELS:
        a["level"] = "beginner" if float(a["training_age_years"]) < 2 or a["age"] < 16 else "qualified"
        assume.append(f"Level not given: {LEVELS[a['level']].lower()} (from age and training age).")
    comps = [c for c in (a.get("competitions") or []) if _d(c.get("start"))]
    for c in comps:
        c["start"] = _d(c["start"])
        c["days"] = max(1, int(c.get("days") or 1))
        c["importance"] = c.get("importance") if c.get("importance") in ("main", "secondary") else "secondary"
        c["end"] = c["start"] + timedelta(days=c["days"] - 1)
        c.setdefault("name", "Competition")
    comps.sort(key=lambda c: c["start"])
    if comps and not any(c["importance"] == "main" for c in comps):
        comps[0]["importance"] = "main"
        assume.append(f"No competition marked MAIN: the first one ({comps[0]['name']}, {comps[0]['start']:%d %b %Y}) is treated as the main peak.")
    if not comps:
        s = _d(a.get("season_start")) or today + timedelta(weeks=12)
        e = _d(a.get("season_end")) or s
        comps = [{"name": a.get("season_name") or "Season", "start": s, "days": (e - s).days + 1, "end": e, "importance": "main"}]
        assume.append(f"No competitions listed: the season ({s:%d %b} - {e:%d %b %Y}) is treated as one main competition.")
    a["competitions"] = comps
    a["plan_start"] = _d(a.get("plan_start")) or today
    if a["plan_start"] > comps[0]["start"]:
        a["plan_start"] = today
    a["training_days"] = int(a.get("training_days") or 0)
    if not 1 <= a["training_days"] <= 7:
        a["training_days"] = 3
        assume.append("Training days not given: 3 S&C days a week (non-consecutive) is assumed.")
    a["sessions_per_day"] = int(a.get("sessions_per_day") or 0)
    if not 1 <= a["sessions_per_day"] <= 3:
        a["sessions_per_day"] = 1
        assume.append("Sessions per day not given: 1 is assumed.")
    lim = [x for x in (a.get("limiting") or []) if x in ABILITY]
    if not lim:
        lim = ["max_strength", "power", "technique"]
        assume.append("Limiting abilities not given and no test ranks below the middle: maximal strength, power and technique are assumed.")
    a["limiting"] = lim
    if a.get("load_increase") not in INCREASE:
        a["load_increase"] = "mild" if a["level"] == "beginner" else "normal"
        assume.append(f"Load increase over last season not given: {INCREASE[a['load_increase']][0].lower()} (from the level).")
    for k in ("injuries", "recovery", "equipment", "sport_result", "last_season_peak", "last_season_loads"):
        a.setdefault(k, "")
    if not a.get("equipment"):
        assume.append("Equipment not given: body weight, bands, medicine balls, light dumbbells and a bar are assumed.")
    if not a.get("last_season_peak"):
        assume.append("Last season not described: no correction for an early or late peak is made.")
    a["school_periods"] = [{"name": p.get("name") or "Exams", "start": _d(p["start"]), "end": _d(p["end"])}
                           for p in (a.get("school_periods") or []) if _d(p.get("start")) and _d(p.get("end"))]
    a["youth"] = a["age"] < 18
    return a, assume


# ───────────── STEP 3: work backward from each main competition ─────────────
def _structure(a: dict) -> tuple[list[date], list[dict], list[dict], list[str]]:
    """-> (week Mondays, mesocycles [{type, weeks: [idx], macro}], macrocycles, notes)."""
    mains = [c for c in a["competitions"] if c["importance"] == "main"]
    # main competitions closer than 6 weeks share one macrocycle (one peak, the tournament as one competition block)
    macros: list[dict] = []
    for c in mains:
        if macros and (c["start"] - macros[-1]["comps"][-1]["end"]).days < 42:
            macros[-1]["comps"].append(c)
        else:
            macros.append({"comps": [c]})
    last_end = macros[-1]["comps"][-1]["end"]
    end = max(_d(a.get("plan_end")) or last_end, last_end + timedelta(days=21))   # at least 3 transition weeks after the last peak
    m0 = _monday(a["plan_start"])
    weeks: list[date] = []
    d = m0
    while d <= end:
        weeks.append(d)
        d += timedelta(days=7)
    wi = lambda day: (_monday(day) - m0).days // 7
    _, r_target = INCREASE[a["load_increase"]]
    mesos: list[dict] = []
    notes: list[str] = []
    start = 0
    for k, mac in enumerate(macros):
        first, last = mac["comps"][0], mac["comps"][-1]
        cw0, cw1 = wi(first["start"]), wi(last["end"])
        prep = list(range(start, cw0))
        W = len(prep)
        mac.update({"number": k + 1, "prep_weeks": W})
        R = min(r_target, W)
        rest = W - R
        if 0 < rest < 4 and R > 2:                       # leave room for a transmutation before the taper
            shift = min(R - 2, 4 - rest)
            R, rest = R - shift, rest + shift
        if rest == 1:
            R, rest = R + 1, 0
        T = 0 if rest < 2 else rest if rest < 6 else max(2, round(rest * 0.35))   # longer accumulation -> longer transmutation
        A = rest - T
        if A == 1:
            T, A = T + 1, 0
        if R < r_target:
            notes.append(f"Macrocycle {k + 1}: only {W} week(s) before {first['name']} - the realization mesocycle is {R} week(s) "
                         f"instead of the {r_target} the {INCREASE[a['load_increase']][0].lower()} load increase calls for.")
        i = start
        for t, n in (("accumulation", A), ("transmutation", T)):
            for sz in _blocks(n):
                mesos.append({"type": t, "weeks": list(range(i, i + sz)), "macro": k + 1})
                i += sz
        if R:
            mesos.append({"type": "realization", "weeks": list(range(i, i + R)), "macro": k + 1})
            i += R
        mesos.append({"type": "competition", "weeks": list(range(cw0, cw1 + 1)), "macro": k + 1, "comps": mac["comps"]})
        start = cw1 + 1
        if k + 1 < len(macros):                           # a short active rest between two peaks when there is time for it
            nxt = wi(macros[k + 1]["comps"][0]["start"]) - start
            if nxt >= 8:
                mesos.append({"type": "transition", "weeks": [start], "macro": k + 1})
                start += 1
    if start < len(weeks):
        mesos.append({"type": "transition", "weeks": list(range(start, len(weeks))), "macro": len(macros)})
    return weeks, mesos, macros, notes


def _model(a: dict, mesos: list[dict], macros: list[dict]) -> dict:
    P = macros[0]["prep_weeks"]
    comp_days = sum((c["end"] - c["start"]).days + 1 for c in a["competitions"])
    span = (a["competitions"][-1]["end"] - a["competitions"][0]["start"]).days + 1
    n_lim = len([x for x in a["limiting"] if x != "technique"])
    why = []
    if P >= 12 and len(macros) == 1 and n_lim <= 3:
        model = "linear"
        why.append(f"{P} preparation weeks before a single peak: there is time to 'start the season from the long end' with sequential blocks.")
        why.append("Risk handled: non-targeted abilities keep retaining loads so they do not detrain; general gains are given the "
                   "transmutation and realization weeks to turn into cricket performance.")
    else:
        model = "nonlinear"
        if P < 12:
            why.append(f"Only {P} preparation week(s) before the first main competition: too short for sequential blocks.")
        if span > 42:
            why.append(f"The competitions span {span} days: a long season needs abilities kept together, not one after another.")
        if len(macros) > 1:
            why.append(f"{len(macros)} peaks in the calendar.")
        if n_lim > 3:
            why.append(f"{n_lim} limiting abilities: several key abilities must be trained in the same period.")
        why.append("Targets change every ~2 weeks (half a mesocycle); the other abilities are held with retaining loads; contributing "
                   "abilities are trained in the same microcycle but never in the same workout.")
    rotation = None
    if not a["youth"] and a["level"] != "beginner" and a["training_days"] >= 3:
        rotation = ("Weekly rotation (optional): 12-15RM -> 8-10RM -> 4-6RM -> 1-3RM with 1-2 rest days between workouts; a missed session "
                    "pushes the rotation forward; a power day at 30-45% 1RM with release movements (throws, jumps).")
    else:
        rotation = ("Weekly RM rotation is not used: the 4-6RM and 1-3RM zones are near-maximal loads, which ch. 10 does not recommend for "
                    + ("young athletes." if a["youth"] else "beginners."))
    return {"model": model, "why": why, "rotation": rotation, "comp_days": comp_days}


# ───────────── STEP 5: targets ─────────────
def _order(lim: list[str], youth: bool) -> tuple[list[str], list[str]]:
    notes = []
    abil = [x for x in SUPERPOSITION if x in lim]
    if youth and "hypertrophy" in abil:
        abil.remove("hypertrophy")
        if "max_strength" not in abil:
            abil.insert(0, "max_strength")
        notes.append("Hypertrophy is not a target for a young athlete: strength gains come from the nervous system (ch. 10), so maximal "
                     "strength (technique-led) takes its place.")
    if not abil:
        abil = ["max_strength", "power"]
    if len(abil) == 1:
        abil.append("max_strength" if abil[0] != "max_strength" else "power")
    if "max_strength" not in abil and "hypertrophy" not in abil:
        notes.append("Maximal strength is not a limiting ability, but it stays in every complex with retaining loads: power and speed "
                     "are built on it, and a long season loses it otherwise (training residuals).")
    return abil, notes


def _pairs(order: list[str]) -> list[list[str]]:
    """Consecutive pairs in superposition order, never heavy strength with aerobic endurance in one mesocycle (interference)."""
    out, i = [], 0
    while i < len(order):
        p = [order[i]]
        if i + 1 < len(order) and not ({order[i], order[i + 1]} & {"max_strength", "hypertrophy"} and "aerobic" in (order[i], order[i + 1])):
            p.append(order[i + 1])
            i += 2
        else:
            i += 1
        out.append(p)
    if len(out) > 1 and len(out[-1]) == 1:                  # a lone last target shares its mesocycle with a compatible ability
        last = out[-1][0]
        prev = next((x for x in reversed(order[:-1]) if not ({x, last} & {"max_strength", "hypertrophy"} and "aerobic" in (x, last))), None)
        if prev:
            out[-1] = [prev, last]
    return out


def _assign_targets(mesos: list[dict], order: list[str], model: str) -> None:
    """Accumulation: sequential pairs in superposition order (strength-type first, aerobic in a later block).
    Transmutation: the specific abilities (power, speed, anaerobic, then strength). Nonlinear: a new pair every half-mesocycle."""
    acc_pairs = _pairs(order)
    spec = [x for x in ("power", "speed", "anaerobic", "max_strength") if x in order] or order[:2]
    trans_pairs = _pairs(spec)
    k = {"accumulation": 0, "transmutation": 0}
    for m in mesos:
        t = m["type"]
        if t not in k:
            continue
        src = acc_pairs if t == "accumulation" else trans_pairs
        if model == "nonlinear" and len(m["weeks"]) >= 3 and len(src) > 1:     # half-mesocycles of ~2 weeks, each with its own targets
            half = (len(m["weeks"]) + 1) // 2
            m["halves"] = [{"weeks": m["weeks"][:half], "targets": src[k[t] % len(src)]},
                           {"weeks": m["weeks"][half:], "targets": src[(k[t] + 1) % len(src)]}]
            m["targets"] = src[k[t] % len(src)]
            k[t] += 2
        else:
            m["targets"] = src[k[t] % len(src)]
            k[t] += 1
    sport = spec[:2]
    for m in mesos:
        if m["type"] == "realization":
            m["targets"] = sport
        elif m["type"] == "competition":
            m["targets"] = [x for x in ("max_strength", "power") if x in order][:2] or order[:1]
        elif m["type"] == "transition":
            m["targets"] = ["aerobic", "flexibility"]


# ───────────── STEP 7: exercise complexes ─────────────
def _by_kind(kinds: list[str], phase: str, role_groups: list[str], n: int, taken: set, seed: str, used: set) -> list[dict]:
    allowed = [k for k in kinds if k in set(PHASE_KINDS[phase])]
    pools = {k: [e for e in _pick(KIND_AREA[k], phase, role_groups, 10, ctx={"taken": set(taken), "seed": seed + k, "used_before": used})
                 if e["kind"] == k] for k in allowed}
    out: list[dict] = []
    while len(out) < n and any(pools.values()):
        for k in allowed:                                      # one of each kind in turn
            while pools[k] and pools[k][0]["name"] in taken:
                pools[k].pop(0)
            if pools[k] and len(out) < n:
                e = pools[k].pop(0)
                out.append(e)
                taken.add(e["name"])
    return out


def _complex_for(abilities: list[str], phase: str, role_groups: list[str], seed: str, used: set, bowler: bool) -> list[dict]:
    """Two exercises for each ability of the block, then the injury-prevention groups every young athlete trains (trunk, landing /
    lower limb, shoulder for bowlers). About 10 exercises."""
    taken: set = set()
    out = []
    for ab in abilities:
        if ab == "technique":
            continue
        ex = _by_kind(ABILITY_KINDS[ab], phase, role_groups, 2, taken, seed + ab, used)
        if len(ex) < 2:
            ex += _by_kind(FALLBACK.get(ab, []), phase, role_groups, 2 - len(ex), taken, seed + ab + "f", used)
        out += [{**e, "ability": ab} for e in ex]
    for kinds in [["trunk_stability"], ["landing", "lower_limb_resilience"]] + ([["shoulder_prehab"]] if bowler else []):
        if not any(e["kind"] in kinds for e in out):
            ex = _by_kind(kinds, phase, role_groups, 1, taken, seed + "inj", used)
            out += [{**e, "ability": "prevention"} for e in ex]
    return out[:11]


def _dose(e: dict, t: str, a: dict, role: str) -> tuple[str, str, int]:
    """(sets x reps, rest, nominal sets) for this exercise in this mesocycle."""
    k, youth, adv = e["kind"], a["youth"], a["level"] != "beginner"
    retain = role != "Target"
    if t == "transition":
        return "1-2 x 10-15 (body weight)" if k not in ENDURANCE else "20-30 min easy", "as needed", 1
    if k in HEAVY:
        if t == "accumulation":
            d = ("2-3 x 10-12, load you could lift 13-15 times (stop 2-3 reps short)" if youth else
                 "3-4 x 8-12RM, repeated effort (last set close to failure)")
            r = "1.5-2 min (repeated effort, not heavy)"
        elif t == "transmutation":
            d = ("3 x 6-8, load you could lift 10-12 times, every rep fast" if youth and a["age"] < 16 else
                 "3 x 5-6 at a 6-8RM load" if youth else
                 "Max effort: 2-3 singles up, then up to 6 sets x 1-3 at the training weight" if adv else "4-5 x 4-6 at 80-85% 1RM")
            r = "4-5 min between heavy sets (or series of sets with 10-12 min between series)"
        elif t == "realization":
            d = "2 x 6-8, same load" if youth else "3 x 2-3 at 85-90% 1RM"
            r = "4-5 min"
        else:
            d = "2 x 8-10, challenging load (never to failure)" if youth else "2-3 x 3-5 at 80-85% 1RM"
            r = "4-5 min"
        if retain:
            d = "1-2 x " + d.split(" x ", 1)[1] + " (retaining)"
        return d, r, 1 if retain else 3
    if k in EXPLOSIVE or k == "repeat_sprint":
        d = {"accumulation": "2-3 x 5, technique and landing first", "transmutation": "3-5 x 3-5 at maximal speed",
             "realization": "2-3 x 3 at maximal speed", "competition": "2 x 3 at maximal speed"}[t]
        if k == "repeat_sprint":
            d = e.get("rep") and f"{e.get('set') or '2-3'} x {e['rep']}" or "2-3 sets of 4-6 repeated efforts"
        if retain:
            d = "1-2 x 3 (retaining)"
        return d, "3-5 min, full recovery (fresh for every rep)", 1 if retain else 3
    dose = " x ".join(x for x in (e.get("set"), e.get("rep") or e.get("time")) if x) or "2 x 30 s"
    if retain or role == "Injury prevention":
        dose = (dose + " (retaining)") if retain and role != "Injury prevention" else dose
    return dose, e.get("rest") or "30-60 s", 1 if retain or role == "Injury prevention" else 3


def _meso_complex(block: list[dict], m: dict, a: dict) -> tuple[list[dict], float]:
    """The block complex with this mesocycle's emphasis: targets get both exercises at full sets; a retained ability keeps one exercise
    at retaining sets; injury prevention always. Returns (exercises, share of the work on the targets)."""
    t = m["type"]
    out, seen = [], set()
    for e in block:
        ab = e["ability"]
        role = "Injury prevention" if ab == "prevention" else "Target" if ab in m["targets"] else "Retain"
        if role == "Retain" and ab in seen and t != "transition" and ab != "max_strength":   # strength keeps lower + upper body
            continue
        seen.add(ab)
        dose, rest, sets = _dose(e, t, a, role)
        out.append({"name": e["name"], "kind": e["kind"], "ability": ab, "ability_label": ABILITY.get(ab, "Injury prevention"),
                    "role": role, "dose": dose, "rest": rest, "sets": sets})
    cap = {"realization": 5, "competition": 6, "transition": 5}.get(t)
    if cap and len(out) > cap:                     # fewer exercises before and during competition: targets and trunk first
        out = sorted(out, key=lambda e: (e["role"] != "Target", e["role"] != "Injury prevention", KIND_ORDER.get(e["kind"], 9)))[:cap]
    tot = sum(e["sets"] for e in out if e["role"] != "Injury prevention") or 1     # the youth injury-prevention block is not counted
    share = sum(e["sets"] for e in out if e["role"] == "Target") / tot
    return _session_order(out), round(share, 2)


def _session_order(ex: list[dict]) -> list[dict]:
    """Power and fast drills first, large before small, and no two consecutive heavy exercises for the same muscles (lower / upper alternate)."""
    ex = sorted(ex, key=lambda e: KIND_ORDER.get(e["kind"], 9))
    heavy = [e for e in ex if e["kind"] in HEAVY]
    if len(heavy) > 1:
        legs = [e for e in heavy if e["kind"] == "leg_strength"]
        ups = [e for e in heavy if e["kind"] == "upper_strength"]
        alt = []
        while legs or ups:
            if legs:
                alt.append(legs.pop(0))
            if ups:
                alt.append(ups.pop(0))
        i = ex.index(heavy[0])
        ex = [e for e in ex if e not in heavy]
        ex[i:i] = alt
    return ex


# ───────────── STEP 12: microcycles ─────────────
def _restoration(load: float, t: str, legs: bool, a: dict, warmup: bool = False) -> str:
    if warmup or t == "transition":
        return "Small (under 12 h)"
    f = {"accumulation": 1.0, "transmutation": 1.0, "realization": 0.75, "competition": 0.8}[t] * load
    f *= 1.0 if legs else 0.85
    if not a["youth"] and a["level"] != "beginner":
        f *= 1.15
    elif a["youth"]:
        f *= 0.9
    return "Large (48-72 h)" if f >= 0.95 else "Substantial (24-48 h)" if f >= 0.75 else "Medium (12-24 h)" if f >= 0.5 else "Small (under 12 h)"


def _sessions_for(t: str, a: dict, prev: int | None = None) -> int:
    D = a["training_days"]
    cap = 3 if a["youth"] else 5
    if t in ("accumulation", "transmutation"):
        return min(D, cap)
    if t == "realization":
        return min(D, prev or cap)                       # two-factor taper: keep the number of sessions, cut the load inside them
    return min(D, 2)


def microcycle(t: str, complex_: list[dict], n: int, a: dict) -> list[dict]:
    """One sample week: each exercise twice, heavy legs >= 48 h apart, aerobic endurance never in a heavy-strength workout, load varied
    day to day by the rule of 60%. Returns a row per day."""
    D = max(n, 1)
    days = PATTERNS[min(D, 7)][:]
    S = a["sessions_per_day"]
    loads = DAY_WAVE[len(days)]
    # two leg days as far apart as possible (circular week)
    idx = [DAYS.index(d) for d in days]
    leg_days = [days[0]]
    if len(days) > 1:
        best = max(range(1, len(days)), key=lambda j: min(idx[j] - idx[0], 7 - (idx[j] - idx[0])))
        leg_days.append(days[best])
    # heaviest loads on the leg days
    order = sorted(range(len(days)), key=lambda j: (days[j] not in leg_days, j))
    load_of = dict(zip([days[j] for j in order], sorted(loads, reverse=True)))
    sess: dict[str, list[dict]] = {d: [] for d in days}
    legs = [e for e in complex_ if e["kind"] in HEAVY_LEGS]
    endu = [e for e in complex_ if e["kind"] in ENDURANCE]
    other = [e for e in complex_ if e not in legs and e not in endu]
    for e in legs:
        for d in leg_days:
            sess[d].append(e)
    non_leg = [d for d in days if d not in leg_days]
    separate: list[tuple[str, dict]] = []
    spare = max(0, a["training_days"] - len(days))     # training days left over after the S&C sessions
    for e in endu:                                   # endurance: never in a heavy-strength workout (interference)
        targets = list(dict.fromkeys(non_leg))[:2]
        if len(targets) < 2 and spare:
            targets += [f"{d}*" for d in DAYS if d not in days and d != "Sun" and DAYS.index(d) > 0][:min(spare, 2 - len(targets))]
        if len(targets) < 2 and S >= 2:
            targets += [d for d in leg_days if d not in targets][: 2 - len(targets)]
        for d in targets:
            if d.endswith("*"):
                separate.append((d[:-1], e))
            elif d in leg_days:
                separate.append((d, e))
            else:
                sess[d].append(e)
    RES = HEAVY | EXPLOSIVE
    res_count = {d: sum(1 for e in sess[d] if e["kind"] in RES) for d in days}
    for e in sorted(other, key=lambda e: e["kind"] not in RES):   # strength / power first, so every session gets resistance work
        is_res = e["kind"] in RES
        cand = sorted(days, key=(lambda d: (res_count[d], len(sess[d]), DAYS.index(d))) if is_res else (lambda d: (len(sess[d]), DAYS.index(d))))
        first = cand[0]                              # twice a week, never on consecutive sessions for upper-body strength
        second = next((d for d in cand[1:] if abs(DAYS.index(d) - DAYS.index(first)) > 1 or e["kind"] not in HEAVY), cand[1] if len(cand) > 1 else None)
        for d in [first, second] if second else [first]:
            sess[d].append(e)
            if is_res:
                res_count[d] += 1
    single = [e for e in endu if sum(1 for x in sess.values() if e in x) + sum(1 for _, x in separate if x is e) < 2]
    rows = []
    for d in DAYS:
        if d in sess:
            load = load_of[d]
            ex = _session_order(sess[d])
            items = []
            for e in ex:
                items.append({"name": e["name"], "dose": _scaled(e["dose"], load), "rest": e["rest"], "role": e["role"]})
                if e["kind"] in HEAVY and ex.index(e) + 1 < len(ex) and ex[ex.index(e) + 1]["kind"] in HEAVY:
                    items.append({"name": "Shoulder and hip flexibility / relaxation, 1-2 min", "dose": "", "rest": "", "role": "Between heavy drills"})
            heavy_legs = any(e["kind"] in HEAVY_LEGS for e in ex)
            resistance = any(e["kind"] in HEAVY | EXPLOSIVE for e in ex)
            when = "AM (fresh; heavy and fast work first)" if S >= 2 else "One session; S&C at the START of the day's training"
            rows.append({"day": d, "when": when, "load": round(load * 100), "items": items, "heavy_legs": heavy_legs,
                         "restoration": _restoration(load, t, heavy_legs, a), "endurance": any(e["kind"] in ENDURANCE for e in ex),
                         "resistance": resistance})
            for sd, e in separate:
                if sd == d:
                    rows.append({"day": d, "when": "PM (separate workout, 6 h or more later)", "load": 60,
                                 "items": [{"name": e["name"], "dose": e["dose"], "rest": e["rest"], "role": e["role"]}],
                                 "heavy_legs": False, "restoration": "Medium (12-24 h)", "endurance": True, "resistance": False})
        else:
            sep = [e for sd, e in separate if sd == d]
            if sep:
                rows.append({"day": d, "when": "Separate conditioning workout", "load": 60,
                             "items": [{"name": e["name"], "dose": e["dose"], "rest": e["rest"], "role": e["role"]} for e in sep],
                             "heavy_legs": False, "restoration": "Medium (12-24 h)", "endurance": True, "resistance": False})
            else:
                rows.append({"day": d, "when": "", "load": 0, "items": [], "heavy_legs": False,
                             "restoration": "", "endurance": False, "resistance": False, "note": "Cricket skills / rest" if d != "Sun" else "Rest"})
    if single:
        rows.append({"day": "Note", "when": "", "load": 0, "items": [], "heavy_legs": False, "restoration": "", "endurance": False,
                     "resistance": False, "note": "The second aerobic dose of the week comes from cricket training (running between "
                     "the wickets, fielding drills): no spare day for a separate workout."})
    return rows


def _scaled(dose: str, load: float) -> str:
    if load >= 0.95 or not dose:
        return dose
    return f"{dose} - {round(load * 100)}% day: one set fewer" if load <= 0.7 else f"{dose} - {round(load * 100)}% day"


# ───────────── STEP 9 / 10: taper and competition microcycle ─────────────
def taper(comp: dict, complex_: list[dict], days_pattern: list[str], a: dict, today: date) -> list[dict]:
    """The last 14 days before a main competition, day by day."""
    legs_last = None
    rows = []
    for off in range(14, 0, -1):
        d = comp["start"] - timedelta(days=off)
        wd = DAYS[d.weekday()]
        row = {"date": d, "day": wd, "days_out": off, "past": d < today}
        if wd in days_pattern:
            if off >= 11:
                ex = ([e for e in complex_ if e["kind"] == "leg_strength"][:1] + [e for e in complex_ if e["role"] == "Target" and e["kind"] != "leg_strength"][:2]
                      + [e for e in complex_ if e["kind"] == "trunk_stability"][:1])
                legs_last = d if any(e["kind"] in HEAVY for e in ex) else legs_last
                row.update(session="Reduced strength + power (last heavy lower-body work: 10-12 days out)", load=70,
                           restoration="Substantial (24-48 h)")
            elif off >= 4:
                ex = [e for e in complex_ if e["kind"] in EXPLOSIVE or e["kind"] in ("upper_strength", "trunk_stability")][:4]
                row.update(session="Short, fast, low volume: explosive drills, upper body, trunk; no heavy legs", load=55 if off >= 7 else 45,
                           restoration="Medium (12-24 h)")
            else:
                ex = [e for e in complex_ if e["kind"] in EXPLOSIVE][:2]
                row.update(session="Warm-up-type session: activation, 2 x 2-3 fast reps, mobility", load=30, restoration="Small (under 12 h)")
            row["exercises"] = [{"name": e["name"], "dose": "2-3 sets" if a["youth"] else "3-5 sets", "kind": e["kind"]} for e in ex[:4]]
        elif off == 1:
            row.update(session="Activation and mobility only (or travel)", load=15, restoration="Small (under 12 h)", exercises=[])
        else:
            row.update(session="Cricket skills at match speed, short; no S&C", load=40 if off > 3 else 30, restoration="Small (under 12 h)", exercises=[])
        rows.append(row)
    return rows


def competition_microcycle(comp: dict, matches: list[date], a: dict) -> tuple[list[dict], str | None]:
    """The competition microcycle matched to the competition's length: match / recovery / activation / short heavy retaining workout."""
    days = [comp["start"] + timedelta(days=i) for i in range(comp["days"])]
    mset = {m for m in matches if comp["start"] <= m <= comp["end"]}
    note = None
    if not mset:
        mset = set(days[::2])
        note = "Match days are not in the calendar: a match every second day is assumed."
    kind = {}
    for d in days:
        before, after = d + timedelta(days=1) in mset, d - timedelta(days=1) in mset
        kind[d] = ("match" if d in mset else "free" if not before and not after else "after" if after and not before
                   else "between" if after else "before")
    heavy: dict = {}

    def ok_gap(d):
        return all(abs((d - x).days) >= 2 for x in heavy)

    def week_count(d):
        return sum(1 for x in heavy if abs((d - x).days) < 7)

    for d in days:                                            # whole-body heavy workouts on free days, 48 h or more apart
        if kind[d] == "free" and ok_gap(d) and week_count(d) < 2:
            heavy[d] = "full"
    for d in days:                                            # still short: upper body and trunk the day after a match
        if kind[d] == "after" and ok_gap(d) and week_count(d) < 2:
            heavy[d] = "upper"
    mins = "25-40" if a["youth"] else "30-40"
    rows = []
    for d in days:
        if kind[d] == "match":
            r = ("Match", "-")
        elif heavy.get(d) == "full":
            r = (f"Short heavy retaining workout, {mins} min: strength 2 x 8-10 / explosive 2 x 3, trunk", "Substantial (24-48 h)")
        elif heavy.get(d) == "upper":
            r = (f"Recovery for the legs + short heavy retaining workout for upper body and trunk, {mins} min", "Medium (12-24 h)")
        elif kind[d] == "between":
            r = ("Recovery and activation: mobility, easy aerobic, 2-3 fast drills", "Small (under 12 h)")
        elif kind[d] == "after":
            r = ("Recovery: mobility, easy aerobic 15-20 min", "Small (under 12 h)")
        elif kind[d] == "before":
            r = ("Activation only (no heavy work the day before a match)", "Small (under 12 h)")
        else:
            r = ("Cricket skills / active rest", "Small (under 12 h)")
        rows.append({"date": d, "day": DAYS[d.weekday()], "session": r[0], "restoration": r[1], "match": d in mset,
                     "heavy": heavy.get(d)})
    if len(days) >= 7:
        per_week = [sum(1 for r in rows[i:i + 7] if r["heavy"]) for i in range(0, len(rows) - 6, 7)]
        if per_week and min(per_week) < 2:
            note = (note + " " if note else "") + "Matches are close together: fewer than 2 heavy retaining workouts fit in some weeks - add one on the next free day."
    return rows, note


# ───────────── the plan ─────────────
def build_athlete_plan(*, answers: dict, prefill: dict, role: str, role_groups: list[str], today: date,
                       matches: list[date] | None = None, tests: list[dict] | None = None) -> dict:
    a, assume = resolve_inputs(answers, prefill, today)
    weeks, mesos, macros, struct_notes = _structure(a)
    model = _model(a, mesos, macros)
    order, order_notes = _order(a["limiting"], a["youth"])
    _assign_targets(mesos, order, model["model"])
    bowler = role in ("fast_bowler", "spin_bowler", "all_rounder")
    tech = TECHNIQUE.get(role, "the main cricket skill at match speed")

    # ── complexes: one per block, kept for 2-4 months, new at the move to specific work (transmutation) and in transition
    used: set = set()
    blocks: list[dict] = []
    cur = None
    for m in mesos:
        phase = EX_PHASE[m["type"]]
        start_w = m["weeks"][0]
        new = (cur is None or m["type"] == "transition" and cur["type"] != "transition"
               or (m["type"] == "transmutation" and cur["type"] == "accumulation")
               or (m["type"] in ("accumulation", "transmutation") and cur["type"] in ("competition", "transition"))
               or (start_w - cur["start_w"]) >= 17)
        if not new and (start_w - cur["start_w"]) >= 9 and m["type"] == cur["type"] and m["type"] in ("accumulation", "transmutation"):
            new = True                                         # 2+ months on one complex: replace it at the mesocycle boundary
        if new:
            if cur:
                used |= {e["name"] for e in cur["exercises"]}
            abil = order[:4] if m["type"] != "transition" else ["aerobic", "flexibility"]
            if m["type"] != "transition" and "max_strength" not in abil and "hypertrophy" not in abil:
                abil = abil[:3] + ["max_strength"]
            ex = _complex_for(abil, phase, role_groups, f"b{len(blocks)}", used, bowler)
            cur = {"number": len(blocks) + 1, "type": m["type"], "start_w": start_w, "exercises": ex, "phase": phase}
            blocks.append(cur)
        else:                                                      # same complex; drop what this period does not allow
            allowed = set(PHASE_KINDS[phase])
            keep = [e for e in cur["exercises"] if e["kind"] in allowed]
            if len(keep) < len(cur["exercises"]):
                missing = sorted({e["ability"] for e in cur["exercises"] if e["kind"] not in allowed} - {e["ability"] for e in keep})
                for ab in missing:
                    if ab == "prevention":
                        continue
                    keep += [{**e, "ability": ab} for e in _by_kind(ABILITY_KINDS.get(ab, []) + FALLBACK.get(ab, []), phase, role_groups, 1,
                                                                        {x["name"] for x in keep}, f"k{ab}", used)]
                cur = {**cur, "exercises": keep}
        m["block"] = cur["number"]
        m["block_ex"] = cur["exercises"]

    # ── mesocycles with loads, microcycles
    out_mesos, wk_rows = [], []
    num: dict[str, int] = {}
    prev_n = None
    mains = [c for c in a["competitions"] if c["importance"] == "main"]
    seconds = [c for c in a["competitions"] if c["importance"] == "secondary"]
    for i, m in enumerate(mesos, 1):
        t = m["type"]
        num[t] = num.get(t, 0) + 1
        cx, share = _meso_complex(m["block_ex"], m, a)
        n = _sessions_for(t, a, prev_n)
        prev_n = n if t in ("accumulation", "transmutation") else prev_n
        wave = (WAVES[min(len(m["weeks"]), 6)] if t in ("accumulation", "transmutation") else
                [1.0, 0.85, 0.75, 0.7, 0.65, 0.6][-len(m["weeks"]):] if t == "realization" else [1.0] * len(m["weeks"]))
        if len(wave) < len(m["weeks"]):
            wave = [1.0] * (len(m["weeks"]) - len(wave)) + wave
        s, e = weeks[m["weeks"][0]], weeks[m["weeks"][-1]] + timedelta(days=6)
        if t == "competition":
            s, e = m["comps"][0]["start"], m["comps"][-1]["end"]
        elif t == "transition" and i > 1 and mesos[i - 2]["type"] == "competition":
            s = mesos[i - 2]["comps"][-1]["end"] + timedelta(days=1)
        elif i < len(mesos) and mesos[i]["type"] == "competition":
            e = mesos[i]["comps"][0]["start"] - timedelta(days=1)          # the taper runs up to the day before the competition
        halves = [{"from": weeks[h["weeks"][0]], "to": weeks[h["weeks"][-1]] + timedelta(days=6),
                   "targets": [ABILITY[x] for x in h["targets"]]} for h in m.get("halves", [])]
        comps_in = [c for c in a["competitions"] if s <= c["start"] <= e]
        for j, wi in enumerate(m["weeks"]):
            w0 = weeks[wi]
            exam = next((p["name"] for p in a["school_periods"] if p["start"] <= w0 + timedelta(days=6) and p["end"] >= w0), None)
            tg = next((h["targets"] for h in m.get("halves", []) if wi in h["weeks"]), m["targets"])
            sess = n if not exam else max(min(n, 2), 1)
            if wave[j] <= 0.6 and t in ("accumulation", "transmutation"):
                sess = max(2, sess - 1)
            wk_rows.append({"week": wi + 1, "start": w0, "period": PERIOD[t], "mesocycle": i, "meso_type": t,
                            "volume": round(MESO_VOLUME[t] * wave[j]), "sessions": sess, "targets": [ABILITY[x] for x in tg],
                            "exam": exam, "competitions": [f"{c['name']} ({c['importance']})" for c in a["competitions"]
                                                           if w0 <= c["start"] <= w0 + timedelta(days=6)]})
        micro = microcycle(t, cx, n, a) if t != "competition" else []
        comp_micro, comp_note = ([], None)
        if t == "competition":
            comp_micro, comp_note = competition_microcycle({"start": s, "end": e, "days": (e - s).days + 1}, matches or [], a)
        new_complex = i == 1 or m["block"] != mesos[i - 2]["block"]
        reps = sum(_reps(x["dose"]) * (2 if t != "competition" else 1) for x in cx if x["kind"] in HEAVY | EXPLOSIVE)
        out_mesos.append({
            "number": i, "type": t, "label": f"{MESO_LABEL[t]} {num[t]}", "macro": m["macro"], "start": s, "end": e,
            "weeks": len(m["weeks"]), "period": PERIOD[t], "targets": [ABILITY[x] for x in m["targets"]], "halves": halves,
            "technique": _technique(t, tech), "retained": [ABILITY[x] for x in order if x not in m["targets"]],
            "methods": _methods(t, a), "relative_load": MESO_VOLUME[t], "target_share": share, "sessions": n,
            "complex": cx, "block": m["block"], "new_complex": new_complex, "microcycle": micro,
            "competition_microcycle": comp_micro, "competition_note": comp_note,
            "competitions": [{"name": c["name"], "start": c["start"], "importance": c["importance"]} for c in comps_in],
            "est_reps": reps * round(sum(wave) * 1),
        })

    tapers = []
    for c in mains:
        real = next((m for m in out_mesos if m["type"] == "realization" and m["end"] >= c["start"] - timedelta(days=7) and m["start"] <= c["start"]), None)
        src = real or next((m for m in reversed(out_mesos) if m["start"] < c["start"] and m["complex"]), out_mesos[0])
        pattern = PATTERNS[min(max(src["sessions"], 1), 7)]
        tapers.append({"competition": c["name"], "start": c["start"], "rows": taper(c, src["complex"], pattern, a, today)})

    tests_plan = _testing(out_mesos, seconds, order, today)
    steps = _steps(a, assume, macros, mesos, out_mesos, model, order, order_notes, struct_notes, blocks, tech, tests_plan, tests)
    plan = {"source": SOURCE, "generated_on": today, "inputs": _inputs_view(a, tests), "assumptions": assume,
            "model": model, "target_order": [ABILITY[x] for x in order], "macrocycles": [
                {"number": mc["number"], "peak": " + ".join(c["name"] for c in mc["comps"]), "start": mc["comps"][0]["start"],
                 "prep_weeks": mc["prep_weeks"]} for mc in macros],
            "mesocycles": out_mesos, "weeks": wk_rows, "blocks": [{"number": b["number"], "from": weeks[b["start_w"]],
                                                                    "exercises": [e["name"] for e in b["exercises"]]} for b in blocks],
            "tapers": tapers, "testing": tests_plan, "steps": steps,
            "transition": _transition(a, out_mesos), "load_curve": _load_curve(out_mesos), "notes": struct_notes + order_notes}
    plan["self_check"] = self_check(plan, a)
    plan["output"] = OUTPUT
    return plan


OUTPUT = ["1. Summary of inputs + assumptions", "2. Season overview table", "3. Load curve", "4. Exercise complexes (with change dates)",
          "5. Sample microcycles for each mesocycle type", "6. Taper plan (last 2 weeks before each main competition)",
          "7. Competition-period and transition guidelines", "8. Monitoring / adjustment rules"]


def _reps(dose: str) -> int:
    import re
    m = re.match(r"\s*(\d+)(?:-(\d+))?\s*x\s*(\d+)(?:-(\d+))?", dose or "")
    if not m:
        return 0
    s = (int(m.group(1)) + int(m.group(2) or m.group(1))) / 2
    r = (int(m.group(3)) + int(m.group(4) or m.group(3))) / 2
    return round(s * r)


def _technique(t: str, tech: str) -> str:
    return {"accumulation": "Lifting and landing technique: squat, hinge, single-leg and landing mechanics before any load is added",
            "transmutation": f"Transfer to cricket: {tech}", "realization": f"{tech[0].upper() + tech[1:]} at match speed",
            "competition": f"Keep {tech} under match fatigue", "transition": "None (rest from technique work)"}[t]


def _methods(t: str, a: dict) -> list[str]:
    youth = a["youth"] or a["level"] == "beginner"
    return {"accumulation": ["Submaximal effort", "Repeated effort"],
            "transmutation": ["Dynamic effort", "Repeated effort"] if youth else ["Maximal effort", "Dynamic effort"],
            "realization": ["Dynamic effort (low volume)", "Specific exercises"] if youth else ["Maximal effort (low volume)", "Specific exercises"],
            "competition": ["Retaining loads (2 short heavy workouts a week)"], "transition": ["Calisthenics, stretching, aerobic"]}[t]


def _testing(mesos: list[dict], seconds: list[dict], order: list[str], today: date) -> list[dict]:
    out = []
    for m in mesos:
        if m["type"] == "accumulation":
            d = m["end"] - timedelta(days=2)
            out.append({"date": d, "mesocycle": m["label"], "kind": "Tests (unloading week)",
                        "what": "; ".join(ABILITY_TESTS[x] for x in order if x in ABILITY_TESTS)[:300] + "; assistance-exercise results; technique rating",
                        "if_below": "Target ability not improved: keep it as a target in the next mesocycle and check recovery (sleep, soreness); "
                                    "if no gain twice, change the exercises (accommodation) rather than adding volume."})
        elif m["type"] == "transmutation":
            sec = [c for c in seconds if m["start"] <= c["start"] <= m["end"]]
            for c in sec:
                out.append({"date": c["start"], "mesocycle": m["label"], "kind": "Secondary competition (test)", "what": c["name"],
                            "if_below": "Performance below expectation: lengthen the taper by a week if fatigue is high, or keep "
                                        "transmutation one more week if fitness is not yet turned into skill."})
            if not sec:
                out.append({"date": m["end"] - timedelta(days=2), "mesocycle": m["label"], "kind": "Practice match / match simulation (test)",
                            "what": "Unimportant match or match simulation", "if_below": "As above: adjust taper length or extend transmutation."})
    for m in mesos:
        if m["type"] == "competition":
            out.append({"date": m["start"], "mesocycle": m["label"], "kind": "Main competition (judge the realization only by this)",
                        "what": " + ".join(c["name"] for c in m["competitions"]) or "Main competition",
                        "if_below": "Note the taper used (length, last heavy session) and the competition result; next season change the "
                                    "realization length (2 / 4 / 6-7 weeks) by how much the load was raised."})
    return sorted(out, key=lambda x: x["date"])


def _transition(a: dict, mesos: list[dict]) -> dict:
    bw = a.get("body_weight_kg")
    tr = [m for m in mesos if m["type"] == "transition"]
    return {"weeks": sum(m["weeks"] for m in tr), "from": tr[0]["start"] if tr else None,
            "body_weight": (f"Keep body weight between {bw:g} and {bw + 3:g} kg (gain no more than 2-3 kg)." if bw else
                            "Keep body weight stable (gain no more than 2-3 kg) - weigh in at the end of the season."),
            "guidelines": ["No long breaks: inactivity detrains, unbalances the abilities (injury risk) and makes players overestimate "
                           "themselves when they come back.",
                           "2-3 light sessions a week: calisthenics, stretching, aerobic play or another sport (20-30 min).",
                           "Motivated athletes may keep progressing with an adjusted schedule (for example around exams)."]
                          + ([f"{p['name']} ({p['start']:%d %b} - {p['end']:%d %b}): sessions cut to 2 short retaining workouts." for p in a["school_periods"]])}


def _load_curve(mesos: list[dict]) -> list[str]:
    out = []
    for m in mesos:
        out.append(f"{m['label']} ({m['start']:%d %b} - {m['end']:%d %b}): volume {m['relative_load']}% of the heaviest mesocycle; "
                   + {"accumulation": "high volume, moderate intensity; loading weeks then an unloading week at 60% of the heaviest.",
                      "transmutation": "volume lower, intensity and speed higher; specific exercises.",
                      "realization": "taper: sessions kept, load inside each session cut (two-factor model) so fatigue clears and fitness shows.",
                      "competition": "retaining: 2 short heavy workouts a week, matches are the heaviest days.",
                      "transition": "low volume and intensity; active rest."}[m["type"]])
    return out


def _inputs_view(a: dict, tests: list[dict] | None) -> list[dict]:
    comps = "; ".join(f"{c['name']}: {c['start']:%d %b %Y}, {c['days']} day(s), {c['importance'].upper()}" for c in a["competitions"])
    weeks = ((a["competitions"][-1]["end"] - a["plan_start"]).days // 7) + 1
    return [
        {"n": 1, "q": "Sport and position", "a": f"{a['sport']} - {a['position']}"},
        {"n": 2, "q": "Age, sex, body weight, training age, level",
         "a": f"{a['age']} years, {a['sex']}, {a.get('body_weight_kg') or '-'} kg, {float(a['training_age_years']):g} year(s), {LEVELS[a['level']]}"},
        {"n": 3, "q": "Competition calendar", "a": comps},
        {"n": 4, "q": "Plan start and weeks available", "a": f"{a['plan_start']:%d %b %Y}; {weeks} week(s) to the end of the last competition"},
        {"n": 5, "q": "Training days and sessions per day", "a": f"{a['training_days']} day(s) a week, {a['sessions_per_day']} session(s) a day"},
        {"n": 6, "q": "Test results and competition result",
         "a": ("; ".join(f"{t['test']} {t['value']}" + (f" (rank {t['rank']:g})" if t.get("rank") is not None else "") for t in tests or [])
               or "No test results") + (f". Competition result: {a['sport_result']}" if a.get("sport_result") else "")},
        {"n": 7, "q": "Limiting abilities", "a": ", ".join(ABILITY[x] for x in a["limiting"])},
        {"n": 8, "q": "Injuries, recovery, equipment, exam periods",
         "a": "; ".join(x for x in (a["injuries"] and "Injuries: " + a["injuries"], a["recovery"] and "Recovery: " + a["recovery"],
                                    a["equipment"] and "Equipment: " + a["equipment"],
                                    a["school_periods"] and "Exams: " + ", ".join(f"{p['name']} {p['start']:%d %b}-{p['end']:%d %b}" for p in a["school_periods"]))
                        if x) or "None given"},
        {"n": 9, "q": "Last season and load increase",
         "a": f"Peaked on time: {a['last_season_peak'] or 'not stated'}. Loads: {a['last_season_loads'] or 'not stated'}. "
              f"Load increase this season: {INCREASE[a['load_increase']][0]}"},
    ]


def _steps(a, assume, macros, mesos, out_mesos, model, order, order_notes, struct_notes, blocks, tech, tests_plan, tests) -> list[dict]:
    youth = a["youth"]
    lim = ", ".join(ABILITY[x] for x in order)
    first_main = macros[0]["comps"][0]
    S = []
    S.append({"n": 1, "title": "The four adaptation principles", "lines": [
        f"Overload: loads must rise above what this {LEVELS[a['level']].lower()} athlete is used to - by more volume or intensity, or by an "
        "unfamiliar exercise (each new complex is itself an overload).",
        "Accommodation: the same exercise at the same load gives shrinking gains, so the load changes every week (waves) and the exercise "
        f"complex changes {len(blocks)} time(s) across the plan.",
        f"Specificity vs variety: general exercises build the base in accumulation; exercises move closer to {a['position'].lower()} "
        f"movements in transmutation and realization ({tech}). Variety early, specificity late.",
        f"Individualization: targets come from this athlete's own limiting abilities ({lim}), position and calendar - not from another "
        "player's programme.",
        "Loads: STIMULATING in accumulation and transmutation (fitness rises), RETAINING for non-targeted abilities and in competition "
        "(fitness kept), DETRAINING only on purpose in the taper and in transition. The zones are relative to this athlete's level: "
        + ("a beginner's retaining load is low, so small loads still stimulate." if a["level"] == "beginner" else "a qualified athlete needs higher loads to stimulate."),
        "Training model: TWO-FACTOR (fitness-fatigue). Fatigue after a workout is larger but about 3 times shorter-lived than the fitness "
        "gain, so heavy sessions are spaced (48 h or more for heavy legs) and the taper cuts the load so fatigue disappears while the gain remains."]})
    S.append({"n": 2, "title": "Structural units", "lines": [
        "Workout: drills separated by rests of 30 min or less. Training day: one or more workouts.",
        f"Microcycle: 7 days in preparation; in competition the microcycle matches the competition ({first_main['days']} days for {first_main['name']}).",
        "Mesocycle: about 4 weeks (2-6). Macrocycle: preparation + competition + transition.",
        f"Macrocycles: {len(macros)} (" + ("single peak" if len(macros) == 1 else f"{len(macros)} peaks") + f") from the {len([c for c in a['competitions'] if c['importance'] == 'main'])} "
        "main competition(s) in the calendar.",
        "Restoration classes used for every planned workout: " + "; ".join(f"{k} {v}" for k, v in RESTORATION) +
        ". Extreme workouts are not planned" + (" for a young athlete." if youth else " outside stress microcycles.")]})
    l3 = []
    for mc in macros:
        c = mc["comps"][0]
        types = [m for m in out_mesos if m["macro"] == mc["number"]]
        l3.append(f"Macrocycle {mc['number']}: main competition {c['name']} on {c['start']:%d %b %Y}; {mc['prep_weeks']} week(s) available before it. "
                  "Backward: " + " <- ".join(f"{m['label']} ({m['weeks']} wk)" for m in reversed(types) if m["type"] != "transition") + ".")
    _, rt = INCREASE[a["load_increase"]]
    l3.append(f"Realization length: the load rise is {INCREASE[a['load_increase']][0].lower()}, which calls for about {rt} week(s) "
              "(mild 2, normal 4, sharp 6-7).")
    l3 += struct_notes
    S.append({"n": 3, "title": "Work backward from each main competition", "lines": l3,
              "table": [{"weeks": f"{m['start']:%d %b} - {m['end']:%d %b}", "period": m["period"], "mesocycle": m["label"],
                         "goal": _goal(m)} for m in out_mesos]})
    S.append({"n": 4, "title": f"Periodization model: {model['model'].upper()}", "lines": model["why"] + [model["rotation"]]})
    l5 = [f"Order of targets (superposition: strength-type first, aerobic endurance last): {' -> '.join(ABILITY[x] for x in order)}."]
    for m in out_mesos:
        if m["type"] in ("accumulation", "transmutation"):
            h = (" Half-mesocycles: " + "; ".join(f"{x['from']:%d %b}-{x['to']:%d %b}: {' + '.join(x['targets'])}" for x in m["halves"])) if m["halves"] else ""
            l5.append(f"{m['label']}: targets {' + '.join(m['targets'])} + technique ({m['technique']}); about {round(m['target_share'] * 100)}% "
                      f"of the sets on the targets; retained: {', '.join(m['retained']) or '-'}.{h}")
    l5.append("Training residuals: anaerobic qualities fade fastest, aerobic capacity and maximal strength last longer, muscle size is the "
              "most stable. Whatever was built is kept with small retaining loads; the faster an ability was built, the faster it goes.")
    if macros[0]["prep_weeks"] < 12 or (a["competitions"][-1]["end"] - a["competitions"][0]["start"]).days > 42:
        l5.append("Short preseason / long season: maximal-strength loads stay in the competition period (2 short heavy workouts a week), "
                  "otherwise strength is lost.")
    l5 += order_notes
    S.append({"n": 5, "title": "Targets for each mesocycle", "lines": l5})
    l6 = ["Accumulation: submaximal-effort (not to failure) and repeated-effort sets build the muscle and the periphery."]
    if youth or a["level"] == "beginner":
        l6.append("Transmutation: the maximal-effort method is replaced by the dynamic-effort method (light loads moved as fast as possible, "
                  "jumps and medicine-ball throws) - ch. 10 does not recommend near-maximal lifts for "
                  + ("young athletes" if youth else "beginners") + ". This is a deliberate deviation from the conventional sequence.")
    else:
        l6.append("Transmutation: shift to the maximal-effort method (heavier, fewer reps) for neural coordination; repeated-effort and "
                  "maximal-effort emphasis may alternate in 2- or 4-week blocks.")
    l6.append("As the main competition approaches the exercises become MORE SPECIFIC (delayed transmutation): general in accumulation, "
              "cricket-like power and speed in transmutation and realization.")
    S.append({"n": 6, "title": "Sequence of strength methods", "lines": l6})
    l7 = []
    for b in blocks:
        l7.append(f"Complex {b['number']} from {_block_from(b, out_mesos)}: "
                  f"{len(b['exercises'])} exercises - " + ", ".join(e["name"] for e in b["exercises"]))
    l7 += ["Each exercise is done at least twice a week, in the same order every microcycle; the complex is kept for 2-4 months.",
           "Expect a small, temporary drop in performance after a complex change, then improvement once adapted.",
           "Keep the athlete's most effective exercises for the season of the most important competition; do not repeat the same complex "
           "for years."]
    S.append({"n": 7, "title": "Exercise complexes", "lines": l7})
    dev_n = max((m["sessions"] for m in out_mesos if m["type"] in ("accumulation", "transmutation")), default=0)
    l8 = ["Rule of 60%: lightest day about 60% of the heaviest in a microcycle; unloading microcycle about 60% of the heaviest in a "
          "mesocycle; the lightest mesocycle about 60% of the heaviest (realization 65%, competition 60%).",
          "The load varies day to day and week to week; the exercises do not change inside a mesocycle.",
          (f"Gain: {dev_n} heavy resistance workouts a week in development mesocycles (3 or more needed to gain). " if dev_n else "") +
          "Retain: 2 a week in competition.",
          "Recovery by muscle size: large groups 48 h or more (heavy legs twice a week, 72-96 h apart where possible); medium groups can be "
          "trained daily; small muscles (calves, forearms) more than once a day."]
    if a["training_days"] < 3:
        l8.append(f"Only {a['training_days']} training day(s): maximal strength can be retained but hardly gained - add a third day if possible.")
    if a["sessions_per_day"] >= 2 and not youth:
        l8.append("Two sessions a day are available: the same volume split into AM and PM workouts gives larger gains if recovery is enough.")
    if a["training_days"] >= 5:
        l8.append("5-6 days a week: exercises rotate between consecutive sessions so no main lift is repeated on two sessions in a row.")
    l8.append("Stress (impact) microcycles: " + ("not planned for a young or beginner athlete." if youth or a["level"] == "beginner" else
              "only if normal training stops producing gains - at most 3-4 a year, each followed by a light microcycle."))
    for m in out_mesos:
        if m["type"] in ("accumulation", "transmutation") and m["est_reps"]:
            l8.append(f"{m['label']}: about {m['est_reps']} repetitions in the main strength and power exercises (for reference, a first-year "
                      "weightlifter does about 1,000 lifts in a 4-week mesocycle; a young cricketer should be well below that).")
    S.append({"n": 8, "title": "Loads: volume, intensity, frequency", "lines": l8})
    S.append({"n": 9, "title": "Precompetition (realization) phase", "lines": [
        "Compared with preparation: fewer exercises per workout (" + ("6-10 -> 1-4" if youth else "3-6 -> 1-4") + "), fewer sets per exercise ("
        + ("2-3 -> 2" if youth else "4-8 -> 3-5") + "), the number of sessions kept and the load inside each session cut (two-factor taper).",
        "Priority: full recovery between workouts.",
        "Heavy lower-body work stops 10-12 days before the main competition (as for track and field: a running sport).",
        "Warm-up-type sessions in the last 3 days. The day-by-day taper is in the output (section 6)."]})
    S.append({"n": 10, "title": "Competition period", "lines": [
        "Strength is retained with 2 short heavy workouts a week (" + ("25-40" if youth else "30-40") + " min), never the day before a match.",
        f"The competition microcycle matches the competition's length ({first_main['days']} days).",
        "No more than 3 days of complete passive rest in a row (normally 1-2): recovery days are active (mobility, easy aerobic).",
        "Secondary competitions are used as tests; the plan is adjusted if results are off track."]})
    S.append({"n": 11, "title": "Transition period", "lines": ["No long breaks."] + _transition(a, out_mesos)["guidelines"]
              + [_transition(a, out_mesos)["body_weight"]]})
    S.append({"n": 12, "title": "Microcycles", "lines": [
        "One sample week per mesocycle type is in the output (section 5): day, AM/PM, exercises with sets x reps and load, rest, restoration class.",
        "Heavy, neural and power work in the morning or at the start of the day when fresh; heavy strength as its own workout when strength is "
        "a key ability, or at the START of a mixed session.",
        "No circuit training for strength goals."]})
    S.append({"n": 13, "title": "Workout design rules", "lines": [
        "Order: main exercises before assistance; power and fast drills before slow strength exercises; large muscle groups before small.",
        "For strength, no two consecutive exercises for the same muscles (lower and upper body alternate).",
        ("Heavy sets: 4-5 min rest; if time is short, sets are grouped into series with 10-12 min between series. No pyramids."
         if not youth else "Heavy and explosive sets: full recovery (3-5 min); repeated-effort sets 1.5-2 min. No pyramids, no singles near the maximum."),
        "A fatigued athlete: drop to an easier set (10-15% lighter) between the hard ones rather than forcing the planned load.",
        "Flexibility / relaxation (shoulders, hips) between heavy drills.",
        "As much work as possible while as fresh as possible: strength workouts never need to exhaust the athlete."]})
    S.append({"n": 14, "title": "Testing and monitoring", "lines": [
        "Accumulation: judged by tests, assistance-exercise results and technique.",
        "Transmutation: judged by results in unimportant (secondary) competitions.",
        "Realization: judged only by the main competition result."] +
        [f"{t['date']:%d %b %Y} - {t['kind']}: {t['what']}" for t in tests_plan]})
    return S


def _block_from(b: dict, mesos: list[dict]) -> str:
    m = next((m for m in mesos if m["block"] == b["number"]), None)
    return f"{m['start']:%d %b %Y} ({m['label']})" if m else ""


def _goal(m: dict) -> str:
    return {"accumulation": "Raise potential: " + " + ".join(m["targets"]) + "; technique",
            "transmutation": "Turn fitness into cricket preparedness: " + " + ".join(m["targets"]),
            "realization": "Taper: let fatigue clear so fitness shows",
            "competition": "Perform; retain strength and power", "transition": "Active rest"}[m["type"]]


# ───────────── STEP 16: self-check ─────────────
def self_check(plan: dict, a: dict) -> list[dict]:
    ms = plan["mesocycles"]
    out = []

    def add(item, ok, detail):
        out.append({"item": item, "ok": ok, "detail": detail})

    # 1 realization before each main comp
    bad = []
    for mc in plan["macrocycles"]:
        mm = [m for m in ms if m["macro"] == mc["number"]]
        ci = next((i for i, m in enumerate(mm) if m["type"] == "competition"), None)
        if ci is None or ci == 0 or mm[ci - 1]["type"] != "realization":
            bad.append(f"{mc['peak']}: {mc['prep_weeks']} week(s) available, no room for a realization mesocycle")
    _, rt = INCREASE[a["load_increase"]]
    short = [r for r in ms if r["type"] == "realization" and r["weeks"] < rt]
    add("Realization mesocycle directly before each MAIN competition, length matched to the load increase",
        not bad, "; ".join(bad) if bad else ("Yes" + (f" (shorter than {rt} weeks where the calendar does not allow more)" if short else "")))
    # 2 order
    rank = {"accumulation": 0, "transmutation": 1, "realization": 2, "competition": 3, "transition": 4}
    ok = all([rank[m["type"]] for m in ms if m["macro"] == k and m["type"] != "transition"] ==
             sorted(rank[m["type"]] for m in ms if m["macro"] == k and m["type"] != "transition") for k in {m["macro"] for m in ms})
    add("Accumulation -> transmutation -> realization order respected", ok, "Yes, in every macrocycle" if ok else "Order broken")
    # 3 targets
    dev = [m for m in ms if m["type"] in ("accumulation", "transmutation")]
    n_ok = all(len(m["targets"]) <= 2 for m in ms)
    shares = [m["target_share"] for m in dev]
    s_ok = all(0.68 <= s <= 0.82 for s in shares)
    add("At most 2-3 targets per mesocycle; 70-80% of the work on the targets", n_ok and (s_ok or not dev),
        ("No development mesocycle in this plan" if not dev else
         "Target share of sets (injury-prevention work not counted): " + ", ".join(f"{m['label']} {round(m['target_share'] * 100)}%" for m in dev)))
    # 4 strength before aerobic, not in the same workout
    pos = {x: i for i, x in enumerate(plan["target_order"])}
    order_ok = pos.get(ABILITY["aerobic"], 99) >= max((pos.get(ABILITY[x], -1) for x in ("max_strength", "hypertrophy")), default=-1)
    same = any(r["heavy_legs"] and r["endurance"] for m in ms for r in m["microcycle"] if r.get("items"))
    pair = any({ABILITY["aerobic"]} <= set(m["targets"]) and {ABILITY["max_strength"], ABILITY["hypertrophy"]} & set(m["targets"]) for m in dev)
    add("Strength before aerobic emphasis; no heavy strength + endurance in the same workout", order_ok and not same and not pair,
        "Yes" if order_ok and not same and not pair else "Heavy strength and aerobic endurance meet - separate them")
    # 5 retaining loads
    ok = all(m["retained"] == [] or any(e["role"] == "Retain" for e in m["complex"]) or m["type"] in ("transition",) for m in dev)
    add("Non-targeted abilities have retaining loads", ok, "Retained abilities keep one exercise at 1-2 sets" if ok else "A mesocycle has no retaining work")
    # 6 complex stable, changed every 2-4 months
    blocks = plan["blocks"]
    spans = []
    for i, b in enumerate(blocks):
        nxt = blocks[i + 1]["from"] if i + 1 < len(blocks) else ms[-1]["end"]
        spans.append(((nxt - b["from"]).days + 1) // 7)
    long_ok = all(s <= 18 for s in spans)
    add("Exercise complex stable within a mesocycle; changed every 2-4 months", long_ok,
        "Complexes last " + ", ".join(f"{s} wk" for s in spans) + " (shorter where the period changes to specific work or transition)")
    # 7 rule of 60%
    day_ok = all(min(r["load"] for r in m["microcycle"] if r["items"] and "PM" not in r["when"]) /
                 max(r["load"] for r in m["microcycle"] if r["items"]) <= 0.75
                 for m in dev if sum(1 for r in m["microcycle"] if r["items"]) >= 2)
    wk_ok = all(abs(min(w["volume"] for w in plan["weeks"] if w["mesocycle"] == m["number"]) /
                    max(w["volume"] for w in plan["weeks"] if w["mesocycle"] == m["number"]) - 0.6) < 0.05 for m in dev if m["weeks"] >= 2)
    train = [m["relative_load"] for m in ms if m["type"] != "transition"]
    meso_ok = not train or min(train) / max(train) >= 0.55
    add("Rule of 60% at day, microcycle and mesocycle level", day_ok and wk_ok and meso_ok,
        f"Day: {'yes' if day_ok else 'no'}; microcycle: {'yes' if wk_ok else 'no'}; mesocycle: lightest {min(train) if train else '-'}% of the heaviest")
    # 8 heavy sessions/week
    heavy_dev = [sum(1 for r in m["microcycle"] if r.get("resistance")) for m in dev]
    comp_heavy = [sum(1 for r in m["competition_microcycle"] if r.get("heavy")) for m in ms if m["type"] == "competition"]
    g_ok = all(h >= 3 for h in heavy_dev)
    add(">= 3 heavy sessions a week when building strength; >= 2 when retaining", g_ok,
        (f"Development weeks: {', '.join(map(str, heavy_dev))} resistance workout(s)" if heavy_dev else "No development weeks") +
        (f"; competition: {', '.join(map(str, comp_heavy))} heavy retaining workout(s)" if comp_heavy else "") +
        ("" if g_ok else f" - only {a['training_days']} training day(s): add a day to gain strength"))
    # 9 large muscles 48 h; squats out 10-12 days before
    gap_ok = True
    for m in ms:
        legs = [DAYS.index(r["day"]) for r in m["microcycle"] if r["heavy_legs"] and r["items"]]
        if len(legs) > 1 and min((b - x) for x, b in zip(legs, legs[1:])) < 2:
            gap_ok = False
    taper_ok = all(not any(e["kind"] in HEAVY_LEGS - {"speed"} and e["kind"] == "leg_strength" for e in r.get("exercises", []))
                   for t in plan["tapers"] for r in t["rows"] if r["days_out"] < 10)
    add("Large-muscle work >= 48 h apart; heavy squats removed 7-12 days before competition", gap_ok and taper_ok,
        "Heavy-leg days are 48 h or more apart; last heavy leg work 11-14 days out" if gap_ok and taper_ok else "Heavy legs too close")
    # 10 stress microcycles
    add("Stress microcycles <= 3-4 a year, each followed by a light microcycle", True,
        "None planned" if a["youth"] or a["level"] == "beginner" else "Only if gains stall; each followed by an unloading week")
    # 11 in-season 2 x 30-40 min
    in_ok, limited = True, False
    for m in ms:
        if m["type"] == "competition":
            cm = m["competition_microcycle"]
            for i in range(0, len(cm), 7):
                chunk = cm[i:i + 7]
                need = 2 if len(chunk) >= 5 else 1 if len(chunk) >= 3 else 0
                got = sum(1 for r in chunk if r.get("heavy"))
                if got < need:
                    possible = [r for r in chunk if not r["match"] and r["session"].startswith(("Recovery:", "Cricket skills", "Short heavy", "Recovery for"))]
                    if len(possible) > got:
                        in_ok = False
                    else:
                        limited = True
    add("In-season: 2 x 30-40 min heavy workouts a week", in_ok if not limited else None,
        "Planned on free days between matches (whole body) and the day after a match (upper body and trunk)" +
        ("" if in_ok and not limited else " - matches every second day leave room for fewer: every possible day is used, none the day before a match"
         if in_ok else " - a free day is not used; add a workout"))
    # 12 passive rest
    run = mx = 0
    for m in ms:
        for r in m["competition_microcycle"]:
            run = run + 1 if r["session"] == "Rest" else 0
            mx = max(mx, run)
    add("No passive rest > 3 days in a row in season; transition keeps body weight within 2-3 kg", mx <= 3,
        f"Longest passive rest in season: {mx} day(s). " + plan["transition"]["body_weight"])
    # 13 workout order and rest
    ord_ok = all([KIND_ORDER.get(e["kind"], 9) for e in m["complex"]] == sorted(KIND_ORDER.get(e["kind"], 9) for e in m["complex"]) for m in ms)
    rest_ok = all(("4-5 min" in e["rest"] or "3-5 min" in e["rest"]) for m in ms if m["type"] in ("transmutation", "realization", "competition")
                  for e in m["complex"] if e["kind"] in HEAVY | EXPLOSIVE and e["role"] == "Target")
    add("Workout order rules and rest for heavy sets followed; no pyramids", ord_ok and rest_ok,
        "Power first, large before small, lower and upper alternate; heavy/explosive sets with full recovery" if ord_ok and rest_ok else "Check order / rest")
    # 14 individualized
    ind = bool(plan["target_order"]) and bool(a.get("position"))
    add("Plan individualized to this athlete's data", ind,
        f"Targets from {', '.join(plan['target_order'])}; exercises from the {a['position'].lower()} list; calendar and days from Step 0")
    return out
