"""Seasonal Strength & Conditioning plan built on Zatsiorsky & Kraemer, Science and Practice of Strength Training (2nd ed.),
chapter 5 "Timing in Strength Training" and chapter 10 "Strength Training for Young Athletes" (NSCA youth guidelines).
Pure module: no database.

Structure (ch. 5): macrocycle -> periods (preparation, competition, transition) -> mesocycles (typically 4 weeks, 2-6) ->
microcycles (1 week; in competition matched to the competition) -> sessions.
  * Mesocycle types: ACCUMULATION (basic motor abilities, submaximal and repeated-effort methods, judged by tests),
    TRANSMUTATION (turns general fitness into specific preparedness), REALIZATION (pre-competition: low load so the delayed
    transformation of the earlier work shows as performance; 2-4 weeks).
  * At most 2 targets per mesocycle, about 70-80% of the work (35-40% each); every other ability gets RETAINING loads.
    Targets change in sequence ("new planning", figure 5.5b); strength-type targets before endurance (superposition).
  * Rule of 60%: the lightest microcycle carries about 60% of the volume of the heaviest; the same holds for mesocycles.
  * One stable exercise complex through a mesocycle; vary the load, not the exercises; change the complex at the next block.
  * Increasing strength needs at least 3 heavy sessions a week; retaining it needs 2 short (30-40 min) sessions a week.
    A short preseason before a long competition period means strength work must stay in-season (training residuals).
  * Continuous training is a must: the transition keeps minimal loads (calisthenics, flexibility, aerobic), never a full stop.
  * Session order: warm-up, power and fast drills while fresh, large multi-joint before small, main before assistance,
    flexibility and relaxation between heavy drills (shoulders), cool-down.
Youth adaptation (ch. 10): 5-10 min warm-up and cool-down; begin with 1 set of 6-8 exercises at 12-15 repetitions; progress to
1-3 sets of 6-15 repetitions on 8-10 exercises, 2-3 non-consecutive days a week; load +5-10% at a time; multi-joint lifts with
light loads after 6-8 weeks; no heavy explosive lifts; in-season 1-2 sessions of 25-45 min at least a day apart, 2-3 sets of 8-10.
Doses are repetitions and sets with bodyweight, bands, medicine balls and light loads - never a % of a maximal lift.
Every number is a PROPOSAL for the coach.
"""
from __future__ import annotations

from datetime import date, timedelta

from .exercise_kinds import PHASE_KINDS
from .individual_plan import _pick
from .test_battery import AREA_LABEL

SOURCE = "Zatsiorsky & Kraemer, Science and Practice of Strength Training, 2nd ed., ch. 5 (timing, periodization) and ch. 10 (young athletes)"

# Strength-type abilities are developed before endurance (ch. 5, superposition of training effects).
SEQUENCE_ORDER = ["power", "upper_strength", "core", "speed", "agility", "endurance"]
PERIOD_OF = {"pre_season": "Preparation", "pre_competition": "Preparation", "in_season": "Competition", "transition": "Transition"}
MESO_LABEL = {"accumulation": "Accumulation", "transmutation": "Transmutation", "realization": "Realization",
              "competition": "Competition (retaining)", "transition": "Transition (active rest)"}
# Relative volume of each mesocycle type (100 = the heaviest); the lightest is about 60% (rule of 60%).
MESO_VOLUME = {"accumulation": 100, "transmutation": 90, "realization": 65, "competition": 60, "transition": 60}
# Load wave of microcycles inside a mesocycle (ch. 5): loading weeks then an unloading week at ~60% of the heaviest.
WAVES = {1: [1.0], 2: [1.0, 0.6], 3: [0.85, 1.0, 0.6], 4: [0.8, 0.9, 1.0, 0.6], 5: [0.8, 0.9, 1.0, 0.85, 0.6], 6: [0.8, 0.9, 1.0, 0.85, 0.95, 0.6]}
MICRO_TYPE = {1.0: "Loading (high)", 0.95: "Loading", 0.9: "Loading", 0.85: "Ordinary", 0.8: "Ordinary", 0.6: "Recovery (unloading)"}
EX_PHASE = {"accumulation": "pre_season", "transmutation": "pre_competition", "realization": "pre_competition",
            "competition": "in_season", "transition": "transition"}
