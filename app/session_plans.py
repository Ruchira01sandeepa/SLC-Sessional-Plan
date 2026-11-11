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

from .annual_grid import SEASON_PHASE_OF  # noqa: F401  (kept so the phase names stay in one place)
from .exercise_kinds import KIND_LABEL, PHASE_KINDS
from .exercises import exercises_for, groups_for, library

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
