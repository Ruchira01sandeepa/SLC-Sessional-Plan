"""Session plan sheets: one 60-minute session per player role and season phase, laid out like the supplied
"SESSION PLAN FOR LOWER BODY" sheet. Pure module.

Content
  * The six parts and their minutes come from the supplied 60-minute template (warm-up 10, strength 15, power or speed 10,
    role-specific activity 15, injury prevention 5, cool-down 5).
  * Exercises come from the supplied exercise list and are filtered by exercise_kinds.PHASE_KINDS, so a session never contains
    work the seasonal plan does not allow in that phase (for example no strength, power or bowling in transition).
  * Doses are CONSERVATIVE RANGES for U15 players (bodyweight or light bands, no % of maximum weight, no maximal lifts).
    They are a proposal for the coaches, to be adjusted for each player.
"""
from __future__ import annotations

import re

from app.planning.annual_grid import SEASON_PHASE_OF  # noqa: F401  (kept so the phase names stay in one place)
from app.reference.exercise_kinds import KIND_LABEL, PHASE_KINDS
from app.reference.exercises import exercises_for, groups_for, library

ROLE_LABEL = {"fast_bowler": "Fast bowler", "spin_bowler": "Spin bowler", "batter": "Batter", "bat_wicketkeeper": "Batting wicketkeeper", "all_rounder": "All-rounder"}
PHASE_LABEL = {"pre_season": "Pre-season", "pre_competition": "Pre-competition", "in_season": "In-season", "transition": "Transition"}
PERIOD = {"pre_season": "Preparatory", "pre_competition": "Competition", "in_season": "Competition", "transition": "Transition"}
STAGE = {"pre_season": "General and special preparation", "pre_competition": "Pre-competition", "in_season": "Competition", "transition": "Transition"}
RPE = {"pre_season": "4 to 5", "pre_competition": "5 to 6", "in_season": "4 to 5", "transition": "2 to 3"}
EQUIPMENT = {
    "fast_bowler": "Cones, skipping rope, resistance bands, light medicine ball, stopwatch, whistle, cricket balls, stumps, net",
    "spin_bowler": "Cones, skipping rope, resistance bands, light medicine ball, stopwatch, whistle, cricket balls, stumps, net, target mat",
    "batter": "Cones, skipping rope, resistance bands, light medicine ball, stopwatch, whistle, cricket balls, bats, stumps, net",
    "bat_wicketkeeper": "Cones, skipping rope, resistance bands, light medicine ball, stopwatch, whistle, cricket balls, bats, gloves, stumps, net",
    "all_rounder": "Cones, skipping rope, resistance bands, light medicine ball, stopwatch, whistle, cricket balls, bats, stumps, net",
}
GENERAL_STRENGTH_KINDS = {"leg_strength", "upper_strength", "lower_limb_resilience"}
GENERAL_KINDS = GENERAL_STRENGTH_KINDS | {"aerobic"}      # may be borrowed from the bowling lists when a role's own list has none

# (time, reps, sets, rest). Ranges for U15: light load, controlled technique, quality before quantity.
DOSE = {
    "leg_strength": ("controlled, 2 s down 2 s up", "8-12", "2-3", "60 s between sets"),
    "upper_strength": ("controlled, 2 s down 2 s up", "8-12", "2-3", "60 s between sets"),
    "trunk_stability": ("20-30 s hold", "1", "2-3", "30 s between sets"),
    "lower_limb_resilience": ("controlled", "8-12", "2-3", "45 s between sets"),
    "shoulder_prehab": ("slow and controlled", "10-15", "2", "30 s between sets"),
    "mobility_balance": ("20-30 s each side", "1-2", "2", "15 s between sides"),
    "grip_wrist": ("controlled", "10-12", "2", "30 s between sets"),
    "landing": ("quality first", "5", "2-3", "45 s between sets"),
    "plyometric_power": ("low height, stop if landing quality drops", "3-5", "2-3", "60-90 s between sets"),
    "rotation_power": ("light ball, smooth", "5-8 each side", "2-3", "45 s between sets"),
    "speed": ("short sprint, about 90% effort", "3-6", "1", "full recovery, walk back"),
    "agility": ("10-15 s", "3-5", "2", "45-60 s between sets"),
    "repeat_sprint": ("shuttle runs, about 85% effort", "4-6", "2", "2 min between sets"),
    "aerobic": ("easy talking pace, as named", "1", "1", "walk if needed"),
}
SKILL_TIME = "4-5 min"
ORG = {"strength": "Stations in pairs", "power": "Small groups", "role": "Stations, rotate every 4-5 min", "injury": "Individual", "warm": "Group circuit", "cool": "Group"}