# Workout load by restoration time (ch. 5): small <12 h, medium 12-24 h, substantial 24-48 h, large 48-72 h.
INTENSITY = {"accumulation": "Substantial (24-48 h recovery)", "transmutation": "Substantial to large (24-72 h)",
             "realization": "Medium (12-24 h)", "competition": "Medium (12-24 h)", "transition": "Small (<12 h)"}

METHOD = {
    "accumulation": {
        "methods": ["Repeated effort", "Submaximal effort"],
        "method": "Repeated-effort and submaximal-effort methods (ch. 4): sets end close to, never past, the point where technique breaks. "
                  "For U15 the aim is technique and neural (coordination) strength, not muscle size (ch. 10).",
        "dose": "First 6-8 weeks of training: 1 set x 12-15 reps on 6-8 exercises (bodyweight, bands, broomstick for new lifts), then 2-3 sets x 8-12 reps "
                "(no more than 10-12 reps per set for strength, except trunk exercises).",
        "rest": "1.5-2 min between sets", "sessions": 3, "minutes": "45-60",
        "frequency": "3 sessions a week on non-consecutive days (Mon, Wed, Fri); each exercise at least twice a week; 48 h or more between heavy leg sessions.",
        "exercises": 8},
    "transmutation": {
        "methods": ["Dynamic effort", "Repeated effort"],
        "method": "Dynamic-effort method (ch. 4, 8): light loads moved as fast as possible and released - jumps, medicine-ball throws, sprints - to raise the rate of "
                  "force development that short cricket actions (bowling, hitting, throwing, under 0.3 s) depend on; strength is kept with repeated-effort sets.",
        "dose": "Explosive: 3 sets x 3-5 reps at maximal speed, fresh, straight after the warm-up. Strength: 2-3 sets x 8-10 reps. Add 5-10% load only when every rep is clean.",
        "rest": "Explosive 2-3 min (full recovery); strength 1.5-2 min", "sessions": 3, "minutes": "45-60",
        "frequency": "3 sessions a week, non-consecutive; each exercise at least twice a week; no jumps or heavy legs the day after bowling.",
        "exercises": 8},
    "realization": {
        "methods": ["Dynamic effort (low volume)"],
        "method": "Realization (ch. 5): the load drops so the earlier work turns into performance (delayed transformation). Keep the speed and quality, cut the volume - "
                  "fewer sessions, exercises and sets. A detraining load is acceptable while tapering (ch. 8).",
        "dose": "Explosive 2-3 sets x 3 reps; strength 2 sets x 6-8 reps. No new exercises.",
        "rest": "2-3 min", "sessions": 2, "minutes": "30-40",
        "frequency": "2 short sessions a week; the last hard lower-body session 10-12 days before the first match (ch. 5).",
        "exercises": 5},
    "competition": {
        "methods": ["Retaining load", "Dynamic effort"],
        "method": "Retaining loads (ch. 5): two short sessions a week keep strength and power through the season - a short preseason is lost within weeks otherwise. "
                  "Keep some high-resistance work in season (ch. 4) and 2 explosive sessions a week to retain power (ch. 8).",
        "dose": "Strength 2-3 sets x 8-10 reps at a challenging load; explosive 2 sets x 3 reps. Never to failure.",
        "rest": "1.5-2 min; explosive 2-3 min", "sessions": 2, "minutes": "25-40",
        "frequency": "2 sessions a week, at least a day apart; never the day before a match; upper body and trunk only the day after bowling.",
        "exercises": 6},
    "transition": {
        "methods": ["Continuous light training"],
        "method": "Continuous training (ch. 5): minimal loads keep fitness - calisthenics, flexibility, aerobic play and other sports - never a full stop.",
        "dose": "1-2 sets x 10-15 bodyweight reps; 20-30 min easy aerobic activity.",
        "rest": "as needed", "sessions": 2, "minutes": "30",
        "frequency": "2 light sessions a week.",
        "exercises": 5},
}
EXCLUDED = ("Maximal-effort method (1-3 reps near the maximum) is not used: the book does not recommend it for beginners or young athletes because of "
            "the injury risk (ch. 4, ch. 7).")
COMPLEX_EVERY = 2                 # change the exercise complex every 2 mesocycles; the dominant method changes every mesocycle (ch. 8)
# Muscle groups every young athlete trains whatever the sport (ch. 8 injury prevention): trunk, hips, lateral knee/ankle, landing.
INJURY_SLOTS = [("core", ("trunk_stability",)), ("agility", ("landing", "mobility_balance")), ("power", ("lower_limb_resilience", "landing"))]

