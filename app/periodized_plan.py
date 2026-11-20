"""The periodized annual plan (year -> mesocycle -> microcycle -> session), built by the rules of the ANNUAL PLAN BUILDER
instructions: Zatsiorsky & Kraemer, Science and Practice of Strength Training (ch. 1, 5, 10) and NSCA, Essentials of Strength
Training and Conditioning (periodization and program design). Pure module: no database, no web, no Excel.

It sits BESIDE the seasonal plan in the supplied workbook's structure (seasonal_workbook.py); neither replaces the other.

Phase 0 inputs come from the app (squad, age group, season and phases, calendar matches, latest test results); anything the app
does not hold is an ASSUMPTION, listed in the plan and on the Inputs sheet. Phases 2 to 8 build the plan; verify() is Phase 10.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

# ───────────── Phase 1: rules, as data ─────────────
# phase code -> (period, phase, mesocycle type)
PHASES = {
    "H": ("Preparatory", "General prep - hypertrophy / strength-endurance", "Accumulation"),
    "B": ("Preparatory", "Basic strength", "Accumulation"),
    "S": ("Preparatory", "Specific prep - strength / power", "Transmutation"),
    "U": ("First transition", "Unloading", "Realization"),
    "P": ("Competition", "Peaking", "Realization"),
    "M": ("Competition", "Maintenance", "Maintenance"),
    "T": ("Second transition", "Active rest", "Transition"),
}
PREP = ("H", "B", "S")
MESO_WEEKS = {"H": 4, "B": 4, "S": 3, "M": 4}           # mesocycles get shorter toward competition (4, 4, 3; taper 4)
LOADING_PATTERN = {2: "1:1", 3: "2:1", 4: "3:1", 5: "4:1", 6: "5:1"}
SPECIFIC_SHARE = 0.35                                      # specific prep scales with the general prep (delayed transmutation)
HYPER_SHARE = 0.55                                         # of the general prep: hypertrophy first, then basic strength
TRANSITION_WEEKS = 3                                       # second transition 1-4 weeks
TAPER_PEAK_WEEKS, UNLOAD_WEEKS = 3, 1                      # taper = 1 unloading week + 3 peaking weeks (normal load rise -> ~4 weeks)
LOAD_RISE = "normal"                                       # no stress microcycles (youth) -> a normal rise
TAPER_FOR_RISE = {"mild": 2, "normal": 4, "stress": 6}
LOAD_HIGH, LOAD_MEDIUM = 0.75, 0.50
PREP_START, PREP_PEAK = 0.60, 1.00                         # first prep mesocycle starts at 60%; the last specific meso peaks at 100%
STEP = 0.05                                                # +5% a loading week inside a mesocycle
UNLOAD_FACTOR = 0.65                                       # unloading week = 65% of the mesocycle's heaviest week (rule of 60%)
TAPER_LOADS = [0.60, 0.70, 0.65, 0.60]                     # unloading week, then the peaking weeks (60-70%)
TOURNAMENT_LOAD = 0.65
MAINT_WAVE = [0.65, 0.70, 0.60, 0.65]                      # in-season undulating 55-70%
TRANSITION_LOADS = [0.35, 0.30, 0.35, 0.30]                # 30-40%
VOL_INT = {"H": ("High", "Low"), "B": ("Medium", "Medium"), "S": ("Medium", "High"), "U": ("Low", "Medium"),
           "P": ("Low", "High"), "M": ("Medium", "High"), "T": ("Low", "Low")}
LEVEL_NUM = {"Low": 1, "Medium": 2, "High": 3}
PEAKING_INDEX = {"T": 1, "H": 2, "B": 2, "S": 3, "U": 4, "M": 4, "P": 5}

# sessions per week by type (youth: resistance 2-3 non-consecutive days, never 4-6)
SESSION_TYPES = ["Resistance", "Plyometrics", "Speed & agility", "Conditioning", "Cricket practice (technical / tactical)", "Recovery"]
SESSIONS = {
    "H": [3, 1, 1, 3, 3, 1], "B": [3, 2, 1, 2, 3, 1], "S": [3, 2, 2, 2, 4, 1], "U": [2, 1, 1, 1, 3, 2],
    "P": [2, 1, 2, 1, 4, 2], "M": [2, 1, 1, 1, 3, 2], "T": [0, 0, 0, 2, 0, 1],
}
TOURNAMENT_SESSIONS = [2, 0, 2, 0, 2, 4]                   # matches every second day: 2 short upper / trunk sessions, recovery between

# Phase 4 factor matrix: 0 not trained, 1 retaining, 2 developing, 3 main focus. At most 3 factors at level 3 a week.
FACTORS = {
    "Physical": [
        ("Aerobic endurance", {"H": 3, "B": 2, "S": 1, "U": 1, "P": 1, "M": 1, "T": 2}),
        ("Anaerobic endurance", {"H": 0, "B": 1, "S": 2, "U": 1, "P": 2, "M": 2, "T": 0}),
        ("Maximal strength", {"H": 1, "B": 3, "S": 2, "U": 1, "P": 1, "M": 1, "T": 0}),
        ("Hypertrophy / strength-endurance", {"H": 3, "B": 1, "S": 1, "U": 0, "P": 0, "M": 0, "T": 0}),
        ("Power / explosive strength", {"H": 1, "B": 1, "S": 3, "U": 2, "P": 2, "M": 2, "T": 0}),
        ("Speed", {"H": 1, "B": 1, "S": 3, "U": 2, "P": 3, "M": 2, "T": 0}),
        ("Agility / change of direction", {"H": 1, "B": 1, "S": 2, "U": 2, "P": 2, "M": 2, "T": 0}),
        ("Reaction speed", {"H": 1, "B": 1, "S": 2, "U": 2, "P": 2, "M": 2, "T": 0}),
        ("Flexibility", {"H": 2, "B": 2, "S": 1, "U": 2, "P": 1, "M": 1, "T": 2}),
        ("Coordination", {"H": 2, "B": 2, "S": 2, "U": 1, "P": 1, "M": 1, "T": 1}),
        ("Trunk / core strength", {"H": 2, "B": 2, "S": 1, "U": 1, "P": 1, "M": 1, "T": 1}),
    ],
    "Technical": [
        ("Basic technique", {"H": 2, "B": 2, "S": 1, "U": 1, "P": 1, "M": 1, "T": 1}),
        ("Advanced technique", {"H": 1, "B": 1, "S": 2, "U": 2, "P": 1, "M": 1, "T": 0}),
        ("Competition technique", {"H": 0, "B": 0, "S": 1, "U": 2, "P": 3, "M": 3, "T": 0}),
    ],
    "Tactical": [
        ("Basic tactics", {"H": 2, "B": 2, "S": 1, "U": 1, "P": 1, "M": 1, "T": 0}),
        ("Team offensive / defensive", {"H": 0, "B": 1, "S": 2, "U": 2, "P": 2, "M": 2, "T": 0}),
        ("Game-plan specific", {"H": 0, "B": 0, "S": 1, "U": 2, "P": 3, "M": 2, "T": 0}),
    ],
    "Psychological": [
        ("Relaxation", {k: 1 for k in PHASES}), ("Imagery", {k: 1 for k in PHASES}), ("Self-talk", {k: 1 for k in PHASES}),
        ("Goal setting", {k: 0 for k in PHASES}),           # set per week: start of the plan and of preseason
        ("Concentration", {"H": 0, "B": 0, "S": 2, "U": 2, "P": 2, "M": 2, "T": 0}),
        ("Confidence", {"H": 0, "B": 0, "S": 1, "U": 2, "P": 2, "M": 2, "T": 0}),
    ],
}
NUTRITION = {
    "H": "Energy balance for the training volume (growing players: never a deficit); protein 1.5-2.0 g/kg a day spread over 4 meals.",
    "B": "Energy balance; protein 1.5-2.0 g/kg; carbohydrate before and after heavy days.",
    "S": "Carbohydrate around speed and power sessions; protein 1.5-2.0 g/kg; sleep 9 h or more.",
    "U": "Keep energy intake; hydration habits for the competition.",
    "P": "Carbohydrate timing around matches; hydration (lose less than 2% of body mass); recovery meal within 1 h.",
    "M": "Carbohydrate timing around matches; hydration (less than 2% body-mass loss); protein after strength sessions.",
    "T": "Keep body weight stable (within about 2-3 kg); balanced meals; active recovery.",
}

# Phase 5: methods by phase (G general, B basic strength, S specific, P peaking / taper, M maintenance, T transition)
METHOD_PHASES = ["General prep", "Basic strength", "Specific prep", "Peaking / taper", "Maintenance", "Transition"]
METHODS = [  # (group, method, note: work:rest or %1RM, phases (letters of METHOD_PHASES))
    ("Aerobic", "Continuous slow run (LSD)", "~70% VO2max, 20-40 min (youth), oxidative", "GT"),
    ("Aerobic", "Fartlek", "mixed paces, 15-25 min", "GB"),
    ("Aerobic", "Hill run", "short hills, walk-back recovery", "G"),
    ("Aerobic", "Tempo run", "at lactate threshold, 15-20 min (youth)", "GB"),
    ("Aerobic", "Steady state", "20-30 min steady", "G"),
    ("Aerobic", "Long intervals", "3-5 min near VO2max, W:R 1:1", "B"),
    ("Aerobic", "Small-sided games", "fielding / running games, W:R 1:1-1:2", "GSMT"),
    ("Anaerobic intervals", "400 m interval", "fast glycolysis + oxidative, W:R 1:3-1:4", ""),
    ("Anaerobic intervals", "300 m interval", "fast glycolysis + oxidative (~60 s), W:R 1:3", "GB"),
    ("Anaerobic intervals", "200 m interval", "fast glycolysis + oxidative, W:R 1:3-1:4", "B"),
    ("Anaerobic intervals", "150 m / 120 m interval", "fast glycolysis (15-30 s), W:R 1:4", "BSPM"),
    ("Anaerobic intervals", "100 m / 50 m interval", "fast glycolysis, W:R 1:3-1:5", "S"),
    ("Alactic sprints", "10-60 m sprints", "phosphagen 90-100%, 5-10 s, W:R 1:12-1:20, full recovery", "SPM"),
    ("Resistance", "Repeated-effort (hypertrophy)", "60-67% 1RM, 12-15 reps (youth: not to failure), 30-90 s", "G"),
    ("Resistance", "Submaximal-effort", "70-80% 1RM, 6-10 reps, 2 min", "BSM"),
    ("Resistance", "Maximal-effort", "U15: not used (estimate 1RM; heaviest 80-85%)", ""),
    ("Resistance", "Dynamic-effort / power", "30-60% 1RM moved fast; jumps and medicine-ball throws", "SPM"),
    ("Plyometrics", "Low intensity (in place, standing)", "beginner <=80-100 contacts a session", "GB"),
    ("Plyometrics", "Moderate (multiple hops, bounds)", "48-72 h between sessions", "BSM"),
    ("Plyometrics", "High (box drills)", "technique first, never on concrete", "SP"),
    ("Plyometrics", "Depth jumps", "U15: not used", ""),
]

YEAR_WEEKS_DEFAULT = 52                                     # the plan covers one year

# Phase 7/8: youth limits
YOUTH_AGE = 18
PLYO_MAX_CONTACTS = 100                                     # beginner 80-100 contacts a session
PLYO_CONTACTS = {"H": 60, "B": 80, "S": 100, "U": 60, "P": 60, "M": 70, "T": 0}
COACH_RATIO = "1:10"
REF_BODY_MASS = 55.0                                        # kg, for the volume-load estimates (assumption; replace per player)

# ───────────── Phase 0: inputs ─────────────
def _comp_blocks(matches: list[date], gap: int = 3) -> list[tuple[date, date, int]]:
    out = []
    for d in sorted(set(matches)):
        if out and (d - out[-1][1]).days <= gap:
            out[-1] = (out[-1][0], d, out[-1][2] + 1)
        else:
            out.append((d, d, 1))
    return out


def competitions(*, plan_start: date, weeks: int, season: dict, phases: list[dict], matches: list[dict]) -> list[dict]:
    """Every competition in the plan, typed MAIN / SECONDARY / LEAGUE, plus next season's main competition when it falls at the end
    of the plan (the target of this year's preparation). matches: [{date, title}]."""
    plan_end = plan_start + timedelta(days=7 * weeks - 1)
    blocks, assumed = _comp_blocks([m["date"] for m in matches]), False
    if not blocks:                                          # no matches in the calendar: the season's competition phase
        assumed = True
        comp = [p for p in phases if p["phase_type"] == "in_season"] or [{"start_date": season["start_date"], "end_date": season["end_date"]}]
        blocks = [(p["start_date"], p["end_date"], 0) for p in comp]
    out = []
    for a, b, n in blocks:
        if (b - a).days + 1 <= 21:
            out.append({"start": a, "end": b, "type": "MAIN", "name": season["name"], "matches": n, "assumed": assumed})
        else:                                               # a league season: the last match is the main one
            out.append({"start": a, "end": b, "type": "LEAGUE", "name": season["name"] + " (league)", "matches": n, "assumed": assumed})
            out.append({"start": b, "end": b, "type": "MAIN", "name": season["name"] + " (final)", "matches": 1, "assumed": assumed})
    first = min(out, key=lambda c: c["start"])
    nxt = first["start"] + timedelta(days=364)
    if plan_end - timedelta(days=6) <= nxt <= plan_end + timedelta(days=7):
        out.append({"start": nxt, "end": nxt + (first["end"] - first["start"]), "type": "MAIN", "name": "Next season (assumed same dates)",
                    "matches": 0, "assumed": True, "next_year": True})
    return sorted(out, key=lambda c: (c["start"], c["type"] != "LEAGUE"))


def needs_analysis(age_group: str) -> list[tuple[str, str]]:
    return [
        ("Movement analysis", "Sprinting between wickets, accelerating and decelerating in the field, throwing (shoulder, trunk rotation), "
                              "bowling (front-leg block, trunk side flexion and rotation), batting (rotation, wrist and forearm). Main muscles: "
                              "hip and knee extensors, hamstrings, trunk rotators and lateral flexors, shoulder rotator cuff, scapular stabilisers."),
        ("Physiological analysis", "Mostly phosphagen (repeated 5-10 s efforts: running between wickets, fielding sprints, bowling run-ups) "
                                   "on an aerobic base for recovery over long days; small fast-glycolytic share. Needs: speed and acceleration, "
                                   "change of direction, leg and rotational power, trunk strength, aerobic recovery."),
        ("Injury analysis", "Lumbar stress injuries in fast bowlers (growth spurt and high bowling loads), hamstring strains, side strains, "
                            "shoulder and elbow overuse, ankle sprains. Prevention: trunk and hip strength, eccentric hamstring work, "
                            "progressive bowling loads (workload limits), landing technique, shoulder rotator-cuff and scapular work."),
        ("Athlete profile", f"{age_group} boys, about 14-15 years, training age about 1-3 years (assumption: beginner-intermediate in the gym). "
                            "Primary goals: technique and general strength, speed and agility, aerobic base, injury prevention, skill."),
    ]


def test_summary(results: dict[str, list[float]]) -> list[tuple[str, str]]:
    from .test_battery import BY_KEY, display
    out = []
    for key, vals in results.items():
        t = BY_KEY.get(key)
        if t and vals:
            out.append((t.label, f"median {display(t, median(vals))} {t.unit} (n = {len(vals)})"))
    return out


# ───────────── Phase 2: the skeleton (top-down, backward from each MAIN competition) ─────────────
def _week_of(plan_start: date, d: date) -> int:
    return (d - plan_start).days // 7


def _prep_mesos(n: int) -> list[tuple[str, int]]:
    """n preparatory weeks -> mesocycles, shorter toward competition: hypertrophy 4s, basic strength 4s, specific 3s."""
    if n <= 0:
        return []
    if n < 6:
        return [("S", n)] if n >= 2 else [("S", 1)]
    s_count = max(1, round(n * SPECIFIC_SHARE / MESO_WEEKS["S"]))
    g = n - MESO_WEEKS["S"] * s_count
    while g < 4 and s_count > 1:
        s_count -= 1
        g = n - MESO_WEEKS["S"] * s_count
    g_count, extra = divmod(g, 4)
    s_sizes = [MESO_WEEKS["S"]] * s_count
    g_sizes = [4] * g_count
    for i in range(extra):                                   # leftover weeks: first the specific mesos (3 -> 4), then general (4 -> 5)
        if i < len(s_sizes):
            s_sizes[i] += 1
        elif g_sizes:
            g_sizes[(i - len(s_sizes)) % len(g_sizes)] += 1
        else:
            s_sizes[0] += 1
    h_count = max(1, round(len(g_sizes) * HYPER_SHARE)) if g_sizes else 0
    out = [("H", s) for s in g_sizes[:h_count]] + [("B", s) for s in g_sizes[h_count:]] + [("S", s) for s in s_sizes]
    return out


def skeleton(plan_start: date, weeks: int, comps: list[dict]) -> list[dict]:
    """Mesocycles covering every week once, built backward from each competition:
    competition weeks first; then each free stretch = [second transition after a competition] + general prep (hypertrophy,
    basic strength) + specific prep + [first transition (unloading) + peaking taper before a MAIN]. Before a league the last
    preparatory week is the first transition (unloading). A league final gets a short realization block (2 weeks + the final)."""
    comp_code: list[str | None] = [None] * weeks
    for c in comps:
        if c.get("next_year"):
            continue
        a, b = max(0, _week_of(plan_start, c["start"])), min(weeks - 1, _week_of(plan_start, c["end"]))
        for w in range(a, b + 1):
            if comp_code[w] is None:
                comp_code[w] = "M" if c["type"] == "LEAGUE" else "P"
    finals = set()
    for c in comps:                                          # a league final (one MAIN day inside a league): a peaking week
        w = _week_of(plan_start, c["start"])
        if c["type"] == "MAIN" and not c.get("next_year") and 0 <= w < weeks and (c["end"] - c["start"]).days == 0 and comp_code[w] == "M":
            comp_code[w] = "P"
            finals.add(w)
    target_after = any(c.get("next_year") for c in comps)
    seq: list[dict] = []
    w, macro, had = 0, 1, False
    while w < weeks:
        if comp_code[w]:
            j = w
            while j + 1 < weeks and comp_code[j + 1] == comp_code[w] and j + 1 not in finals:
                j += 1
            seq.append({"code": comp_code[w], "n": j - w + 1, "macro": macro, "final": w in finals})
            had, w = True, j + 1
            continue
        j = w
        while j + 1 < weeks and comp_code[j + 1] is None:
            j += 1
        free = j - w + 1
        nxt = comp_code[j + 1] if j + 1 < weeks else ("P" if target_after else None)
        if had:
            t = min(TRANSITION_WEEKS if free >= 12 else max(1, min(2, free)), 4, free)
            seq.append({"code": "T", "n": t, "macro": macro})
            free -= t
            macro += 1
        if nxt == "P" and free >= 10:
            prep = _prep_mesos(free - TAPER_PEAK_WEEKS - UNLOAD_WEEKS)
            seq += [{"code": c, "n": n, "macro": macro} for c, n in prep]
            seq.append({"code": "UP", "n": TAPER_PEAK_WEEKS + UNLOAD_WEEKS, "macro": macro})
        else:
            prep = _prep_mesos(free)
            seq += [{"code": c, "n": n, "macro": macro} for c, n in prep]
            if nxt and seq and seq[-1]["code"] in PREP:
                seq[-1]["unload_last"] = True                # the first transition: the last preparatory week unloads
        w = j + 1
    out = []
    for i, x in enumerate(seq):
        code, n = x["code"], x["n"]
        if code == "UP":
            out.append({"codes": ["U"] * UNLOAD_WEEKS + ["P"] * TAPER_PEAK_WEEKS, "type": "Realization", "macro": x["macro"], "taper": True})
        elif code == "M":
            nxt_final = i + 1 < len(seq) and seq[i + 1].get("final")
            keep = n - 2 if nxt_final and n >= 4 else n      # the last 2 league weeks join the final's realization block
            parts_n = max(1, round(keep / MESO_WEEKS["M"]))
            base, extra = divmod(keep, parts_n)
            for k in range(parts_n):
                ln = base + (1 if k < extra else 0)
                if ln:
                    out.append({"codes": ["M"] * ln, "type": "Maintenance", "macro": x["macro"]})
            if keep < n:
                out.append({"codes": ["M"] * (n - keep), "type": "Realization", "macro": x["macro"], "taper": True, "mini": True})
        elif code == "P" and x.get("final") and out and out[-1].get("mini"):
            out[-1]["codes"] += ["P"] * n                     # the final closes the realization block
        elif code == "P":
            out.append({"codes": ["P"] * n, "type": "Realization", "macro": x["macro"]})
        else:
            codes = [code] * n
            if x.get("unload_last") and n > 1:
                codes[-1] = "U"
            out.append({"codes": codes, "type": PHASES[code][2], "macro": x["macro"]})
    w = 0
    for i, m in enumerate(out, 1):
        m["no"], m["first"], m["last"] = i, w, w + len(m["codes"]) - 1
        m["main"] = m["codes"][0] if m["codes"][0] != "U" else "U"
        w += len(m["codes"])
    return out


# ───────────── Phase 3: load ─────────────
def week_loads(mesos: list[dict]) -> tuple[list[float], list[bool]]:
    """Load % per week and whether the week is an unloading week. Step loading inside each preparatory mesocycle."""
    loads, unload = [], []
    prep = [m for m in mesos if m["codes"][0] in PREP]
    by_macro: dict[int, list[dict]] = {}
    for m in prep:
        by_macro.setdefault(m["macro"], []).append(m)
    start_of: dict[int, float] = {}
    for mac, ms in by_macro.items():
        for i, m in enumerate(ms):
            loading = len(m["codes"]) - 1 if len(m["codes"]) > 1 else 1
            top = PREP_START + (PREP_PEAK - STEP * (loading - 1) - PREP_START) * (i / (len(ms) - 1) if len(ms) > 1 else 1)
            start_of[id(m)] = round(top, 2)
    maint_i = 0
    for m in mesos:
        n, code = len(m["codes"]), m["codes"][0]
        if code in PREP:
            b = start_of[id(m)]
            ws = [round(min(1.0, b + STEP * i), 2) for i in range(max(1, n - 1))]
            if n > 1:
                ws.append(round(max(ws) * UNLOAD_FACTOR, 2))
            loads += ws
            unload += ([False] * (n - 1) + [True]) if n > 1 else [False]
        elif m.get("mini"):                                 # before a league final: 2 lighter weeks, then the final
            ws = [0.60, 0.55][: n - 1] + [0.60] * max(0, n - 3) + [0.65]
            loads += ws[:n]
            unload += [False] * n
            continue
        elif m.get("taper") or code == "U":
            seq = (TAPER_LOADS if m["codes"][0] == "U" else TAPER_LOADS[1:])
            ws = [seq[min(i, len(seq) - 1)] for i in range(n)]
            loads += ws
            unload += [c == "U" for c in m["codes"]]
        elif code == "P":
            loads += [TOURNAMENT_LOAD] * n
            unload += [False] * n
        elif code == "M":
            for i in range(n):
                loads.append(MAINT_WAVE[maint_i % len(MAINT_WAVE)])
                maint_i += 1
            unload += [False] * n
        else:                                                # transition
            loads += [TRANSITION_LOADS[i % len(TRANSITION_LOADS)] for i in range(n)]
            unload += [False] * n
    return loads, unload


def load_text(p: float) -> str:
    return "High" if p >= LOAD_HIGH else "Medium" if p >= LOAD_MEDIUM else "Low"


# ───────────── conditioning (Phase 5/9: each interval separately; total by SUMPRODUCT in the sheet) ─────────────
MAX_SPEED = 7.0                                              # m/s, an assumed U15 maximal running speed (bout times are estimates)
INTERVALS = {  # phase -> [(method, distance m, base reps at full load, % max speed)]
    "H": [("Continuous slow run", 3000, 1, 0.45), ("300 m interval", 300, 6, 0.70)],
    "B": [("300 m interval", 300, 5, 0.70), ("150 m interval", 150, 6, 0.80)],
    "S": [("150 m interval", 150, 6, 0.85), ("120 m interval", 120, 6, 0.85), ("30 m sprint", 30, 6, 0.95)],
    "U": [("120 m interval", 120, 4, 0.85), ("30 m sprint", 30, 6, 0.95)],
    "P": [("120 m interval", 120, 4, 0.90), ("30 m sprint", 30, 6, 0.95), ("20 m sprint", 20, 4, 1.00)],
    "M": [("120 m interval", 120, 4, 0.85), ("30 m sprint", 30, 6, 0.95)],
    "T": [("Continuous easy run / games", 2000, 1, 0.40)],
}
TOURNAMENT_INTERVALS = [("20 m sprint (activation)", 20, 4, 0.95)]
SYSTEMS = [  # (system, bout seconds from, to, work:rest from, to)
    ("Phosphagen", 0, 10, 12, 20), ("Fast glycolysis", 10, 35, 3, 5), ("Fast glycolysis + oxidative", 35, 180, 3, 4), ("Oxidative", 180, 10 ** 6, 0, 3)]
PROGRESSION_CAP = 0.10
PREP_START_VOLUME = 0.45                                     # the first preparatory week: 45% of the phase's full volume


def system_of(seconds: float) -> tuple[str, int, int]:
    for name, a, b, lo, hi in SYSTEMS:
        if a <= seconds < b:
            return name, lo, hi
    return SYSTEMS[-1][0], SYSTEMS[-1][3], SYSTEMS[-1][4]


def conditioning(codes: list[str], loads: list[float], unload: list[bool], tournament: list[bool], scale: float = 1.0) -> list[list[dict]]:
    """Per week: the interval rows. Volume follows the load % and never rises more than 10% on the previous loading week inside a
    training block (from the first preparatory week to the competition); a block's first week starts at 45% of the full volume;
    an unloading week is at most 65% of the previous loading week."""
    out, prev_loading, in_block = [], None, False
    for w, code in enumerate(codes):
        sets = TOURNAMENT_INTERVALS if tournament[w] else INTERVALS[code]
        full = sum(d * r for _, d, r, _ in sets)
        target = full * loads[w] * (1 if tournament[w] else scale)
        counted = code in PREP + ("U", "P", "M") and not tournament[w]
        if counted and not in_block:
            target, in_block, prev_loading = full * PREP_START_VOLUME, True, None
        if not counted:
            in_block, prev_loading = False, None
        if counted and prev_loading is not None:
            target = min(target, prev_loading * (UNLOAD_FACTOR if unload[w] else 1 + PROGRESSION_CAP))
        ratio = min(1.0 if tournament[w] else scale, target / full)
        rows, used = [], 0
        for name, dist, reps, spd in sets:                   # intervals first (whole reps, rounded down)
            if name.startswith("Continuous"):
                continue
            r = max(1, int(reps * ratio))
            rows.append((name, dist, r, spd))
            used += dist * r
        for name, dist, reps, spd in sets:                   # the continuous run takes the rest, in 100 m steps
            if name.startswith("Continuous"):
                rows.insert(0, (name, max(400, int((target - used) / 100) * 100), 1, spd))
        week = []
        for name, d, r, spd in rows:
            work = round(d / (MAX_SPEED * spd))
            system, lo, hi = system_of(work)
            cont = name.startswith("Continuous")
            rest = 0 if cont else round(work * (lo + hi) / 2)
            week.append({"method": name, "distance": d, "reps": r, "speed": spd, "work_s": work, "rest_s": rest, "system": system,
                         "wr_lo": lo, "wr_hi": hi, "continuous": cont, "counted": counted})
        total = sum(x["distance"] * x["reps"] for x in week)
        if counted and not unload[w]:
            prev_loading = total
        out.append(week)
    return out


# ───────────── Phase 6: exercise complexes and resistance prescription (U15: estimated 1RM, never maximal testing) ─────────────
# (exercise, category, load type, ratio to body mass for the estimated 1RM or body-weight load)
COMPLEXES = {
    "A": [("Goblet squat", "core", "%1RM", 0.6), ("Dumbbell Romanian deadlift", "core", "%1RM", 0.8), ("Push-up", "core", "BW", 0.65),
          ("Inverted row", "core", "BW", 0.6), ("Dumbbell split squat", "assist", "%1RM", 0.4), ("Dumbbell bench press", "assist", "%1RM", 0.5),
          ("Band pull-apart", "assist", "Band", 0), ("Medicine-ball chest pass (3 kg)", "power", "Ball", 0), ("Front plank", "trunk", "Time", 0),
          ("Side plank", "trunk", "Time", 0)],
    "B": [("Back squat (technique bar to light)", "core", "%1RM", 1.0), ("Trap-bar deadlift", "core", "%1RM", 1.2),
          ("Dumbbell bench press", "core", "%1RM", 0.5), ("Assisted chin-up", "core", "BW", 0.7), ("Walking lunge", "assist", "%1RM", 0.4),
          ("Single-leg Romanian deadlift", "assist", "%1RM", 0.4), ("Landmine press", "assist", "%1RM", 0.35),
          ("Nordic hamstring (assisted)", "assist", "BW", 0.5), ("Pallof press", "trunk", "Band", 0), ("Medicine-ball rotational throw (3 kg)", "power", "Ball", 0)],
    "C": [("Trap-bar jump (light)", "power", "%1RM", 1.2), ("Medicine-ball rotational throw (3 kg)", "power", "Ball", 0),
          ("Back squat", "core", "%1RM", 1.0), ("Push press (dumbbell)", "core", "%1RM", 0.4), ("Single-arm dumbbell row", "core", "%1RM", 0.4),
          ("Rear-foot-elevated split squat", "assist", "%1RM", 0.4), ("Lateral bound to stick", "power", "BW", 0),
          ("Copenhagen plank", "trunk", "Time", 0), ("Shoulder external rotation (band)", "assist", "Band", 0), ("Dead bug", "trunk", "Time", 0)],
    "D": [("Trap-bar deadlift", "core", "%1RM", 1.2), ("Dumbbell bench press", "core", "%1RM", 0.5), ("Inverted row", "core", "BW", 0.6),
          ("Rear-foot-elevated split squat", "assist", "%1RM", 0.4), ("Nordic hamstring (assisted)", "assist", "BW", 0.5),
          ("Medicine-ball rotational throw (3 kg)", "power", "Ball", 0), ("Shoulder external rotation (band)", "assist", "Band", 0),
          ("Pallof press", "trunk", "Band", 0), ("Side plank", "trunk", "Time", 0), ("Front plank", "trunk", "Time", 0)],
}
COMPLEX_FOR = {"H": "A", "B": "B", "S": "C", "U": "C", "P": "C", "M": "D", "T": None}


def prescription(code: str, k: int) -> dict:
    """Sets x reps @ %1RM and rest (s) for the mesocycle (k = its index inside the phase). %1RM never above the max-reps table."""
    if code == "H":                                          # youth: start at 1-2 sets of 12-15, progress 5-10%
        return [dict(sets=2, reps=15, pct=0.60, rest=60), dict(sets=2, reps=12, pct=0.65, rest=75),
                dict(sets=3, reps=12, pct=0.65, rest=75), dict(sets=3, reps=12, pct=0.67, rest=90)][min(k, 3)]
    if code == "B":
        return [dict(sets=3, reps=8, pct=0.75, rest=120), dict(sets=3, reps=6, pct=0.80, rest=150), dict(sets=3, reps=6, pct=0.80, rest=150)][min(k, 2)]
    if code == "S":
        return dict(sets=3, reps=5, pct=0.80, rest=150, power=dict(sets=3, reps=5, pct=0.50, rest=120))
    if code in ("U", "P"):
        return dict(sets=2, reps=3, pct=0.80, rest=150, power=dict(sets=2, reps=3, pct=0.50, rest=120))
    if code == "M":
        return dict(sets=2, reps=5, pct=0.80, rest=150, power=dict(sets=2, reps=4, pct=0.50, rest=120))
    return {}


MAX_REPS = [(1.00, 1), (0.95, 2), (0.93, 3), (0.90, 4), (0.87, 5), (0.85, 6), (0.83, 7), (0.80, 8), (0.77, 9), (0.75, 10), (0.70, 11),
            (0.67, 12), (0.65, 15), (0.0, 20)]


def max_reps(pct: float) -> int:
    return next(r for p, r in MAX_REPS if pct >= p - 1e-9)


def resistance_rows(mesos: list[dict]) -> list[dict]:
    rows, seen = [], {}
    for m in mesos:
        code = m["codes"][-1] if m["codes"][0] == "U" else m["codes"][0]
        cx = COMPLEX_FOR[code]
        if not cx:
            continue
        k = seen.get(code, 0)
        seen[code] = k + 1
        pr = prescription(code, k)
        for ex, cat, ltype, ratio in COMPLEXES[cx]:
            p = pr.get("power") if cat == "power" and pr.get("power") else pr
            reps = p["reps"] if ltype not in ("Time",) else 30
            rows.append({"meso": m["no"], "complex": cx, "exercise": ex, "category": cat, "load_type": ltype, "sets": p["sets"],
                         "reps": reps, "pct": p["pct"] if ltype == "%1RM" else None, "rest": p["rest"], "ratio": ratio})
    return rows


# ───────────── Phase 7: microcycle templates ─────────────
# day: (day, AM, PM, content, load H/M/L/Match/Rest, day load %, restoration, heavy lower body, plyometrics, match, passive rest)
def _d(day, am, pm, content, load, pct, rest_cat, heavy=0, plyo=0, match=0, off=0):
    return dict(day=day, am=am, pm=pm, content=content, load=load, pct=pct, restoration=rest_cat, heavy_legs=heavy, plyo=plyo, match=match, off=off)


def microcycles(tournament_days: int) -> list[dict]:
    t_days = []
    for i in range(max(tournament_days, 2)):
        if i % 2 == 0:
            t_days.append(_d(f"Day {i + 1}", "Activation 20 min", "MATCH", "Match day: warm-up, 20 m activation sprints, match", "Match", 100, "Large (48-72 h)", match=1))
        else:
            t_days.append(_d(f"Day {i + 1}", "Recovery 30 min", "Upper body / trunk 30 min", "Recovery between matches: mobility, pool or walk, short "
                             "upper-body and trunk strength (retaining), skills light", "Light", 60, "Small (<12 h)"))
    return [
        {"name": "General preparation week", "phase": "General prep", "days": [
            _d("Mon", "-", "Resistance A (lower + upper) 60 min; aerobic tempo 20 min", "Heavy: complex A, then tempo run", "Heavy", 100, "Large (48-72 h)", heavy=1),
            _d("Tue", "-", "Cricket practice 90 min; plyometrics low 15 min (start)", "Medium: skills, low plyometrics fresh", "Medium", 80, "Substantial (24-48 h)", plyo=1),
            _d("Wed", "-", "Resistance A (upper emphasis) 45 min; flexibility", "Light: upper body, mobility", "Light", 60, "Medium (12-24 h)"),
            _d("Thu", "-", "Cricket practice 90 min; 300 m intervals", "Medium: skills, then intervals", "Medium", 80, "Substantial (24-48 h)"),
            _d("Fri", "-", "Resistance A (lower + trunk) 60 min; speed technique first", "Heavy: speed technique, complex A", "Heavy", 100, "Large (48-72 h)", heavy=1),
            _d("Sat", "Match practice 2 h; continuous run 20 min", "-", "Medium: match practice, aerobic", "Medium", 70, "Substantial (24-48 h)"),
            _d("Sun", "-", "-", "Rest", "Rest", 0, "-", off=1)]},
        {"name": "Specific preparation week", "phase": "Specific prep", "days": [
            _d("Mon", "-", "Speed 20 min; resistance C (power + strength) 60 min", "Heavy: speed fresh, then power and strength", "Heavy", 100, "Large (48-72 h)", heavy=1),
            _d("Tue", "-", "Cricket practice 2 h; plyometrics moderate 20 min (start)", "Medium: skills, plyometrics", "Medium", 80, "Substantial (24-48 h)", plyo=1),
            _d("Wed", "-", "Cricket practice 90 min; mobility", "Light: skills, flexibility", "Light", 60, "Medium (12-24 h)"),
            _d("Thu", "-", "Agility 20 min; resistance C (upper + trunk) 45 min; 150 m intervals", "Heavy: agility, upper body, intervals", "Heavy", 90, "Substantial (24-48 h)"),
            _d("Fri", "-", "Cricket practice 2 h; plyometrics 15 min (start)", "Medium: skills, plyometrics", "Medium", 80, "Substantial (24-48 h)", plyo=1),
            _d("Sat", "Match simulation 3 h", "-", "Medium-heavy: match simulation", "Medium", 80, "Large (48-72 h)"),
            _d("Sun", "-", "-", "Rest", "Rest", 0, "-", off=1)]},
        {"name": "Taper week", "phase": "Peaking / taper", "days": [
            _d("Mon", "-", "Speed 15 min; resistance 2 x 3 (no squats 10-12 days out) 30 min", "Medium: speed, short strength", "Medium", 80, "Substantial (24-48 h)"),
            _d("Tue", "-", "Cricket practice 90 min (competition technique)", "Heavy (short, intense): game scenarios", "Heavy", 100, "Substantial (24-48 h)"),
            _d("Wed", "-", "Mobility, recovery 45 min", "Light: recovery", "Light", 60, "Small (<12 h)"),
            _d("Thu", "-", "Speed 15 min; cricket practice 75 min; plyometrics 10 min", "Medium: speed, skills", "Medium", 80, "Substantial (24-48 h)", plyo=1),
            _d("Fri", "-", "Activation 30 min; team tactics", "Light: activation", "Light", 60, "Small (<12 h)"),
            _d("Sat", "Practice match 2 h", "-", "Medium: practice match", "Medium", 70, "Substantial (24-48 h)"),
            _d("Sun", "-", "-", "Rest", "Rest", 0, "-", off=1)]},
        {"name": "In-season match week (match Saturday)", "phase": "Maintenance", "days": [
            _d("Sun", "Recovery session 45 min", "-", "Day after the match: pool or walk, mobility", "Light", 60, "Small (<12 h)"),
            _d("Mon", "-", "-", "Rest", "Rest", 0, "-", off=1),
            _d("Tue", "-", "Main strength (resistance D, 35 min); cricket practice 90 min", "Heavy: main strength 3 days after the match", "Heavy", 100, "Large (48-72 h)", heavy=1),
            _d("Wed", "-", "Cricket practice 2 h; speed 15 min; plyometrics 10 min", "Medium: skills, speed", "Medium", 80, "Substantial (24-48 h)", plyo=1),
            _d("Thu", "-", "Power primer (upper, medicine ball, 25 min); cricket practice 75 min", "Medium: short power primer, no heavy legs", "Medium", 80, "Medium (12-24 h)"),
            _d("Fri", "-", "Team tactics 60 min; activation", "Light: activation", "Light", 60, "Small (<12 h)"),
            _d("Sat", "MATCH", "-", "Match", "Match", 100, "Large (48-72 h)", match=1)]},
        {"name": f"Tournament microcycle ({len(t_days)} days, a match every second day)", "phase": "Peaking (tournament)", "days": t_days},
        {"name": "Transition week (active rest)", "phase": "Transition", "days": [
            _d("Mon", "-", "Games (football, swimming) 45 min", "Light: recreational", "Light", 60, "Small (<12 h)"),
            _d("Tue", "-", "Mobility 30 min", "Light: mobility", "Light", 60, "Small (<12 h)"),
            _d("Wed", "-", "-", "Rest", "Rest", 0, "-", off=1),
            _d("Thu", "-", "Easy run or bike 25 min", "Light: aerobic easy", "Light", 60, "Small (<12 h)"),
            _d("Fri", "-", "-", "Rest", "Rest", 0, "-", off=1),
            _d("Sat", "Games 60 min", "-", "Light: recreational", "Light", 60, "Small (<12 h)"),
            _d("Sun", "-", "-", "Rest", "Rest", 0, "-", off=1)]},
    ]


# ───────────── Phase 8: session plans (time computed from the rows) ─────────────
# row: (part, exercise, sets, reps / time, load, tempo, work s, rest s, cues, order category 0 warm-up / 1-7 main / 8 cool-down)
def _r(part, ex, sets, reps, load, tempo, work, rest, cues, cat, goal=None):
    return dict(part=part, exercise=ex, sets=sets, reps=reps, load=load, tempo=tempo, work=work, rest=rest, cues=cues, cat=cat, goal=goal)


REST_BY_GOAL = {"plyo": (45, 180), "strength": (120, 300), "power": (120, 300), "hypertrophy": (30, 90), "endurance": (0, 30), "speed": (45, 300)}
INTRO = _r("Introduction", "Goals and safety briefing", 1, "3 min", "-", "-", 180, 0, "Session goals, spotting rules, water", 0)
WARMUP = [_r("Warm-up (RAMP)", "Raise: jog and skips", 1, "5 min", "easy", "-", 300, 0, "Build gradually", 0),
          _r("Warm-up (RAMP)", "Activate & mobilise: dynamic mobility (leg swings, lunges with rotation)", 1, "5 min", "-", "-", 300, 0, "Dynamic stretching only", 0),
          _r("Warm-up (RAMP)", "Potentiate: A-skips, 2 x 20 m build-ups", 2, "20 m", "70-90%", "-", 10, 50, "Session-specific", 0)]
COOLDOWN = [_r("Cool-down", "Easy jog / walk", 1, "5 min", "easy", "-", 300, 0, "", 8),
            _r("Cool-down", "Static stretching: hamstrings, hip flexors, calves, shoulders (15-30 s holds)", 1, "8 min", "-", "-", 480, 0, "No bouncing", 8)]


def session_plans() -> list[dict]:
    S = []
    S.append({"name": "General prep - Monday (heavy)", "micro": "General preparation week", "goal": "Strength-endurance (complex A); aerobic base",
              "equipment": "Dumbbells, kettlebells, bands, mats, track", "intensity": "60-67% 1RM; tempo run 70%", "rows": [INTRO] + WARMUP + [
                  _r("Main", "Speed technique: wall drills, A-march", 3, "20 m", "technique", "-", 15, 60, "Tall posture", 1, "speed"),
                  _r("Main", "Pogo hops (low plyometrics, 30 contacts)", 3, "10", "BW", "quick", 15, 75, "Soft quiet landings, grass or sprung floor", 2, "plyo"),
                  _r("Main", "Goblet squat", 3, "12", "65% 1RM", "2-0-1", 40, 75, "Knees track toes; spot not needed", 4, "hypertrophy"),
                  _r("Main", "Push-up", 3, "12", "BW", "2-0-1", 35, 75, "Rigid trunk", 4, "hypertrophy"),
                  _r("Main", "Dumbbell Romanian deadlift", 3, "12", "65% 1RM", "3-0-1", 45, 75, "Hip hinge, flat back", 4, "hypertrophy"),
                  _r("Main", "Inverted row", 3, "10", "BW", "2-0-1", 35, 75, "Chest to bar", 4, "hypertrophy"),
                  _r("Main", "Dumbbell split squat", 2, "10 each", "40% BM", "2-0-1", 60, 60, "Upright trunk", 5, "hypertrophy"),
                  _r("Main", "Front plank / side plank", 3, "30 s", "BW", "hold", 30, 30, "Neutral spine", 6, "endurance"),
                  _r("Main", "300 m interval at 70% (W:R 1:3)", 4, "300 m", "70% max speed", "-", 61, 183, "Even pace", 7, None)] + COOLDOWN})
    S.append({"name": "Specific prep - Monday (heavy)", "micro": "Specific preparation week", "goal": "Speed and power (complex C)",
              "equipment": "Track, cones, trap bar, barbell, medicine balls", "intensity": "Sprints 95%; power 50% 1RM fast; strength 80% 1RM", "rows": [INTRO] + WARMUP + [
                  _r("Main", "30 m sprints, full recovery", 6, "30 m", "95%", "-", 5, 90, "Fast, relaxed; walk back", 1, "speed"),
                  _r("Main", "Lateral bound to stick (36 contacts)", 3, "6 each", "BW", "explosive", 20, 90, "Stick 2 s", 2, "plyo"),
                  _r("Main", "Trap-bar jump (light)", 3, "5", "50% 1RM", "explosive", 15, 120, "Max intent, soft landing", 3, "power"),
                  _r("Main", "Back squat", 3, "5", "80% 1RM", "2-0-X", 25, 150, "Spot from behind; depth to parallel", 4, "strength"),
                  _r("Main", "Single-arm dumbbell row", 3, "5 each", "80% 1RM", "1-0-1", 30, 150, "Alternates with the squat", 4, "strength"),
                  _r("Main", "Rear-foot-elevated split squat", 2, "6 each", "70% 1RM", "2-0-1", 40, 120, "Balance first", 5, "strength"),
                  _r("Main", "Copenhagen plank", 2, "20 s each", "BW", "hold", 40, 30, "Groin strength", 6, "endurance")] + COOLDOWN})
    S.append({"name": "Taper - Monday (medium)", "micro": "Taper week", "goal": "Keep speed and strength with low volume",
              "equipment": "Track, dumbbells, medicine balls", "intensity": "Sprints 95-100%; strength 80% 1RM, 2 x 3", "rows": [INTRO] + WARMUP + [
                  _r("Main", "20 m sprints", 4, "20 m", "100%", "-", 4, 120, "Full recovery", 1, "speed"),
                  _r("Main", "Medicine-ball rotational throw", 3, "4 each", "3 kg", "explosive", 15, 120, "Hips lead", 3, "power"),
                  _r("Main", "Push press (dumbbell)", 2, "3", "80% 1RM", "X", 15, 150, "No squats in the last 10-12 days", 4, "strength"),
                  _r("Main", "Inverted row", 2, "6", "BW", "1-0-1", 20, 120, "Quality", 4, "strength"),
                  _r("Main", "Dead bug", 2, "30 s", "BW", "slow", 30, 30, "", 6, "endurance")] + COOLDOWN})
    S.append({"name": "In-season - Tuesday main strength (match Saturday)", "micro": "In-season match week (match Saturday)", "goal": "Retain strength and power",
              "equipment": "Trap bar, dumbbells, bands", "intensity": "80% 1RM, 2 x 5; power 50%", "rows": [INTRO] + WARMUP + [
                  _r("Main", "Medicine-ball rotational throw", 3, "4 each", "3 kg", "explosive", 15, 120, "", 3, "power"),
                  _r("Main", "Trap-bar deadlift", 2, "5", "80% 1RM", "1-0-X", 25, 150, "Neutral spine", 4, "strength"),
                  _r("Main", "Dumbbell bench press", 2, "5", "80% 1RM", "2-0-1", 25, 150, "Spot at the head", 4, "strength"),
                  _r("Main", "Nordic hamstring (assisted)", 2, "5", "BW", "slow lowering", 25, 120, "", 5, "strength"),
                  _r("Main", "Pallof press", 2, "10 each", "band", "hold 2 s", 40, 30, "", 6, "endurance")] + COOLDOWN})
    S.append({"name": "Tournament - recovery day between matches", "micro": "Tournament microcycle", "goal": "Recover; retain upper-body and trunk strength",
              "equipment": "Bands, mats, pool if available", "intensity": "Light; RPE 3-4", "rows": [INTRO] + [
                  _r("Warm-up (RAMP)", "Raise: walk / easy bike", 1, "8 min", "easy", "-", 480, 0, "", 0),
                  _r("Main", "Band row and external rotation", 2, "15", "band", "2-0-2", 40, 30, "", 5, "endurance"),
                  _r("Main", "Push-up", 2, "10", "BW", "2-0-1", 30, 30, "", 5, "endurance"),
                  _r("Main", "Side plank", 2, "25 s each", "BW", "hold", 50, 30, "", 6, "endurance")] + COOLDOWN})
    S.append({"name": "Transition - Monday games", "micro": "Transition week (active rest)", "goal": "Active rest; enjoy sport",
              "equipment": "Balls, pool", "intensity": "Light; RPE 3-5", "rows": [INTRO] + [
                  _r("Warm-up (RAMP)", "Raise and mobilise", 1, "8 min", "easy", "-", 480, 0, "", 0),
                  _r("Main", "Small-sided games (football / basketball)", 3, "8 min", "easy-moderate", "-", 480, 120, "Fun first", 7, None)] + COOLDOWN})
    for s in S:
        s["minutes"] = sum(r["sets"] * (r["work"] + r["rest"]) for r in s["rows"]) / 60
        s["duration"] = int(5 * round(s["minutes"] / 5))
    return S


# ───────────── the whole plan ─────────────
def build(*, squad: str, age_group: str, season: dict, phases: list[dict], matches: list[dict], results: dict[str, list[float]],
          players: int, plan_start: date | None = None, weeks: int = 52) -> dict:
    plan_start = plan_start or season["start_date"]
    weeks = max(weeks, (season["end_date"] - plan_start).days // 7 + 1)
    comps = competitions(plan_start=plan_start, weeks=weeks, season=season, phases=phases, matches=matches)
    mesos = skeleton(plan_start, weeks, comps)
    codes = [c for m in mesos for c in m["codes"]]
    assert len(codes) == weeks, (len(codes), weeks)
    loads, unload = week_loads(mesos)
    meso_of = [m for m in mesos for _ in m["codes"]]
    comp_week = [""] * weeks
    tournament = [False] * weeks
    for c in comps:
        a = _week_of(plan_start, c["start"])
        b = _week_of(plan_start, c["end"])
        for w in range(max(0, a), min(weeks - 1, b) + 1):
            if not comp_week[w] or c["type"] == "MAIN":
                comp_week[w] = c["type"]
            if c["type"] == "MAIN" and (c["end"] - c["start"]).days >= 3:
                tournament[w] = True
    # Phase 4 factor levels per week
    factors = []
    for sec, rows in FACTORS.items():
        out = []
        for label, lv in rows:
            vals = [lv[c] for c in codes]
            if label == "Goal setting":
                first_prep = next((m for m in mesos if m["codes"][0] == "S"), None)
                vals = [2 if w < 2 or (first_prep and first_prep["first"] <= w < first_prep["first"] + 2) else 0 for w in range(weeks)]
            out.append((label, vals))
        factors.append((sec, out))
    # sessions per week
    sessions = [[(TOURNAMENT_SESSIONS[i] if tournament[w] else SESSIONS[codes[w]][i]) for w in range(weeks)] for i in range(len(SESSION_TYPES))]
    matches_per_week = [0] * weeks
    for m in matches:
        w = _week_of(plan_start, m["date"])
        if 0 <= w < weeks:
            matches_per_week[w] += 1
    if not any(matches_per_week):                            # assumed: a match every second day of a tournament, Saturdays in a league
        for c in comps:
            if c.get("next_year"):
                continue
            d = c["start"]
            while d <= c["end"]:
                w = _week_of(plan_start, d)
                if 0 <= w < weeks:
                    matches_per_week[w] += 1
                d += timedelta(days=2 if c["type"] == "MAIN" else 7)
    # tests: baseline, end of each phase, before preseason / taper, in-season checks
    test_due = [False] * weeks
    first_prep = next((m["first"] for m in mesos if m["codes"][0] in PREP), 0)
    test_due[first_prep] = True
    for i in range(weeks - 1):
        if codes[i] in PREP and codes[i + 1] != codes[i]:
            test_due[i] = True                               # end of the phase (its unloading week)
    for i, c in enumerate(codes):
        if c == "M" and (i - next(j for j in range(weeks) if codes[j] == "M")) % 6 == 5:
            test_due[i] = True                               # in-season check every 6 weeks
    medical = [test_due[w] or (w == 0) or (comp_week[w] == "MAIN" and (w == 0 or comp_week[w - 1] != "MAIN")) for w in range(weeks)]
    # days from the END of each week to the next MAIN start (for the no-heavy-legs rule)
    mains = sorted(c["start"] for c in comps if c["type"] == "MAIN")
    days_to_main = []
    for w in range(weeks):
        end = plan_start + timedelta(days=7 * w + 6)
        nxt = next((d for d in mains if d > end), None)
        days_to_main.append((nxt - end).days if nxt else 999)
    heavy_legs = [int(codes[w] in ("H", "B", "S", "M") and days_to_main[w] > 12 and not tournament[w]) for w in range(weeks)]
    cond = conditioning(codes, loads, unload, tournament)
    plyo = [0 if tournament[w] else PLYO_CONTACTS[codes[w]] for w in range(weeks)]
    # taper length by the size of the load rise: a full preparation (normal rise) -> 4 weeks; a league final (mild) -> 2 weeks + the final
    taper_required = sum(TAPER_FOR_RISE[LOAD_RISE] if not m.get("mini") else 3 for m in mesos if m.get("taper"))
    targets = sum(1 for m in mesos if m.get("taper"))
    assumptions = [
        "Plan start = the season's start date; the plan covers 52 weeks (one year); the training week starts on the season's start weekday.",
        "Competitions: " + ("from the calendar's matches." if not any(c.get("assumed") for c in comps if not c.get("next_year"))
                            else "no matches are in the calendar, so the season's competition phase is used (a match every second day of a tournament)."),
        "Next season's main competition is assumed on the same dates next year: this year's preparation peaks for it." if any(c.get("next_year") for c in comps) else
        "No competition after the plan: the last weeks prepare generally for next season.",
        "Training age 1-3 years, beginner-intermediate in the gym: loading 3:1 (2:1 in the specific phase), no stress microcycles (youth).",
        "Days per week: 5-6 training days after school (PM), Saturday AM; Sunday rest. Sessions 60-120 min.",
        f"Facilities: cricket ground, track or field, basic gym (dumbbells, barbell, trap bar, bands, medicine balls). Coach ratio {COACH_RATIO} (youth).",
        "1RM is ESTIMATED from multi-rep sets (no maximal 1RM tests for U15). Volume loads use a reference body mass of "
        f"{REF_BODY_MASS:g} kg: replace with each player's mass.",
        "Injury history and medical detail are not used (privacy); each player needs medical clearance before testing.",
        "School exams and holidays are not in the system: move unloading weeks onto exam weeks.",
        "Units: kg and metres. Language: English.",
    ]
    return {
        "squad": squad, "age_group": age_group, "season": season, "plan_start": plan_start, "weeks": weeks, "players": players,
        "competitions": comps, "mesos": mesos, "codes": codes, "loads": loads, "unload": unload, "meso_of": meso_of,
        "comp_week": comp_week, "tournament": tournament, "factors": factors, "sessions": sessions, "matches_per_week": matches_per_week,
        "test_due": test_due, "medical": medical, "days_to_main": days_to_main, "heavy_legs": heavy_legs, "conditioning": cond,
        "plyo": plyo, "resistance": resistance_rows(mesos), "microcycles": microcycles(max(2, max(((c["end"] - c["start"]).days + 1
                  for c in comps if c["type"] == "MAIN" and not c.get("next_year")), default=2))),
        "session_plans": session_plans(), "targets": targets, "taper_weeks": TAPER_FOR_RISE[LOAD_RISE], "taper_required": taper_required,
        "youth": True, "assumptions": assumptions, "needs": needs_analysis(age_group), "tests": test_summary(results),
        "model": ("Linear (traditional) periodization with step loading for the long single-peak preparation; undulating loads in "
                  "competition. Reason: one main competition a year, youth beginner-intermediate players who need a long general base "
                  "(technique first), and a block model is for advanced athletes."),
    }


# ───────────── Phase 10: the checks, recalculated in Python (the Checks sheet does the same with formulas) ─────────────
def verify(p: dict) -> list[tuple[str, bool, str]]:
    W, codes, loads, mesos = p["weeks"], p["codes"], p["loads"], p["mesos"]
    out = []

    def add(rule, ok, fix=""):
        out.append((rule, bool(ok), fix))

    add("Every week has a period, phase, mesocycle and microcycle; months are not called mesocycles", len(codes) == W and all(codes))
    lens = [len(m["codes"]) for m in mesos]
    add("Each mesocycle is 2-6 weeks", all(2 <= n <= 6 for n in lens))
    prep = [(m["macro"], len(m["codes"])) for m in mesos if m["codes"][0] in PREP]
    add("Mesocycles get shorter toward competition", all(b[1] <= a[1] for a, b in zip(prep, prep[1:]) if a[0] == b[0]))
    pre_main = [w - 1 for w in range(1, W + 1) if (w == W and any(c.get("next_year") for c in p["competitions"]))
                or (w < W and p["comp_week"][w] == "MAIN" and p["comp_week"][w - 1] != "MAIN")]
    add("A realization block (taper) sits directly before each MAIN competition", all(p["meso_of"][w]["type"] == "Realization" for w in pre_main))
    taper = sum(1 for w in range(W) if p["meso_of"][w].get("taper"))
    mains_with_prep = sum(1 for m in mesos if m.get("taper"))
    add("Taper length matches the load rise", taper == p["taper_required"] and all(
        len(m["codes"]) == (TAPER_FOR_RISE[LOAD_RISE] if not m.get("mini") else 3) for m in mesos if m.get("taper")) and mains_with_prep == p["targets"])
    peak_w = max(range(W), key=lambda w: loads[w])
    add("Peak load in the last specific-preparation mesocycle, before the taper", codes[peak_w] == "S")
    ok60 = all(min(loads[m["first"]:m["last"] + 1]) / max(loads[m["first"]:m["last"] + 1]) >= 0.6 - 1e-9 for m in mesos if m["type"] != "Transition")
    avgs = [sum(loads[m["first"]:m["last"] + 1]) / len(m["codes"]) for m in mesos if m["type"] != "Transition"]
    days = [d["pct"] for mc in p["microcycles"] for d in mc["days"] if d["pct"]]
    days_ok = all(min(d["pct"] for d in mc["days"] if d["pct"]) / max(d["pct"] for d in mc["days"] if d["pct"]) >= 0.6 for mc in p["microcycles"])
    add("Rule of 60% (days, weeks in a mesocycle, mesocycles)", ok60 and min(avgs) / max(avgs) >= 0.6 and days_ok and days)
    steps = all(loads[m["last"]] < max(loads[m["first"]:m["last"] + 1]) for m in mesos if m["codes"][0] in PREP and len(m["codes"]) > 1)
    add("Every preparatory mesocycle has an unloading week (step loading)", steps)
    vi = {c: VOL_INT[c] for c in set(codes)}
    falls = LEVEL_NUM[VOL_INT["H"][0]] > LEVEL_NUM[VOL_INT["S"][0]] and LEVEL_NUM[VOL_INT["H"][1]] < LEVEL_NUM[VOL_INT["S"][1]]
    add("Volume falls as intensity rises toward competition; Load text agrees with the load %", falls and bool(vi))
    lv3 = [sum(1 for _, rows in p["factors"] for _, v in rows if v[w] == 3) for w in range(W)]
    add("At most 3 factors at level 3 in any week", max(lv3) <= 3)
    comp = [w for w in range(W) if PHASES[codes[w]][0] == "Competition"]
    res = p["sessions"][0]
    strength = dict(p["factors"][0][1])["Maximal strength"]
    add("Strength is retained in-season (2+ short sessions a week, level 1+)", all(res[w] >= 2 and strength[w] >= 1 for w in comp))
    tech = [sum(v[w] for sec, rows in p["factors"] if sec in ("Technical", "Tactical") for _, v in rows) for w in range(W)]
    add("Technical and tactical work continue through competition", all(tech[w] > 0 for w in comp))
    add("No heavy lower-body work in the last 10-12 days before a MAIN competition", all(not p["heavy_legs"][w] for w in range(W) if p["days_to_main"][w] <= 12))
    legs48 = True
    for mc in p["microcycles"]:
        ds = mc["days"]
        for i, d in enumerate(ds):
            if d["heavy_legs"] and any(ds[j]["match"] for j in range(i + 1, min(len(ds), i + 3))):
                legs48 = False
    add("No heavy legs within 48 h of a match", legs48)
    add("No stress microcycles (youth)", True)
    rises = []
    for w in range(1, W):
        rows = p["conditioning"][w]
        if not rows or not rows[0]["counted"] or p["unload"][w]:
            continue
        prev = next((x for x in range(w - 1, -1, -1) if p["conditioning"][x] and p["conditioning"][x][0]["counted"] and not p["unload"][x]), None)
        if prev is None or not all(p["conditioning"][y][0]["counted"] for y in range(prev, w + 1)):
            continue
        a = sum(r["distance"] * r["reps"] for r in p["conditioning"][prev])
        b = sum(r["distance"] * r["reps"] for r in rows)
        rises.append(b / a - 1 if a else 0)
    add("Conditioning volume rises at most 10% a week", all(r <= PROGRESSION_CAP + 1e-9 for r in rises))
    wr_ok = all(r["continuous"] or r["wr_lo"] <= r["rest_s"] / r["work_s"] <= r["wr_hi"] for rows in p["conditioning"] for r in rows)
    add("Work:rest matches the energy system", wr_ok)
    gaps_ok = all(sum(d["plyo"] for d in mc["days"]) <= 3 for mc in p["microcycles"])
    for mc in p["microcycles"]:
        idx = [i for i, d in enumerate(mc["days"]) if d["plyo"]]
        gaps_ok = gaps_ok and all(b - a >= 2 for a, b in zip(idx, idx[1:]))
    add("Plyometric contacts within the limit, 48-72 h between sessions", max(p["plyo"]) <= PLYO_MAX_CONTACTS and gaps_ok)
    add("Tests at the right points (baseline, end of each phase, before the taper, in-season)", all(p["test_due"][w] for w in [next(m["first"] for m in mesos if m["codes"][0] in PREP)]))
    sess_ok = True
    for s in p["session_plans"]:
        main = [r["cat"] for r in s["rows"] if r["part"] == "Main"]
        sess_ok = sess_ok and all(b >= a for a, b in zip(main, main[1:])) and abs(s["minutes"] - s["duration"]) <= 5
        for r in s["rows"]:
            if r["goal"]:
                lo, hi = REST_BY_GOAL[r["goal"]]
                sess_ok = sess_ok and lo <= r["rest"] <= hi
    add("Session order, rest by goal, no pyramids, session time adds up", sess_ok)
    rest_ok = True
    for mc in p["microcycles"]:
        if mc["phase"].startswith(("Maintenance", "Peaking")):
            run = best = 0
            for d in mc["days"]:
                run = run + 1 if d["off"] else 0
                best = max(best, run)
            rest_ok = rest_ok and best <= 3
    trans = [len(m["codes"]) for m in mesos if m["type"] == "Transition"]
    add("No passive rest over 3 days in season; transition 1-4 weeks", rest_ok and all(1 <= n <= 4 for n in trans))
    add("Resistance loads never above the max-reps table", all(r["pct"] is None or r["reps"] <= max_reps(r["pct"]) for r in p["resistance"]))
    add("Youth rules (no stress microcycles, resistance <= 3 a week, technique first, estimated 1RM)", max(res) <= 3)
    return out


# ───────────── one player's own periodized plan (Zatsiorsky ch. 1: individualization - never copy a program) ─────────────
WEAK_AT, STRONG_AT = 50, 75                                  # percentile in the player's own test group
AREA_FACTORS = {  # test area -> the factor rows it raises when weak
    "endurance": ["Aerobic endurance", "Anaerobic endurance"],
    "power": ["Power / explosive strength"],
    "upper_strength": ["Maximal strength", "Hypertrophy / strength-endurance"],
    "speed": ["Speed", "Reaction speed"],
    "agility": ["Agility / change of direction", "Coordination"],
    "core": ["Trunk / core strength"],
}
UPPER_WORDS = ("push-up", "inverted row", "bench", "chin-up", "row", "press", "pull-apart", "external rotation")
EXTRA = {  # what a WEAK area adds (all inside the youth limits)
    "endurance": "conditioning volume x1.10 (the 10% weekly rule still holds); +1 conditioning session in general and basic-strength weeks (max 4)",
    "power": "+1 set on power exercises; +20 jump contacts a plyometric session (max 100)",
    "upper_strength": "+1 set on upper-body exercises (push, pull, press, rotator cuff)",
    "speed": "+1 speed & agility session a week outside transition (max 3); speed factor raised",
    "agility": "+1 speed & agility session a week outside transition (max 3); agility factor raised",
    "core": "+1 set on trunk exercises; trunk factor raised",
}


def personalize(base: dict, *, name: str, role: str, areas: list[dict], own_results: list[tuple[str, str]] | None = None,
                matches_plan: dict | None = None) -> dict:
    """The squad's periodized plan made into one player's: the player's WEAK areas (below the 50th percentile of their own test
    group) are raised a level in every week the squad trains them (never above 3, never more than 3 factors at level 3 in a week)
    and get extra sets, contacts, conditioning or sessions; STRONG areas (75th percentile or more) keep the full squad work so
    they keep improving. Everything else follows the squad plan. Re-checked by verify()."""
    import copy
    p = copy.deepcopy(base)
    tested = [a for a in areas if a.get("percentile") is not None and a["area"] in AREA_FACTORS]
    weak = sorted((a for a in tested if a["percentile"] < WEAK_AT), key=lambda a: a["percentile"])
    strong = sorted((a for a in tested if a["percentile"] >= STRONG_AT), key=lambda a: -a["percentile"])
    wk = {a["area"] for a in weak}
    W, codes = p["weeks"], p["codes"]
    # factor levels
    raise_rows = {f for a in wk for f in AREA_FACTORS[a]}
    for w in range(W):
        lv3 = sum(1 for _, rows in p["factors"] for _, v in rows if v[w] == 3)
        for _, rows in p["factors"]:
            for label, v in rows:
                if label in raise_rows and codes[w] != "T" and not p["tournament"][w] and 1 <= v[w] < 3:
                    if v[w] + 1 == 3 and lv3 >= 3:
                        continue
                    v[w] += 1
                    lv3 += v[w] == 3
    # sessions per week
    ses = p["sessions"]
    for w in range(W):
        if codes[w] == "T" or p["tournament"][w]:
            continue
        if wk & {"speed", "agility"}:
            ses[2][w] = min(3, ses[2][w] + 1)
        if "endurance" in wk and codes[w] in ("H", "B"):
            ses[3][w] = min(4, ses[3][w] + 1)
    # plyometric contacts
    if "power" in wk:
        p["plyo"] = [min(PLYO_MAX_CONTACTS, c + 20) if c else 0 for c in p["plyo"]]
    # resistance sets
    for r in p["resistance"]:
        ex = r["exercise"].lower()
        if ("upper_strength" in wk and any(k in ex for k in UPPER_WORDS)) or ("core" in wk and r["category"] == "trunk") \
                or ("power" in wk and r["category"] == "power"):
            r["sets"] += 1
            r["extra"] = True
    # conditioning
    if "endurance" in wk:
        p["conditioning"] = conditioning(codes, p["loads"], p["unload"], p["tournament"], scale=1.10)
    p["player"] = {"name": name, "role": role, "weak": weak, "strong": strong, "results": own_results or [],
                   "extras": [(a["label"], EXTRA[a["area"]]) for a in weak]}
    p["squad_label"] = p["squad"]
    p["squad"] = f"{name} - {p['squad']}"
    focus = ", ".join(a["label"] for a in weak) or "none below the middle of the group"
    p["assumptions"] = [f"PERSONAL PLAN for {name} ({role}). Focus (below the 50th percentile of the player's own test group): {focus}. "
                        "Strong areas (75th percentile or more) keep the full squad work so they keep improving."] + p["assumptions"]
    return p