STRENGTH_KINDS = {"pre_season": ["leg_strength", "upper_strength", "trunk_stability", "lower_limb_resilience"],
                  "pre_competition": ["leg_strength", "upper_strength", "trunk_stability", "lower_limb_resilience"],
                  "in_season": ["leg_strength", "trunk_stability", "lower_limb_resilience"],
                  "transition": ["trunk_stability", "mobility_balance"]}
POWER_KINDS = {"pre_season": ["landing", "agility"],
               "pre_competition": ["plyometric_power", "speed", "rotation_power", "agility", "repeat_sprint"],
               "in_season": ["speed", "rotation_power", "agility"],
               "transition": ["aerobic"]}
ROLE_KINDS = {"pre_season": ["foundation", "catching", "ground_fielding", "throwing", "analysis"],
              "pre_competition": ["foundation", "variation", "tactical", "match_prep", "catching", "throwing", "fielding_game"],
              "in_season": ["variation", "tactical", "match_prep", "foundation", "fielding_game", "catching"],
              "transition": ["analysis"]}
INJURY_KINDS = {"pre_season": ["shoulder_prehab", "lower_limb_resilience", "mobility_balance", "grip_wrist"],
                "pre_competition": ["shoulder_prehab", "lower_limb_resilience", "mobility_balance", "grip_wrist"],
                "in_season": ["shoulder_prehab", "lower_limb_resilience", "mobility_balance", "grip_wrist"],
                "transition": ["shoulder_prehab", "mobility_balance"]}
PART_N = {"strength": 5, "power": 3, "role": 4, "injury": 3}