SESSION_ORDER = ["Warm-up 5-10 min (jog or skip, activation, mobility)",
                 "Power and speed drills while fresh",
                 "Large multi-joint strength exercises",
                 "Assistance and single-joint exercises",
                 "Flexibility / relaxation between heavy drills (shoulders, hips)",
                 "Trunk and injury prevention",
                 "Cool-down 5-10 min (easy aerobic, stretching)"]
KIND_ORDER = {"speed": 0, "plyometric_power": 0, "rotation_power": 1, "agility": 1, "repeat_sprint": 2, "leg_strength": 3, "upper_strength": 3,
              "landing": 4, "aerobic": 5, "trunk_stability": 6, "lower_limb_resilience": 7, "shoulder_prehab": 7, "grip_wrist": 7, "mobility_balance": 8}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _stem(name: str) -> str:
    return " ".join(name.lower().replace(",", " ").split()[:2])


def _week_kind(d: date, phases: list[dict]) -> str:
    for p in phases:
        if p["start_date"] <= d <= p["end_date"]:
            return p["phase_type"]
    before = [p for p in phases if p["end_date"] < d]
    return before[-1]["phase_type"] if before else phases[0]["phase_type"]


def _blocks(n: int) -> list[int]:
    """Split n weeks into mesocycles of about 4 weeks (2-6), never a single week left alone."""
    if n <= 6:
        return [n]
    out, left = [], n
    while left > 6:
        out.append(4)
        left -= 4
    if left == 1:
        out[-1] += 1
    elif left:
        out.append(left)
    return out


def order_targets(squad_areas: list[dict]) -> list[str]:
    """squad_areas: [{area, priority (players below the middle), median}] -> the areas in the order they are targeted:
    strength-type areas by need, endurance last (ch. 5 superposition: strength -> endurance works, the reverse does not)."""
    need = sorted((a for a in squad_areas if a["area"] in SEQUENCE_ORDER), key=lambda a: (-a["priority"], a["median"] if a["median"] is not None else 50))
    top = [a["area"] for a in need]
    strength = [a for a in top if a != "endurance"]            # "focus first on strength training and afterward on endurance" (ch. 8)
    return strength + [a for a in top if a == "endurance"]


