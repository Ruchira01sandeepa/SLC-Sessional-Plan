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
        "method": "Submaximal and repeated-effort methods: technique first, sets stopped before failure.",
        "dose": "Weeks 1-6 of training: 1-2 sets x 12-15 reps (bodyweight, bands, broomstick for new lifts). Then 2-3 sets x 8-12 reps.",
        "rest": "1-2 min between sets", "sessions": 3, "minutes": "45-60",
        "frequency": "3 sessions a week on non-consecutive days (e.g. Mon, Wed, Fri) - at least 48 h between heavy lower-body work.",
        "exercises": 8},
    "transmutation": {
        "method": "More specific work: fast, explosive drills first while fresh (jumps, medicine-ball throws, sprints), then strength 8-10 reps.",
        "dose": "Power: 3-5 sets x 3-5 fast reps, full recovery. Strength: 2-3 sets x 8-10 reps. Load +5-10% only when all reps are clean.",
        "rest": "2 min (power: walk-back / full recovery)", "sessions": 3, "minutes": "45-60",
        "frequency": "2-3 sessions a week, non-consecutive; no heavy legs the day after bowling.",
        "exercises": 8},
    "realization": {
        "method": "Low load so the earlier work shows (delayed transformation): keep intensity, cut volume - fewer sessions, exercises and sets.",
        "dose": "2 sets x 6-8 quality reps; power drills 2-3 sets x 3 reps. No new exercises.",
        "rest": "2 min", "sessions": 2, "minutes": "30-40",
        "frequency": "2 short sessions a week; the last hard lower-body session 7-10 days before the first match.",
        "exercises": 5},
    "competition": {
        "method": "Retaining loads: two short sessions keep strength and power through the season (a short preseason is lost otherwise).",
        "dose": "2-3 sets x 8-10 reps; power 2 sets x 3 reps. Never to failure.",
        "rest": "1-2 min", "sessions": 2, "minutes": "25-40",
        "frequency": "1-2 sessions a week, at least a day apart; never the day before a match; upper body and trunk only the day after bowling.",
        "exercises": 6},
    "transition": {
        "method": "Continuous training: minimal loads keep fitness (calisthenics, flexibility, aerobic play, other sports) - never a full stop.",
        "dose": "1-2 sets x 10-15 bodyweight reps; 20-30 min easy aerobic activity.",
        "rest": "as needed", "sessions": 2, "minutes": "30",
        "frequency": "2 light sessions a week.",
        "exercises": 5},
}
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
    most needed first, then (ch. 5 superposition) strength-type before endurance within the same need."""
    need = sorted((a for a in squad_areas if a["area"] in SEQUENCE_ORDER), key=lambda a: (-a["priority"], a["median"] if a["median"] is not None else 50))
    top = [a["area"] for a in need]
    return sorted(top[:4], key=SEQUENCE_ORDER.index) + top[4:]


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

    # exercise complexes: stable within a mesocycle; a new complex at the next block (used_before steers away from repeats)
    used: dict[str, set] = {}
    out_mesos, wk_rows = [], []
    num_by_type: dict[str, int] = {}
    for n, m in enumerate(mesos, 1):
        t, spec = m["type"], METHOD[m["type"]]
        num_by_type[t] = num_by_type.get(t, 0) + 1
        phase = EX_PHASE[t]
        retained = [a for a in SEQUENCE_ORDER if a not in m["targets"]]
        plan = [(a, 3 if t in ("accumulation", "transmutation") else 2, True) for a in m["targets"]] + [(a, 1, False) for a in retained]
        complex_, taken = [], set()
        for area, cnt, target in plan:
            med = medians.get(area)
            ex = _pick(area, phase, role_groups, cnt, priority=target and med is not None, percentile=med if target else None,
                       ctx={"taken": taken, "seed": f"{t}{n}{area}", "used_before": used.get(area, set())})
            taken.update(e["name"] for e in ex)
            used[area] = used.get(area, set()) | {e["name"] for e in ex}
            complex_ += [{**e, "area": area, "area_label": AREA_LABEL[area], "role": "Target" if target else "Retain"} for e in ex]
        cap = spec["exercises"]
        tgt = [e for e in complex_ if e["role"] == "Target"][:max(2, cap - 2)]
        keep = sorted((e for e in complex_ if e["role"] == "Retain"),                 # trunk and injury prevention kept first
                      key=lambda e: (e["kind"] not in ("trunk_stability", "shoulder_prehab", "lower_limb_resilience", "landing"), KIND_ORDER.get(e["kind"], 9)))
        complex_ = tgt + keep[:max(0, cap - len(tgt))]
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
            micro = ("Competition microcycle" if t == "competition" else "Pre-competition" if t == "realization" else
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
                          "method": spec["method"], "dose": spec["dose"], "rest": spec["rest"], "frequency": spec["frequency"],
                          "minutes": spec["minutes"], "intensity": INTENSITY[t], "complex": complex_,
                          "microcycle": microcycle_template(t, spec["sessions"], complex_)})

    short = (e0 - s0).days + 1 < 28
    notes = [f"Built on {SOURCE}. Every number is a proposal for the coach.",
             "Volume is relative (100 = the heaviest week); the lightest week is about 60% of the heaviest (rule of 60%). Doses are repetitions and sets "
             "with bodyweight, bands, medicine balls and light loads - never a percentage of a maximal lift (U15).",
             "Each development mesocycle has at most two targets that get about 70-80% of the work; every other ability is kept with retaining loads.",
             "The exercise complex stays the same through a mesocycle (vary load, not exercises) and changes at the next block."]
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
    "Train as fresh as possible: speed, power and technique work right after the warm-up; never to exhaustion in strength sets.",
    "At least 48 h between heavy lower-body sessions; small muscle groups (calves, forearms) may be trained more often.",
    "Do not repeat the same heavy session on consecutive days - the fatigue of similar workouts adds up.",
    "Increase the load by 5-10% only when every repetition of every set is done with good technique.",
    "Fast bowlers: no jumps, sprints or heavy leg work the day after bowling; nothing hard the day before a match.",
    "Growth spurt: keep jumps and sprints at the low end and add landing, mobility and trunk work.",
    "Keep training through the season: stopping loses a short preseason's gains within weeks (training residuals).",
    "5-10 min warm-up and cool-down every session; stop and refer to the physiotherapist if there is pain.",
]


def microcycle_template(t: str, sessions: int, complex_: list[dict]) -> list[dict]:
    """The week: sessions on non-consecutive days, alternating emphasis so consecutive sessions use different muscle groups."""
    lower = [e["name"] for e in complex_ if e["kind"] in ("speed", "plyometric_power", "leg_strength", "landing", "agility", "repeat_sprint", "lower_limb_resilience")]
    upper = [e["name"] for e in complex_ if e["kind"] in ("upper_strength", "rotation_power", "trunk_stability", "shoulder_prehab", "grip_wrist")]
    other = [e["name"] for e in complex_ if e["name"] not in lower + upper]
    if t == "transition":
        slots = {"Tue": "Calisthenics, flexibility and easy aerobic play", "Fri": "Another sport or easy aerobic activity"}
    elif sessions >= 3:
        slots = {"Mon": "A - Power and lower body: " + ", ".join(lower[:4] or other[:3]),
                 "Wed": "B - Upper body, trunk and conditioning: " + ", ".join((upper[:3] + other[:2]) or lower[-2:]),
                 "Fri": "C - Whole body, target areas: " + ", ".join((lower[:2] + upper[:2]) or other[:3])}
    elif t == "competition":
        slots = {"Mon": "A - Short whole-body session (25-40 min): " + ", ".join((lower[:2] + upper[:2]) or other[:3]),
                 "Thu": "B - Upper body, trunk and activation only (no heavy legs 2 days before a match): " + ", ".join(upper[:3] or other[:3])}
    else:
        slots = {"Mon": "A - Power and lower body (reduced): " + ", ".join(lower[:3] or other[:3]),
                 "Thu": "B - Upper body and trunk (reduced): " + ", ".join(upper[:3] or other[:3])}
    return [{"day": d, "session": slots.get(d) or ("Cricket training / rest" if d not in ("Sat", "Sun") else "Match or rest")} for d in DAYS]