def split_minutes(total: int, n: int) -> list[int]:
    base, extra = divmod(total, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def _dose(kind: str, name: str, phase: str) -> tuple[str, str, str, str]:
    t, rep, sets, rest = DOSE[kind]
    if "nordic" in name.lower():                                   # a high-load eccentric exercise: very low volume for U15
        rep, sets, t = "3-5", "2", "slow lowering, stop if sore"
    if phase == "in_season" and kind in ("leg_strength", "upper_strength"):
        sets = "2"                                                 # maintenance
    if phase == "transition" and kind == "trunk_stability":
        sets = "2"
    return t, rep, sets, rest


def _pick(exs: list[dict], kinds: list[str], n: int, used: set[str]) -> list[dict]:
    """Round-robin over the kinds in the order given, so the part mixes types of work instead of repeating one."""
    pools = {k: [e for e in exs if e["kind"] == k and e["name"] not in used] for k in kinds}
    out = []
    while len(out) < n and any(pools.values()):
        for k in kinds:
            if pools[k] and len(out) < n:
                e = pools[k].pop(0)
                if e["name"] not in used:
                    used.add(e["name"])
                    out.append(e)
    return out


def _general_pool(phase: str) -> list[dict]:
    """General strength and aerobic exercises from the bowling lists, for roles whose own list has none (batters, keepers)."""
    kinds = set(PHASE_KINDS[phase]) & GENERAL_KINDS
    seen, out = set(), []
    for g in ("fast", "spin"):
        for e in library()["groups"][g]["physical"]:
            if e["kind"] in kinds and e["name"] not in seen:
                seen.add(e["name"])
                out.append({**e, "group": g, "category": "physical"})
    return out


def _item(e: dict, phase: str, org: str) -> dict:
    if e["kind"] not in DOSE:                                      # a skill drill: a time block, no sets and reps
        return {"desc": e["name"], "time": SKILL_TIME, "rep": "", "set": "", "org": org, "rest": "1 min change-over", "kind": e["kind"]}
    t, rep, sets, rest = _dose(e["kind"], e["name"], phase)
    return {"desc": e["name"], "time": t, "rep": rep, "set": sets, "org": org, "rest": rest, "kind": e["kind"]}


def build_session(role: str, phase: str, bowling_types: set[str] | None = None) -> dict:
    if phase not in PHASE_KINDS:
        raise ValueError(f"Unknown phase {phase}")
    tpl = {p["part"]: p for p in library()["session_template"]}
    exs = exercises_for(groups_for(role, bowling_types), phase)
    phys = [e for e in exs if e["category"] == "physical"]
    skill = [e for e in exs if e["category"] == "skill"]
    used: set[str] = set()
    notes = []

    def part(key: str, template_name: str, title: str, items: list[dict]) -> dict:
        return {"key": key, "name": title, "minutes": tpl[template_name]["minutes"], "items": items}

    warm_items = [w.strip() for w in tpl["Warm-up"]["what"].split(",")]
    wt = split_minutes(tpl["Warm-up"]["minutes"], len(warm_items))
    warm = [{"desc": w.capitalize(), "time": f"{m} min", "rep": "", "set": "", "org": ORG["warm"] if i == 0 else "", "rest": "", "kind": None} for i, (w, m) in enumerate(zip(warm_items, wt))]

    strength_pool = phys + [e for e in _general_pool(phase) if not any(x["kind"] == e["kind"] for x in phys)]
    if len(strength_pool) > len(phys) and role not in ("fast_bowler", "spin_bowler"):
        notes.append("This role's own list has no leg-strength exercises, so general strength exercises from the bowling lists are used.")
    st = [_item(e, phase, ORG["strength"]) for e in _pick(strength_pool, STRENGTH_KINDS[phase], PART_N["strength"], used)]
    power_pool = phys + [e for e in _general_pool(phase) if e["kind"] == "aerobic" and not any(x["kind"] == "aerobic" for x in phys)]
    pw = [_item(e, phase, ORG["power"]) for e in _pick(power_pool, POWER_KINDS[phase], 1 if phase == "transition" else PART_N["power"], used)]
    # roles with more than one skill list (keeper: keeping + batting; all-rounder: bowling + batting) share the role slots between them
    own = [g for g in groups_for(role, bowling_types) if g in ("spin", "fast", "batting", "keeping")]
    if len(own) > 1:
        n_role, picked = PART_N["role"], []
        for i, g in enumerate(own):
            share = n_role // len(own) + (1 if i < n_role % len(own) else 0)
            picked += _pick([e for e in skill if e["group"] == g], ROLE_KINDS[phase], share, used)
        if len(picked) < n_role:
            picked += _pick(skill, ROLE_KINDS[phase], n_role - len(picked), used)
    else:
        picked = _pick(skill, ROLE_KINDS[phase], PART_N["role"], used)
    ro = [_item(e, phase, ORG["role"]) for e in picked]
    inj = [_item(e, phase, ORG["injury"]) for e in _pick(phys, INJURY_KINDS[phase], PART_N["injury"], used)]

    cool_items = [c.strip().replace("and ", "") for c in tpl["Cool-down"]["what"].split(",")]
    ct = split_minutes(tpl["Cool-down"]["minutes"], len(cool_items))
    cool = [{"desc": c.capitalize(), "time": f"{m} min", "rep": "", "set": "", "org": ORG["cool"] if i == 0 else "", "rest": "", "kind": None} for i, (c, m) in enumerate(zip(cool_items, ct))]

    if any(e.get("added") for e in skill if e["name"] in used):
        notes.append("Batting and wicketkeeping drills are ADDED to the supplied exercise list (it has none). Coaches review them and replace any with their own.")
    if not ro:
        ro.append({"desc": "Coach to add a role-specific review (video or skill review); none is in the supplied exercise list for this role", "time": SKILL_TIME, "rep": "", "set": "", "org": ORG["role"], "rest": "", "kind": None})
    if phase == "transition":
        pw_title = "Easy aerobic (power and speed work is not used in transition)"
        ro_title = "Role-specific review (no structured bowling or high-intensity work in transition)"
        st_title = "Trunk and mobility (no strength loading in transition)"
    else:
        pw_title, ro_title, st_title = "Power or speed", "Role-specific activity", "Strength"
    parts = [part("initial", "Warm-up", "Warm-up", warm), part("main", "Strength", st_title, st), part("main", "Power or speed", pw_title, pw),
             part("main", "Role-specific activity", ro_title, ro), part("main", "Injury prevention", "Injury prevention", inj), part("final", "Cool-down", "Cool-down", cool)]
    total = sum(p["minutes"] for p in parts)
    return {
        "role": role, "phase": phase, "title": f"SESSION PLAN FOR {ROLE_LABEL[role].upper()} - {PHASE_LABEL[phase].upper()}",
        "header": [("TOPIC", f"{ROLE_LABEL[role]} training session ({PHASE_LABEL[phase]})"), ("PERIOD", PERIOD[phase]), ("STAGE", STAGE[phase]),
                   ("MESO", PHASE_LABEL[phase]), ("MICRO", "Ordinary week (no match)"), ("EQUIPMENT", EQUIPMENT[role]),
                   ("DURATION", f"{total // 60} h" if total % 60 == 0 else f"{total} min"),
                   ("TRAINING UNIT", f"Body weight or light bands. Moderate effort, RPE {RPE[phase]} of 10. Planned load = RPE x {total} min.")],
        "parts": parts, "minutes": total,
        "notes": [
            "Do all exercises at a slow to moderate pace, controlled technique, about 2 seconds down and 2 seconds up. Quality before quantity.",
            "Doses are conservative junior ranges (set for U15 and also used for U17 until SLC sets U17 doses). Adjust for each player; stop an exercise and refer to the physiotherapist if there is pain.",
            "Allow 1 to 2 minutes between parts. Fast-bowling volume in this session counts towards the weekly bowling load (see the Load distribution sheet).",
        ] + notes,
    }


# ───────────── day-by-day session plans ─────────────
DAY_TOPIC = {"heavy": "Heavy training day: strength, speed and explosive power while fresh",
             "medium": "Medium day: endurance, technique and tactics", "light": "Light day: flexibility, tactics and recovery",
             "practice": "Match practice", "active": "Active rest", "match": "Match day", "free": "Tournament training day: short heavy retaining session",
             "before": "Day before a match: activation and match preparation", "after": "Recovery day after a match",
             "between": "Recovery and activation between two matches"}
MICRO_OF = {"heavy": "Loading", "medium": "Loading", "light": "Recovery", "practice": "Loading", "active": "Transition",
            "match": "Competition", "free": "Competition", "before": "Competition (pre-match)", "after": "Competition (recovery)",
            "between": "Competition (recovery)"}
UPPER_KINDS = {"upper_strength", "trunk_stability", "shoulder_prehab", "grip_wrist"}


def _it(desc, time="", rep="", sets="", org="", rest="", kind=None):
    return {"desc": desc, "time": time, "rep": rep, "set": sets, "org": org, "rest": rest, "kind": kind}


def build_day_session(roles: list[str], phase: str, day_kind: str, *, title: str, meso: str, micro: str, pct: float | None,
                      marks: dict, load: dict, bowling_types: set | None = None) -> dict:
    """One squad session for one day, laid out like the supplied session plan: the parts depend on the kind of day, the exercises
    come from the role sessions of the phase (so nothing the phase does not allow), and every role gets its own station."""
    base = {r: build_session(r, phase, bowling_types) for r in roles}
    first = base[roles[0]]
    part_of = lambda ses, name: next((p for p in ses["parts"] if p["name"].startswith(name)), {"items": []})
    strength = part_of(first, "Strength")["items"] or part_of(first, "Trunk")["items"]
    power = part_of(first, "Power")["items"]
    injury = part_of(first, "Injury")["items"]
    warm = part_of(first, "Warm-up")["items"]
    cool = part_of(first, "Cool-down")["items"]
    stations = []
    for r in roles:
        for it in part_of(base[r], "Role-specific")["items"][:2]:
            stations.append({**it, "desc": f"[{ROLE_LABEL[r]}] {it['desc']}"})
    parts: list[dict] = []

    def add(key, name, minutes, items):
        if items:
            parts.append({"key": key, "name": name, "minutes": minutes, "items": items})

    k = day_kind
    sprint = load.get("sprint_reps")
    shuttle = load.get("shuttle_reps")
    aerobic = load.get("aerobic_min")
    overs = load.get("overs")
    if k == "match":
        add("initial", "Match warm-up and activation", 20, [_it("Easy jog and dynamic mobility", "8 min", org="Group"),
            _it("Strides at 80-90% effort", "", "3-4", "1", rest="walk back"), _it("Skill touches: catching, throwing, shadow batting / bowling run-ups", "8 min", org="Role groups")])
        add("main", "MATCH", 0, [_it("Match (fluids every drinks break; snack between innings)", "match", org="Team"),
                                 _it("Fast bowlers: match overs count towards the bowling limits", "", org="Coach records overs")])
        add("final", "Recovery", 15, [_it("Easy walk and light stretching", "10 min", org="Group"), _it("Fluids and food within 30 minutes", "5 min"),
                                      _it("Cold water or ice bath if available", "5-10 min", rest="")])
    elif k in ("after", "between"):
        add("initial", "Warm-up (easy)", 10, [_it("Easy walk or jog, mobility", "10 min", org="Group")])
        if k == "after" and marks.get("Strength"):
            upper = [_item(e, phase, ORG["strength"]) for e in _general_pool(phase) if e["kind"] == "upper_strength"][:2]
            add("main", "Upper body and trunk (short retaining strength - the legs recover)", 15,
                upper + [x for x in strength if x["kind"] in UPPER_KINDS and x["desc"] not in {u["desc"] for u in upper}][:2])
        add("main", "Mobility and injury prevention", 10, injury[:3])
        add("main", "Easy aerobic recovery", 15, [_it("Easy aerobic (bike, swim or walk-jog), talking pace", f"{aerobic or 15} min")])
        if k == "between":
            add("main", "Activation for tomorrow's match", 5, [_it("2-3 fast drills (quick feet, short strides)", "5 min", "2-3", "1", rest="full")])
        add("final", "Cool-down", 10, [_it("Stretching", "5 min"), _it("Cold water or ice bath if available", "5 min")])
    elif k == "before":
        add("initial", "Warm-up", 10, warm)
        add("main", "Speed (short, fresh, no heavy work)", 10, [_it(f"Sprint {20} m at about 90% effort", "", str(min(sprint or 3, 3)), "1", "Small groups", "full recovery, walk back")]
            + [x for x in power if x["kind"] in ("speed", "agility")][:1])
        add("main", "Match preparation (role stations)", 20, stations)
        add("main", "Mobility", 5, [x for x in injury if x["kind"] in ("mobility_balance", "shoulder_prehab")][:2])
        add("final", "Cool-down", 5, cool)
    elif k == "practice":
        add("initial", "Warm-up", 15, warm)
        add("main", "Match practice / match simulation", 60, [_it("Practice match or centre-wicket simulation with match rules", "60 min", org="Two teams")]
            + ([_it(f"Bowlers: {overs} overs in spells", "", "", "", "Coach records overs")] if overs else []))
        add("final", "Cool-down", 10, cool)
    elif k == "active":
        add("initial", "Warm-up", 5, warm[:2])
        add("main", "Easy aerobic or another sport", 25, [_it("Easy aerobic play, swimming or another sport", f"{aerobic or 20} min", org="Group")])
        add("main", "Trunk and mobility", 15, strength[:3] + injury[:2])
        add("final", "Cool-down", 5, cool)
    else:                                                        # heavy, medium, light, free
        add("initial", "Warm-up", 10, warm)
        if marks.get("Strength"):
            add("main", "Strength" + (" (short heavy retaining, 25-40 min in total)" if k == "free" else ""), 15, strength[:4 if k == "free" else 5])
        if marks.get("Speed") or marks.get("Explosive power"):
            items = power[:3]
            if sprint:
                items = [_it(f"Sprint 20 m at {int(round((load.get('effort') or 0.85) * 100))}% effort", "", str(sprint), "1", "Small groups",
                             "full recovery, walk back")] + [x for x in items if x["kind"] != "speed"][:2]
            add("main", "Speed and explosive power", 10, items)
        if marks.get("Endurance") or shuttle:
            items = []
            if aerobic:
                items.append(_it("Easy aerobic run, talking pace", f"{aerobic} min", org="Group"))
            if shuttle:
                items.append(_it("Shuttle runs 20 m", "", str(shuttle), "2", "Pairs", "2 min between sets"))
            add("main", "Endurance", 15 if aerobic else 10, items)
        if k in ("medium", "free", "heavy"):
            add("main", "Role stations (technique)" + (f" - bowlers {overs} overs" if overs else ""), 20 if k == "medium" else 15, stations)
        if k == "light":
            add("main", "Flexibility and mobility", 15, [x for x in injury if x["kind"] == "mobility_balance"][:2]
                + [_it("Stretching: hips, hamstrings, thoracic spine, shoulders", "10 min", org="Group")])
            add("main", "Tactics and analysis", 15, [_it("Video or tactical session (field placings, match plans)", "15 min", org="Squad")])
        add("main", "Injury prevention", 5, injury[:3])
        add("final", "Cool-down", 5, cool)
    total = sum(p["minutes"] for p in parts)
    rpe = {"heavy": "6 to 7", "medium": "5 to 6", "light": "3 to 4", "practice": "6 to 7", "active": "2 to 3", "match": "match",
           "free": "6", "before": "3 to 4", "after": "2 to 3", "between": "2 to 3"}[k]
    return {
        "title": f"SESSION PLAN - {title.upper()}",
        "header": [("TOPIC", f"{title}: {DAY_TOPIC[k]}"), ("PERIOD", PERIOD[phase]), ("STAGE", STAGE[phase]), ("MESO", meso),
                   ("MICRO", f"{micro} - {MICRO_OF[k]}"), ("EQUIPMENT", "; ".join(sorted({EQUIPMENT[r] for r in roles}))[:300]),
                   ("DURATION", f"{total} min" if k != "match" else "Match + 35 min"),
                   ("TRAINING UNIT", (f"{int(round(pct * 100))}% of the maximum planned load. " if pct else "") + f"RPE {rpe} of 10. "
                    "Body weight, bands, medicine balls and light loads - never a % of a maximal lift (U15).")],
        "parts": parts, "minutes": total,
        "notes": ["Rest 1 minute between exercises unless the REST column says otherwise; strength exercises slow to moderate pace, 2 s down 2 s up.",
                  "Role stations: each role does its own drills in the same time block, then the groups rotate.",
                  "A proposal for the coaches: adjust for each player; stop and refer to the physiotherapist if there is pain."],
    }


# ───────────── the supplied "Session plan" sheet, as it is (Monday lower-body session, general preparation) ─────────────
_STRETCHES = ["Supine Lower Back Stretches", "Foot Behind Knee Lower Back", "Rocking", "Seated gluteus Stretch", "Supine knee to Chest",
              "Walking knee to Chest", "Calf Walk", "Lying knee flexion", "Soleus Stretch", "Standing Leg Swing", "Walking Hamstring Walk",
              "Standing Groin Stretch", "Supine Hamstring Stretch", "Overhead squat", "Lateral Arm Chest", "Vertical Arm Raises",
              "Arm Rotation", "Neck Stretch(R/L)"]
_HYPERTROPHY = [("Back Squat", "12,10,10,8,8", 5), ("Incline Leg Press", "12,10,10,8,8", 5), ("Leg Extension", "12,10,10,8", 4),
                ("Weighted Lunges", "12,12,12", 3), ("Lying Hamstring Curl", "12,10,10,8", 4), ("Standing Hamstring Curl", "12,10,10", 3),
                ("Standing Calf Raises", "12,10,10,8", 4)]
_CORE = [("Hanging Leg Raises", "", "12", 3), ("Star plank", "", "12", 3), ("Hollow hold", "", "20s", 3), ("Land mine Rotation", "", "12", 3),
         ("Plank", "", "1min", 1), ("Right Plank", "", "1min", 1), ("Left Plank", "", "1min", 1)]


def classic_session(*, period: str = "Preparatory", stage: str = "General Preparatory", meso: str = "Introduction",
                    micro: str = "ORDINARY") -> dict:
    """The session plan sheet of the supplied workbook: header, then initial / main / final parts with time, rep, set,
    organization and rest."""
    stretch = [_it(s, "20s", "8", "1", rest="MICRO REST - 2 SEC" if i == 0 else "") for i, s in enumerate(_STRETCHES)]
    parts = [
        {"key": "initial", "name": "WARM UP", "minutes": 20, "items": [_it("Light jogging", "12min")]},
        {"key": "main", "name": "Stretch", "minutes": None, "items": [{**stretch[0], "org": "circle warm up"}] + stretch[1:]},
        {"key": "main", "name": "Rest 1 minutes for all other exercises perform exercises at a slow to moderate pace 2-4s up, 2-4 down",
         "minutes": None, "items": []},
        {"key": "main", "name": "Hypertrophy program", "minutes": None,
         "items": [_it(e, "", reps, str(s), rest="MICRO REST - 30 SEC" if i == 0 else "") for i, (e, reps, s) in enumerate(_HYPERTROPHY)]},
        {"key": "main", "name": "MACRO REST 3 MIN", "minutes": None, "items": []},
        {"key": "main", "name": "Crunches", "minutes": None, "items": [_it(e, t, r, str(s)) for e, t, r, s in _CORE]},
        {"key": "final", "name": "WARM DOWN", "minutes": 20, "items": [_it("Slow walk"), _it("Stretch"), _it("Ice bath")]},
    ]
    return {
        "title": "SESSION PLAN FOR LOWER BODY",
        "header": [("TOPIC", "Monday session plan"), ("PERIOD", period), ("STAGE", stage), ("MESO", meso), ("MICRO", micro),
                   ("EQUIPMENTS", "SKIPPING,BOX,STOP WATCH,WHISTLE,MINI CONES,RACKETS,BALLS"), ("DURATION", "1h 40min"),
                   ("TRAINING UNIT", "60-85% of the maximum weight")],
        "parts": parts, "minutes": 100, "notes": [],
    }