def build_macrocycle(*, season: dict, phases: list[dict], squad_areas: list[dict], role_groups: list[str], today: date,
                     matches: list[date] | None = None, lead_in_from: date | None = None) -> dict:
    """season: {name, start_date, end_date}; phases: season phases [{phase_type, start_date, end_date}];
    squad_areas: [{area, priority, median}] from the squad's test ranks; role_groups: exercise lists of the squad's roles.
    lead_in_from: when the season starts later, the weeks from this date to the start become a realization lead-in."""
    phases = sorted(phases, key=lambda p: p["start_date"])
    s0, e0 = season["start_date"], season["end_date"]
    weeks: list[dict] = []
    if lead_in_from and lead_in_from < s0:
        d = lead_in_from - timedelta(days=lead_in_from.weekday())
        while d < s0:
            weeks.append({"start": d, "end": min(d + timedelta(days=6), s0 - timedelta(days=1)), "kind": "lead_in", "in_season": False})
            d += timedelta(days=7)
        if weeks:
            weeks[0]["start"] = max(weeks[0]["start"], lead_in_from)
            if len(weeks) > 1 and (weeks[0]["end"] - weeks[0]["start"]).days < 2:     # a 1-2 day stub joins the next week
                weeks[1]["start"] = weeks[0]["start"]
                weeks.pop(0)
    d = s0
    while d <= e0:
        weeks.append({"start": d, "end": min(d + timedelta(days=6), e0), "kind": _week_kind(d, phases), "in_season": True})
        d += timedelta(days=7)

    # mesocycles: contiguous runs of the same season phase, split into ~4-week blocks; typed by the period
    runs: list[list[int]] = []
    for i, w in enumerate(weeks):
        if runs and weeks[runs[-1][-1]]["kind"] == w["kind"]:
            runs[-1].append(i)
        else:
            runs.append([i])
    mesos = []
    first_comp = next((i for i, w in enumerate(weeks) if w["kind"] == "in_season"), None)
    for run in runs:
        kind = weeks[run[0]]["kind"]
        sizes = _blocks(len(run))
        k = 0
        for sz in sizes:
            idx = run[k:k + sz]
            k += sz
            if kind == "lead_in":
                t = "realization"
            elif kind == "pre_season":
                t = "accumulation"
            elif kind == "pre_competition":
                t = "transmutation"
            elif kind == "in_season":
                t = "competition"
            else:
                t = "transition"
            mesos.append({"type": t, "weeks": idx})
    # the last 2-4 preparation weeks before the first competition week become the realization mesocycle (delayed transformation)
    if first_comp is not None:
        prep = [m for m in mesos if m["weeks"][-1] < first_comp and m["type"] in ("accumulation", "transmutation")]
        if prep and not any(m["type"] == "realization" and m["weeks"][-1] == first_comp - 1 for m in mesos):
            last = prep[-1]
            total_prep = sum(len(m["weeks"]) for m in prep)
            r = 2 if total_prep < 10 else 3 if total_prep < 20 else 4
            if len(last["weeks"]) > r + 1:
                mesos.insert(mesos.index(last) + 1, {"type": "realization", "weeks": last["weeks"][-r:]})
                last["weeks"] = last["weeks"][:-r]
            elif len(prep) > 1 or len(last["weeks"]) >= 2:
                last["type"] = "realization"

    # targets: sequential, 2 per development mesocycle; competition retains the top needs
    order = order_targets(squad_areas) or ["power", "core"]
    medians = {a["area"]: a["median"] for a in squad_areas}
    dev = [m for m in mesos if m["type"] in ("accumulation", "transmutation")]
    for i, m in enumerate(dev):
        a = (2 * i) % len(order)
        m["targets"] = [order[a], order[(a + 1) % len(order)]] if len(order) > 1 else order[:1]
    comp = [m for m in mesos if m["type"] == "competition"]
    for i, m in enumerate(comp):                                  # in-season: the emphasis keeps rotating, everything else is retained
        a = (2 * i) % len(order)
        m["targets"] = [order[a], order[(a + 1) % len(order)]] if len(order) > 1 else order[:1]
    for m in mesos:
        if "targets" not in m:
            m["targets"] = order[:2] if m["type"] == "realization" else []

    # exercise complexes (ch. 5, 8): one stable complex per mesocycle, the same exercises kept for 2 mesocycles, then a new complex;
    # the youth injury-prevention groups (trunk, hips / lower limb, landing) are in every complex
    used: dict[str, set] = {}
    keep_for: dict[str, list] = {}
    prev_names: set = set()
    prev_block = 0
    out_mesos, wk_rows = [], []
    num_by_type: dict[str, int] = {}
    block = 0
    for n, m in enumerate(mesos, 1):
        t, spec = m["type"], METHOD[m["type"]]
        num_by_type[t] = num_by_type.get(t, 0) + 1
        phase = EX_PHASE[t]
        allowed = set(PHASE_KINDS[phase])
        if n == 1 or (n - 1) % COMPLEX_EVERY == 0 or any(e["kind"] not in allowed for v in keep_for.values() for e in v):
            block += 1
            for area, ex in keep_for.items():
                used[area] = used.get(area, set()) | {e["name"] for e in ex}
            keep_for = {}
        # one BASE exercise per area, kept for the whole block (2 mesocycles); a target area adds one more exercise this mesocycle
        complex_, taken = [], set()
        for area in SEQUENCE_ORDER:
            if t == "transition" and area not in ("endurance", "core", "agility"):
                continue
            target = area in m["targets"]
            med = medians.get(area)
            base = [e for e in keep_for.get(area, []) if e["kind"] in allowed and e["name"] not in taken][:1]
            if not base:
                base = _pick(area, phase, role_groups, 1, priority=False, percentile=None,
                             ctx={"taken": set(taken), "seed": f"{block}{area}", "used_before": used.get(area, set())})
                keep_for[area] = base
            taken.update(e["name"] for e in base)
            complex_ += [{**e, "area": area, "area_label": AREA_LABEL[area], "role": "Target" if target else "Retain"} for e in base]
            if target and t != "transition":
                extra = _pick(area, phase, role_groups, 3, priority=med is not None, percentile=med,
                              ctx={"taken": set(taken), "seed": f"{n}{area}", "used_before": used.get(area, set())})
                extra = [e for e in extra if _stem(e["name"]) not in {_stem(x) for x in taken}][:1]   # no two versions of one exercise
                taken.update(e["name"] for e in extra)
                complex_ += [{**e, "area": area, "area_label": AREA_LABEL[area], "role": "Target"} for e in extra]
        cap = spec["exercises"]
        if len(complex_) > cap:                                   # realization / competition: fewer exercises, targets and trunk first
            pri = lambda e: (e["role"] != "Target", e["kind"] not in ("trunk_stability", "lower_limb_resilience", "landing"), KIND_ORDER.get(e["kind"], 9))
            complex_ = sorted(complex_, key=pri)[:cap]
        for area, kinds in INJURY_SLOTS:                          # always one trunk and one hip / lower-limb / landing exercise
            if not any(e["kind"] in kinds for e in complex_) and any(k in allowed for k in kinds):
                extra = next((e for e in _pick(area, phase, role_groups, 6, ctx={"taken": {x["name"] for x in complex_}, "seed": f"inj{block}"})
                              if e["kind"] in kinds), None)
                if extra:
                    complex_.append({**extra, "area": area, "area_label": AREA_LABEL[area], "role": "Injury prevention"})
        complex_.sort(key=lambda e: KIND_ORDER.get(e["kind"], 9))                    # session order: fast and power first
        wave = WAVES[min(len(m["weeks"]), 6)] if t not in ("competition", "transition", "realization") else (
            [1.0, 0.9, 0.8, 0.7][-len(m["weeks"]):] if t == "realization" else
            ([1.0, 0.9, 1.0, 0.8, 1.0, 0.9][:len(m["weeks"])] if t == "competition" and len(m["weeks"]) >= 3 else [1.0] * len(m["weeks"])))
        if t == "realization" and len(wave) < len(m["weeks"]):
            wave = [1.0] * (len(m["weeks"]) - len(wave)) + wave                       # the taper ends right before competition
        for j, wi in enumerate(m["weeks"]):
            w = weeks[wi]
            vol = round(MESO_VOLUME[t] * wave[j])
            match_days = [d for d in (matches or []) if w["start"] <= d <= w["end"]]
            sessions = spec["sessions"] if wave[j] > 0.6 or t in ("competition", "transition") else max(1, spec["sessions"] - 1)
            if match_days:
                sessions = min(sessions, 2 if len(match_days) <= 1 else 1)
            days = (e0 - s0).days + 1
            micro = (f"Tournament microcycle ({days} days)" if t == "competition" and days < 28 else "Competition microcycle" if t == "competition" else "Pre-competition" if t == "realization" else
                     "Active rest" if t == "transition" else MICRO_TYPE.get(wave[j], "Ordinary"))
            wk_rows.append({"week": len(wk_rows) + 1, "start": w["start"], "end": w["end"], "before_season": not w["in_season"],
                            "period": "Preparation (lead-in)" if not w["in_season"] else PERIOD_OF[w["kind"]],
                            "mesocycle": n, "meso_type": t, "meso_label": MESO_LABEL[t], "microcycle": micro, "volume": vol,
                            "intensity": INTENSITY[t], "sessions": sessions, "matches": len(match_days),
                            "targets": [AREA_LABEL[a] for a in m["targets"]]})
        out_mesos.append({"number": n, "type": t, "label": f"{MESO_LABEL[t]} {num_by_type[t]}", "start": weeks[m["weeks"][0]]["start"],
                          "end": weeks[m["weeks"][-1]]["end"], "weeks": len(m["weeks"]),
                          "targets": [{"area": a, "label": AREA_LABEL[a], "share": "35-40% of the work" if t in ("accumulation", "transmutation") else "kept"} for a in m["targets"]],
                          "retained": [AREA_LABEL[a] for a in SEQUENCE_ORDER if a not in m["targets"]],
                          "methods": spec["methods"], "new_complex": block != prev_block,
                          "method": spec["method"], "dose": spec["dose"], "rest": spec["rest"], "frequency": spec["frequency"],
                          "minutes": spec["minutes"], "intensity": INTENSITY[t], "complex": complex_,
                          "microcycle": microcycle_template(t, spec["sessions"], complex_)})
        prev_names = {e["name"] for e in complex_}
        prev_block = block

    short = (e0 - s0).days + 1 < 28
    notes = [f"Built on {SOURCE}. Every number is a proposal for the coach.",
             "Volume is relative (100 = the heaviest week); the lightest week is about 60% of the heaviest (rule of 60%). Doses are repetitions and sets "
             "with bodyweight, bands, medicine balls and light loads - never a percentage of a maximal lift (U15).",
             "Each development mesocycle has at most two targets that get about 70-80% of the work; every other ability is kept with retaining loads.",
             "The exercise complex stays the same through a mesocycle and is kept for two mesocycles before it changes; the dominant method changes every "
             "mesocycle and the load follows the rule of 60% (ch. 5, ch. 8).",
             "Targets: strength-type abilities first, endurance last (ch. 5 superposition; ch. 8 'strength first, endurance afterward')."]
    if short:
        notes.append("Short season (a tournament): there is no time to build fitness inside it, so it is one competition mesocycle with retaining loads; "
                     "the competition microcycle is matched to the tournament. Strength is built before the season.")
    if any(not w["in_season"] for w in weeks):
        notes.append("The weeks before the season starts are planned as a realization (pre-competition) lead-in: the earlier work turns into "
                     "performance during reduced loading (delayed transformation).")
    if not any(m["type"] in ("accumulation", "transmutation") for m in mesos):
        notes.append("No preparation weeks in this season, so no new strength is built inside it: development work belongs to the next preparation period.")
    return {"source": SOURCE, "season": {"name": season["name"], "start_date": s0, "end_date": e0}, "generated_on": today,
            "target_order": [AREA_LABEL[a] for a in order], "mesocycles": out_mesos, "weeks": wk_rows,
            "session_order": SESSION_ORDER, "rules": RULES, "notes": notes}


RULES = [
    "Methods excluded for U15: " + EXCLUDED,
    "Every young athlete trains the abdominals, trunk extensors and hip muscles, lateral knee and ankle control, landing (stretch-shortening) drills and "
    "left-right balance, whatever the sport (ch. 8); a strength difference of 10% or more between the legs is corrected first.",
    "Prepubescent and early-pubertal players gain strength mainly through the nervous system: coach technique and coordination, not muscle size (ch. 10).",
    "Train as fresh as possible: speed, power and technique work right after the warm-up; never to exhaustion in strength sets.",
    "At least 48 h between heavy lower-body sessions; small muscle groups (calves, forearms) may be trained more often.",
    "Do not repeat the same heavy session on consecutive days - the fatigue of similar workouts adds up.",
    "Increase the load by 5-10% only when every repetition of every set is done with good technique.",
    "Fast bowlers: no jumps, sprints or heavy leg work the day after bowling; nothing hard the day before a match.",
    "Growth spurt: keep jumps and sprints at the low end and add landing, mobility and trunk work.",
    "Keep training through the season: stopping loses a short preseason's gains within weeks (training residuals).",
    "5-10 min warm-up and cool-down every session; stop and refer to the physiotherapist if there is pain.",
]


HEAVY_LEGS = {"leg_strength", "plyometric_power", "speed", "repeat_sprint"}       # heavy or maximal-speed leg work: >= 48 h apart


def microcycle_template(t: str, sessions: int, complex_: list[dict]) -> list[dict]:
    """The week. With 3 sessions every exercise is done twice (ch. 5: each exercise of the complex at least twice a week):
    leg and explosive work on Mon and Fri (more than 48 h apart), upper body and trunk on Wed and on one of the other days.
    With 2 sessions the whole complex is done twice, except that the second in-season session has no heavy legs (match week)."""
    names = lambda xs: ", ".join(e["name"] for e in xs) or "-"
    legs = [e for e in complex_ if e["kind"] in HEAVY_LEGS]
    rest = [e for e in complex_ if e["kind"] not in HEAVY_LEGS]
    if t == "transition":
        slots = {"Tue": "Calisthenics, flexibility and easy aerobic play: " + names(complex_), "Fri": "Another sport or easy aerobic activity"}
    elif sessions >= 3:
        half = (len(rest) + 1) // 2
        mon, wed, fri = legs + rest[:half], rest, legs + rest[half:]
        order = lambda xs: sorted(xs, key=lambda e: KIND_ORDER.get(e["kind"], 9))
        slots = {"Mon": "A - " + names(order(mon)), "Wed": "B - upper body, trunk, conditioning: " + names(order(wed)), "Fri": "C - " + names(order(fri))}
    elif t == "competition":
        slots = {"Mon": "A - whole complex, short (25-40 min): " + names(complex_),
                 "Thu": "B - upper body, trunk, low-volume explosive drills; no heavy legs before the weekend match: " + names(rest + [e for e in legs if e["kind"] in ("speed", "agility")][:1])}
    else:
        slots = {"Mon": "A - whole complex, reduced: " + names(complex_), "Thu": "B - whole complex, reduced (last hard leg work 10-12 days before the first match): " + names(complex_)}
    return [{"day": d, "session": slots.get(d) or ("Cricket training / rest" if d not in ("Sat", "Sun") else "Match or rest")} for d in DAYS]
