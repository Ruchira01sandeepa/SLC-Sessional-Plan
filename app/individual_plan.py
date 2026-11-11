"""A seasonal plan for ONE player, built from that player's own profile (player_profile.py). Pure module.

What makes it personal
  * Strengths and priorities come from the player's own test ranks (inside their level), the trend since the last window, the
    coach's PDP ratings, the screening needs analysis (what matters most for THIS player) and their role.
  * Exercises are scored for the player, not just listed by kind: the weakest single test of an area decides the movement
    (weak inverted row -> pulling, weak push-ups -> pushing, weak 5-10-5 -> change of direction), growth stage and training age
    change what is safe and sensible, and each phase rotates exercises so the plan progresses through the season.
  * Overall development: EVERY area stays in the plan. Priority areas share about 60% of the exercise slots, weighted by how far
    below the middle they are and how much they matter for the player; strengths keep a maintenance slot and say how they help
    in the player's role.
  * Goals are measurable: test targets come from the player's own test group (the result that would lift them about 15 rank
    points), PDP items rated 1-2 aim one point higher at the next review, habits get simple daily actions.
  * Cricket skills: low-rated PDP items get drills from the supplied list (bowling, fielding, tactics) where the phase allows them.
  * Load: plan_load.plan_weeks() starts from the player's own logged load (or an age-group estimate), with a 10% weekly rise
    cap, easy weeks and a load ratio cap of 1.3. The player's own bowling limits apply; a growth spurt lowers the season's peak,
    and fast bowlers in or just after the spurt bowl one over fewer per bowling day.
  * Doses are personal (dosing.py) and are kept low for high-impact work during the growth spurt and smaller for new players.
Every exercise and number is a PROPOSAL for the coach.
"""
from __future__ import annotations

import zlib
from datetime import date, timedelta

from .age_groups import profile as age_profile
from .annual_grid import SEASON_PHASE_OF
from .dosing import personal_dose
from .exercise_kinds import KIND_LABEL, PHASE_KINDS
from .exercises import groups_for, library
from .load_distribution import build_loads
from .player_profile import build_profile, physical_goal
from .role_skills import STATUS_CLASS, STATUS_LABEL, match_drills
from .plan_load import LOAD_FACTOR, plan_weeks, verify
from .session_plans import PHASE_LABEL
from .test_battery import AREA_LABEL, WINDOW_LABEL, WINDOWS

AREA_KINDS = {
    "endurance": ["aerobic", "repeat_sprint"],
    "power": ["plyometric_power", "leg_strength", "landing"],
    "upper_strength": ["upper_strength", "shoulder_prehab", "grip_wrist"],
    "speed": ["speed", "plyometric_power"],
    "agility": ["agility", "landing"],
    "core": ["trunk_stability", "rotation_power"],
}
SESSIONS = {"pre_season": 2, "pre_competition": 2, "in_season": 1, "transition": 1}
PHASE_ORDER = ["pre_season", "pre_competition", "in_season", "transition"]
BOWLER_ROLES = {"fast_bowler", "spin_bowler", "all_rounder"}
TOTAL_SLOTS = 12                  # exercise slots per phase, shared between the areas
PRIORITY_SHARE = 0.60             # share of the slots for areas below the middle (when there are also areas at or above it)
MIDDLE = 50.0
ALTERNATIVES = 6                  # next-best exercises kept per area so a coach can swap one in
GROWTH_PEAK_FACTOR = 1.25        # planned peak week as a share of the starting load during the growth spurt (normally 1.40)

# Words in an exercise name that match a specific weak test: the plan prefers these movements.
TEST_PREFS = {
    "pushups": ("push-up", "chest pass"),
    "inverted_row": ("band row", "pull-up", "pull-apart"),
    "broad_jump": ("broad jump", "countermovement", "split squat", "bulgarian", "glute bridge"),
    "sprint_20m": ("acceleration", "20 m sprint", "bounding", "power skips", "reaction sprint"),
    "shuttle_5_10_5": ("pro-agility", "lateral shuffle", "three-cone", "controlled landing", "t-drill"),
    "plank": ("plank", "side plank", "pallof"),
    "run_2km": ("aerobic", "shuttle"),
    "bronco": ("shuttle", "aerobic"),
}
HIGH_IMPACT = {"plyometric_power", "repeat_sprint"}
GROWTH_FRIENDLY = {"landing", "mobility_balance", "trunk_stability", "lower_limb_resilience", "shoulder_prehab"}
ADVANCED = ("bulgarian", "nordic", "single-leg hop", "bounding", "box jump", "copenhagen", "pull-up")

# Cricket-skill PDP items -> skill kinds in the supplied list, and the library groups that hold the drills
PDP_SKILL_KINDS = {
    "Repeatable action": ["foundation"], "Ball Speed": ["foundation"], "Control": ["foundation"], "Variations": ["variation"],
    "New Ball Old Ball": ["tactical", "variation"], "Sideway Spin": ["variation", "foundation"],
    "Format knowledge": ["tactical", "analysis"], "Game awareness": ["match_prep", "tactical"], "Decision making": ["match_prep", "tactical"],
    "Tactical adaptability": ["tactical", "match_prep"], "Field Placements": ["tactical"],
    "Throwing": ["throwing"], "Outfield catching": ["catching"], "Close catching": ["catching"], "Run saving ability": ["ground_fielding", "fielding_game"],
    "Anticipation": ["fielding_game", "match_prep"],
    # batting (added drills)
    "Balance / Batswing Wristwork": ["foundation"], "Weight transfer front foot": ["foundation"], "Weight transfer back foot": ["foundation", "variation"],
    "Rotate strike": ["match_prep"], "Boundary hitting": ["variation"], "Run Judgement / Calling": ["match_prep"],
    # wicketkeeping (added drills)
    "Clean takes": ["foundation", "variation"], "Up to stumps": ["foundation"], "Back from stumps": ["foundation"],
    "Agility Left / Right": ["catching", "variation"], "Fielding leader": ["tactical", "match_prep"],
}
# Words in a drill name that fit a skill best. Keyed by (PDP group, skill) first, then by skill.
SKILL_PREFS = {"Control": ("target", "single-stump", "cone"), "Repeatable action": ("shadow", "grip and release", "run-up", "stock-ball"),
               "Ball Speed": ("run-up",), "Outfield catching": ("high", "outfield"), "Close catching": ("slip", "close", "reaction"),
               ("Batting to Pace", "Balance / Batswing Wristwork"): ("balance", "shadow"), ("Batting to Spin", "Balance / Batswing Wristwork"): ("soft-hands", "balance"),
               ("Batting to Pace", "Weight transfer front foot"): ("front-foot", "side-arm"), ("Batting to Spin", "Weight transfer front foot"): ("use-of-feet",),
               ("Batting to Pace", "Weight transfer back foot"): ("back-foot", "pull", "cut"), ("Batting to Spin", "Weight transfer back foot"): ("soft-hands", "back-foot"),
               ("Batting to Pace", "Boundary hitting"): ("range", "pull"), ("Batting to Spin", "Boundary hitting"): ("sweep", "range"),
               "Rotate strike": ("rotate",), "Run Judgement / Calling": ("running", "calling"),
               ("Tactical - Batting", "Format knowledge"): ("game-plan", "video"), ("Tactical - Batting", "Game awareness"): ("scenario", "rotate"),
               ("Tactical - Batting", "Decision making"): ("scenario",), ("Tactical - Batting", "Tactical adaptability"): ("game-plan",),
               "Clean takes": ("clean-takes", "reaction"), "Up to stumps": ("standing-up",), "Back from stumps": ("standing-back",),
               "Agility Left / Right": ("lateral", "leg-side"), "Fielding leader": ("communication", "run-out")}
PDP_LIBRARY_GROUPS = {"Pace Bowl": ["fast"], "Spin Bowl": ["spin"], "Field": ["fielding"], "Batting to Pace": ["batting"], "Batting to Spin": ["batting"],
                      "Tactical - Batting": ["batting"], "Wk": ["keeping"]}
COACH_LED: set[str] = set()                     # every PDP group now has drills (batting and keeping drills were added)
HABIT_TIPS = {
    "Hydration": "Bring a water bottle to every session; drink before, during and after; pale urine is a simple check.",
    "Diet habits": "Three meals and planned snacks on training days, with a protein food and vegetables at each main meal; eat breakfast before morning sessions.",
    "Recovery nutrition": "Within an hour after training or a match: a meal or snack with carbohydrate and protein (for example rice and curry, milk, a sandwich).",
    "Recovery practices": "Aim for 8-10 hours of sleep, cool down and stretch lightly after sessions, and keep one full rest day a week.",
}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def allocate(areas: list[dict]) -> dict[str, int]:
    """areas: [{area, percentile, weight?, importance?}] (percentile None = not tested). Slots per area: priority areas 60%, the rest
    40%, every area at least 1. Within the priority areas a bigger weight (gap below the middle x importance) gets more; without a
    weight the gap alone is used. Largest-remainder rounding."""
    weak = [a for a in areas if a["percentile"] is not None and a["percentile"] < MIDDLE]
    rest = [a for a in areas if a not in weak]
    if not areas:
        return {}
    if not weak or not rest:
        share = {a["area"]: 1 / len(areas) for a in areas}
    else:
        wts = {a["area"]: (a.get("weight") or (MIDDLE - a["percentile"] + 10)) for a in weak}
        tot = sum(wts.values())
        share = {k: PRIORITY_SHARE * v / tot for k, v in wts.items()}
        rw = {a["area"]: a.get("importance") or 1.0 for a in rest}
        rtot = sum(rw.values())
        share.update({k: (1 - PRIORITY_SHARE) * v / rtot for k, v in rw.items()})
    raw = {k: v * TOTAL_SLOTS for k, v in share.items()}
    slots = {k: max(1, int(v)) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: raw[k] - int(raw[k]), reverse=True)
    i = 0
    while sum(slots.values()) < TOTAL_SLOTS and order:
        slots[order[i % len(order)]] += 1
        i += 1
    while sum(slots.values()) > TOTAL_SLOTS:                     # minimum-one rule can overshoot with many areas
        k = max((k for k in slots if slots[k] > 1), key=lambda k: slots[k] - raw[k])
        slots[k] -= 1
    return slots


def _physical(groups: list[str]) -> list[dict]:
    out, seen = [], set()
    for g in groups:
        for e in library()["groups"][g]["physical"]:
            if e["name"] not in seen:
                seen.add(e["name"])
                out.append({**e, "group": g})
    return out


def _skill_drills(groups: list[str]) -> list[dict]:
    out, seen = [], set()
    for g in groups:
        for e in library()["groups"][g]["skill"]:
            if e["name"] not in seen:
                seen.add(e["name"])
                out.append({**e, "group": g})
    return out


def _score(e: dict, kind: str, kind_rank: int, own: bool, ctx: dict) -> tuple[float, list[str]]:
    name = e["name"].lower()
    s, why = 100.0 - 12 * kind_rank, []
    hit = next((t for t, words in ctx.get("prefs", {}).items() if any(w in name for w in words)), None)
    if hit:
        s += 30 if hit == ctx.get("weakest") else 12
        label = ctx["test_labels"].get(hit, hit)
        if ctx.get("area_status") == "strength":
            why.append(f"keeps your {label} strong")
        else:
            why.append(f"targets {label}" + (" (your weakest test here)" if hit == ctx.get("weakest") else ""))
    if own:
        s += 8
    stage = ctx.get("stage")
    if ctx.get("in_spurt"):
        if kind in HIGH_IMPACT:
            s -= 40
            why.append("low volume during the growth spurt")
        if any(w in name for w in ("bounding", "single-leg hop", "box jump")):
            s -= 10
        if kind in GROWTH_FRIENDLY:
            s += 15
            why.append("suits the growth spurt")
    elif stage == "pre" and kind in ("speed", "agility"):
        s += 10
        why.append("speed and agility suit this stage of growth")
    elif stage == "post" and kind in ("leg_strength", "upper_strength") and ctx.get("priority"):
        s += 6
    if ctx.get("new_player") and any(w in name for w in ADVANCED):
        s -= 20
    if e["name"] in ctx.get("used_before", set()):
        s -= 12                                                   # rotate exercises between phases where an alternative fits
    s += (zlib.crc32((ctx.get("seed", "") + e["name"]).encode()) % 100) / 100     # stable tie-break, different per player
    return s, why


def _pick(area: str, phase: str, role_groups: list[str], n: int, *, priority: bool = False, percentile: float | None = None,
          status: str = "ready", ctx: dict | None = None) -> list[dict]:
    """Up to n exercises for the area that the phase allows, best fit for this player first."""
    ctx = {**(ctx or {}), "priority": priority}
    allowed = set(PHASE_KINDS[phase])
    kinds = [k for k in AREA_KINDS[area] if k in allowed]
    if not kinds or n <= 0:
        return []
    own = {e["name"] for e in _physical(role_groups)}
    pool = [e for e in _physical(role_groups) + _physical(["spin", "fast", "fielding"]) if e["kind"] in kinds]
    if ctx.get("new_player"):                                     # new players: advanced variations only if nothing simpler fits
        simple = [e for e in pool if not any(w in e["name"].lower() for w in ADVANCED)]
        pool = simple or pool
    seen, cands = set(), []
    for e in pool:
        if e["name"] in seen:
            continue
        seen.add(e["name"])
        sc, why = _score(e, e["kind"], kinds.index(e["kind"]), e["name"] in own, ctx)
        cands.append((sc, e, why))
    picked: list[dict] = []
    kind_count: dict[str, int] = {}
    while cands and len(picked) < n:
        cands.sort(key=lambda c: c[0] - 15 * kind_count.get(c[1]["kind"], 0), reverse=True)   # mix types of work
        sc, e, why = cands.pop(0)
        kind = e["kind"]
        kind_count[kind] = kind_count.get(kind, 0) + 1
        low = "Growth spurt: jumps and sprints stay at the low end of the range." if ctx.get("in_spurt") and kind in HIGH_IMPACT else None
        dose = personal_dose(kind, e["name"], phase, priority=priority, percentile=percentile, status=status,
                             t_scale=0.5 if ctx.get("new_player") else 1.0, low_reason=low)
        picked.append({"name": e["name"], "purpose": e["purpose"], "kind": kind, "kind_label": KIND_LABEL[kind],
                       "source": "role list" if e["name"] in own else "general list", "why": "; ".join(why) or None, **dose})
    return picked


def _skill_work(skills: list[dict], phase: str, role_groups: list[str], seed: str) -> list[dict]:
    """Drills for the cricket skills rated 1-2 (priority), from the supplied list, where the phase allows them."""
    out = []
    allowed = set(PHASE_KINDS[phase])
    bowl_groups = [g for g in role_groups if g in ("fast", "spin")]
    for s in [x for x in skills if x["status"] == "priority" and x["domain"] == "cricket"][:5]:
        if s["group"] in COACH_LED:
            out.append({"skill": s["skill"], "group": s["group"], "rating": s["rating"], "drills": [],
                        "note": "Coach-led: the supplied exercise list has no batting or keeping drills. Set 2-3 drills for this skill."})
            continue
        groups = PDP_LIBRARY_GROUPS.get(s["group"], bowl_groups or ["fielding"])
        kinds = [k for k in PDP_SKILL_KINDS.get(s["skill"], []) if k in allowed]
        prefs = SKILL_PREFS.get((s["group"], s["skill"])) or SKILL_PREFS.get(s["skill"], ())
        cands = [d for d in _skill_drills(groups) if d["kind"] in kinds]
        cands.sort(key=lambda d: (-(any(w in d["name"].lower() for w in prefs)), kinds.index(d["kind"]),
                                  zlib.crc32((seed + d["name"]).encode()) % 97))
        drills = [{"name": d["name"], "purpose": d["purpose"], "kind_label": KIND_LABEL[d["kind"]], "added": bool(d.get("added"))} for d in cands[:2]]
        note = None if drills else f"No drill for this skill is planned in {PHASE_LABEL[phase].lower()}; it is worked on in another phase."
        if s["skill"] == "Ball Speed":
            note = (note + " " if note else "") + "Leg power and trunk work in the physical programme also support ball speed."
        out.append({"skill": s["skill"], "group": s["group"], "rating": s["rating"], "drills": drills, "note": note})
    return out


def _typical_week(phase: str, sessions: int, bowl_days: int, fast: bool) -> list[dict]:
    """A template week: where the focus sessions go around squad training, bowling and matches.
    Rules: a non-bowling day after every bowling day; no lower-body power the day after bowling; nothing hard the day before a match."""
    week = {d: [] for d in DAYS}
    match = phase in ("in_season", "pre_competition")
    if match:
        week["Sat"].append("Match")
        week["Sun"].append("Rest and recovery")
        week["Fri"].append("Light skills, no hard work before the match")
    else:
        week["Sun"].append("Rest")
    if phase == "transition":
        week["Wed"].append("Other sport or active play")
        week["Sat"].append("Easy aerobic or another sport")
    squad = ["Tue", "Thu"] + ([] if match else ["Sat"])
    for d in squad:
        if phase != "transition":
            week[d].append("Squad training")
    bowling = [d for d in ("Tue", "Thu", "Sat") if not (match and d == "Sat")][:max(0, bowl_days)] if phase != "transition" else []
    for d in bowling:
        week[d].append("Bowling")
    after_bowl = {DAYS[(DAYS.index(d) + 1) % 7] for d in bowling}
    candidates = ["Mon", "Wed", "Fri"] if not match else ["Mon", "Wed", "Thu"]
    placed = 0
    for d in candidates:
        if placed >= sessions:
            break
        if "Bowling" in week[d] or "Match" in week[d] or (match and d == "Fri"):
            continue
        label = f"Focus session {chr(65 + placed)}"
        if fast and d in after_bowl:
            label += " (upper body and trunk; no jumps after a bowling day)"
        week[d].append(label)
        placed += 1
    return [{"day": d, "items": week[d] or ["Rest or light activity"]} for d in DAYS]


def build_individual_plan(*, player: dict, cat: dict | None, ready: dict, g: dict, bowling_types: set[str] | None = None,
                          workload: dict | None = None, extra: dict | None = None, today: date | None = None) -> dict:
    """player: {name, role, age?, date_of_birth?, maturity_status?, custom_limits?}; cat: categorisation result for the player (or
    None); ready: categorisation.readiness(); g: annual_grid.build_grid() for the player's squad season; workload:
    workload_rules.summarise() output (or None). extra (all optional): {prev_cat, pdp, needs, heights, screening, cohort_values,
    window}."""
    extra = extra or {}
    status = ready["status"]
    factor = LOAD_FACTOR[status]
    prof = build_profile(player=player, cat=cat, prev_cat=extra.get("prev_cat"), pdp=extra.get("pdp"), needs=extra.get("needs"),
                         heights=extra.get("heights"), screening=extra.get("screening"))
    gr, ta = prof["growth"], prof["training_age"]
    areas = [{"area": a["area"], "label": a["label"], "percentile": a["percentile"], "weight": a["weight"] or None,
              "importance": a["importance"], "status": a["status"], "trend": a["trend"], "note": a["note"], "use": a.get("use"),
              "weakest_test": a["weakest_test"], "tests": a["tests"], "source": a["source"]} for a in prof["areas"]]
    focus = list(cat["focus_areas"]) if cat and cat.get("overall") is not None else []
    priority = {a["area"] for a in areas if a["status"] == "priority"} | {f["area"] for f in focus}
    ordered = areas                                                                  # priorities first (by weight), then the rest
    slots = allocate(ordered)
    role_groups = groups_for(player["role"], bowling_types)
    present = {SEASON_PHASE_OF[k] for k in g["kinds"]}
    phases = [p for p in PHASE_ORDER if p in present]
    test_labels = {t["key"]: t["label"].lower() for a in areas for t in a["tests"]}
    seed = player["name"]

    notes = ["Every exercise and number is a PROPOSAL for the coach. Adjust for the player; stop and refer to the physiotherapist if there is pain.",
             "Areas below the middle of the player's own level are priority areas and get about 60% of the exercises; every other area is still trained "
             "(about 40%), so the player develops across all areas. The ranking compares the player with squad peers only; it is not a pass or fail mark."]
    if not areas:
        notes.append("There is no band yet, so there are no focus areas. Import test results for this window first (at least 5 players of the same level are needed).")
    elif not priority:
        notes.append("No area is below the middle, so all areas share the work equally. Re-test next window.")
    if status == "hold":
        notes.append("Readiness is Hold: no new load is planned until a coach or physiotherapist clears the player.")
    elif status == "caution":
        notes.append("Readiness is Caution: weekly load is 80% of the player's usual build and focus sessions are shorter.")
    notes.extend(gr["notes"])
    if prof["missing"]:
        notes.append("The plan would be more personal with: " + "; ".join(prof["missing"]) + ".")

    role_skills = [r for r in (extra.get("role_skills") or []) if r.get("status") in STATUS_CLASS]
    role_focus = ([r for r in role_skills if STATUS_CLASS[r["status"]] == "priority"]
                  + [r for r in role_skills if STATUS_CLASS[r["status"]] == "developing"])[:6]
    out_phases, used_before = [], {}
    for ph in phases:
        rows = []
        for a in ordered:
            n = slots.get(a["area"], 1)
            ctx = {"prefs": {t["key"]: TEST_PREFS.get(t["key"], ()) for t in a["tests"]}, "weakest": a["weakest_test"], "test_labels": test_labels,
                   "stage": gr["stage"], "in_spurt": gr["in_spurt"], "new_player": ta["band"] == "new", "seed": seed,
                   "used_before": used_before.get(a["area"], set()), "area_status": a["status"]}
            ranked = [] if status == "hold" else _pick(a["area"], ph, role_groups, n + ALTERNATIVES, priority=a["area"] in priority,
                                                        percentile=a["percentile"], status=status, ctx=ctx)
            ex, alternatives = ranked[:n], ranked[n:]              # the next-best fits: what a coach can swap in
            used_before[a["area"]] = {e["name"] for e in ex} or used_before.get(a["area"], set())
            note = None
            if status == "hold":
                note = "On hold."
            elif not ex:
                later = next((p for p in PHASE_ORDER[PHASE_ORDER.index(ph) + 1:] if p in present and _pick(a["area"], p, role_groups, 1)), None)
                earlier = next((p for p in PHASE_ORDER[:PHASE_ORDER.index(ph)] if p in present and _pick(a["area"], p, role_groups, 1)), None)
                where = later or earlier
                note = (f"No exercise for this area is allowed in {PHASE_LABEL[ph].lower()}. It is trained in {PHASE_LABEL[where].lower()}."
                        if where else f"No exercise for this area is allowed in {PHASE_LABEL[ph].lower()}.")
            elif a["percentile"] is None:
                note = "Not tested yet: general work until a result is available."
            elif a["status"] == "strength":
                note = f"Strength: maintenance work" + (f". It helps with {a['use']}." if a.get("use") else ".")
            elif a["note"]:
                note = a["note"]
            rows.append({"area": a["area"], "label": a["label"], "percentile": a["percentile"], "priority": a["area"] in priority,
                         "status": a["status"], "trend": a["trend"], "importance": a["importance"], "slots": n, "exercises": ex, "note": note,
                         "alternatives": alternatives})
        base_sessions = SESSIONS[ph] + (1 if ph == "pre_season" and len(priority) >= 3 and ta["band"] != "new" else 0)
        sessions = 0 if status == "hold" or not areas else (max(1, base_sessions - 1) if status == "caution" else base_sessions)
        skills = [] if status == "hold" else _skill_work(prof["skills"], ph, role_groups, seed)
        rs_work = [] if status == "hold" else [
            {**r, "status_label": STATUS_LABEL[r["status"]], "drills": match_drills(r["group"], r["skill"], player["role"], bowling_types, ph)}
            for r in role_focus]
        out_phases.append({"phase": ph, "label": PHASE_LABEL[ph], "sessions_per_week": sessions, "areas": rows, "skills": skills,
                           "role_skills": rs_work})

    # ───── load ─────
    nominal = {p["phase"]: p["sessions_per_week"] for p in out_phases}
    squad_load = build_loads(g)                                          # bowling days and overs per day, already within the fast-bowler limits
    bowler = player["role"] in BOWLER_ROLES
    agep = age_profile(g.get("age_group"))
    from .workload_rules import effective_limits
    limits = effective_limits(player["role"], player.get("custom_limits"), g.get("age_group")) or dict(agep.fast_limits)
    limits = {**agep.fast_limits, **{k: v for k, v in limits.items() if v}}
    trim = gr["bowling_window"]
    grid_weeks = []
    for w in range(g["weeks"]):
        opd = squad_load["overs_per_day"][w]
        if opd and trim:
            opd = max(2, opd - 1)
        days = min(squad_load["bowl_days"][w], max(0, limits["max_bowling_days_week"] - g["match_counts"][w]))
        grid_weeks.append({"week": w + 1, "phase": SEASON_PHASE_OF[g["kinds"][w]], "percentage": g["percentage"][w],
                           "matches": g["match_counts"][w], "test": bool(g["test_weeks"][w]), "bowl_days": days, "overs_per_day": opd})
    load = plan_weeks(weeks=grid_weeks, status=status, workload=workload, sessions_by_phase=nominal, bowler=bowler, limits=limits,
                      start_load=agep.start_load, peak_factor=GROWTH_PEAK_FACTOR if gr["in_spurt"] else None)
    weeks = []
    for w, calc in zip(range(g["weeks"]), load["weeks"]):
        ph = SEASON_PHASE_OF[g["kinds"][w]]
        flags = list(calc["flags"])
        if trim and calc["bowl_days"]:
            flags.append("Growth window: one over fewer per bowling day")
        weeks.append({"week": w + 1, "start": g["week_starts"][w], "phase": ph, "phase_label": PHASE_LABEL[ph],
                      "squad_percentage": g["percentage"][w], **{k: v for k, v in calc.items() if k not in ("week", "flags")}, "flags": flags})
    notes.append("Weekly load is in units of session RPE x minutes, the same as the workload log. Start: " + load["summary"]["source"].rstrip(".") + ". "
                 "The week's load includes matches and bowling: " + load["summary"]["assumptions"])
    if player.get("custom_limits"):
        notes.append("This player's own bowling limits (set by the coach) are used instead of the age-group defaults.")
    if player["role"] in ("spin_bowler", "all_rounder") and not player.get("custom_limits"):
        notes.append("Spin bowlers and all-rounders have no automatic bowling limit: the coach sets the overs for this player. The overs shown are the squad proposal.")

    # typical week per phase
    for p in out_phases:
        bd = [w["bowl_days"] for w in weeks if w["phase"] == p["phase"]]
        typical_bowl = max(set(bd), key=bd.count) if bd else 0
        p["typical_week"] = _typical_week(p["phase"], p["sessions_per_week"], typical_bowl if bowler else 0, player["role"] == "fast_bowler")

    # ───── goals ─────
    cur_window = extra.get("window")
    nxt = WINDOWS[WINDOWS.index(cur_window) + 1] if cur_window in WINDOWS and WINDOWS.index(cur_window) + 1 < len(WINDOWS) else None
    by = WINDOW_LABEL[nxt] + " test" if nxt else "next season's baseline test"
    goals = []
    for a in [x for x in prof["areas"] if x["status"] == "priority"][:3]:
        if a["weakest_test"]:
            gl = physical_goal(a, a["weakest_test"], (extra.get("cohort_values") or {}).get(a["weakest_test"]), by)
            if gl:
                goals.append(gl)
        elif a.get("coach_rating"):
            goals.append({"kind": "rating", "area": a["area"], "label": f"{a['label']}: coach rating {a['coach_rating']} to {a['coach_rating'] + 1}",
                          "by": "next PDP review", "why": "Rated as an area to improve and not tested yet."})
    strong = [a["label"] for a in prof["areas"] if a["status"] == "strength"]
    if strong:
        goals.append({"kind": "maintain", "label": "Keep " + ", ".join(strong) + " at rank 70 or better", "by": by,
                      "why": "Strengths are maintained so they stay strengths while the priorities improve."})
    for s in [x for x in prof["skills"] if x["status"] == "priority" and x["domain"] == "cricket"][:4]:
        goals.append({"kind": "skill", "label": f"{s['group']} - {s['skill']}: rating {s['rating']} to {s['rating'] + 1}", "by": "next PDP review (about 4-6 weeks)",
                      "why": "Rated as an area to improve by the coach."})
    for r in [x for x in role_skills if STATUS_CLASS[x["status"]] == "priority"][:4]:
        goals.append({"kind": "role_skill", "label": f"{r['group']} - {r['skill']}: Have to improve to Improving", "by": "next skill review (about 4 weeks)",
                      "why": "Marked Have to improve on the role skill grid."})
    habits = [{"item": s["skill"], "rating": s["rating"], "action": HABIT_TIPS.get(s["skill"])} for s in prof["skills"]
              if s["domain"] == "habits" and s["status"] == "priority" and HABIT_TIPS.get(s["skill"])]
    for h in habits:
        goals.append({"kind": "habit", "label": f"{h['item']}: {h['action']}", "by": "every day", "why": f"Rated {h['rating']} of 5."})

    # ───── reviews ─────
    reviews = []
    for a, b, num in g.get("macros", []):
        end = g["week_starts"][b] + timedelta(days=6)
        reviews.append({"date": end, "what": f"End of block {num}: check technique, soreness and whether reps reached the target; progress, hold or step back."})
    for w, on in enumerate(g["test_weeks"]):
        if on:
            reviews.append({"date": g["week_starts"][w], "what": "Test week: re-test, update the band and refresh this plan."})
    reviews.sort(key=lambda r: r["date"])
    today = today or date.today()
    upcoming = [r for r in reviews if r["date"] >= today]
    reviews = upcoming or reviews[-1:]                               # only what is still ahead (the last one if the season is over)

    strengths = [{"label": a["label"], "detail": f"rank {a['percentile']:g}" + (f"; helps with {a['use']}" if a.get("use") else "")} for a in prof["areas"] if a["status"] == "strength"] + \
                [{"label": f"{s['group']} - {s['skill']}", "detail": f"coach rating {s['rating']}/5"} for s in prof["skills"] if s["status"] == "strength"]
    prios = [{"label": a["label"], "detail": (f"rank {a['percentile']:g}" if a["percentile"] is not None else "coach rating")
              + (f", weakest test {test_labels.get(a['weakest_test'], '')}" if a["weakest_test"] else "")
              + (", matters a lot for this player" if a["importance"] >= 1.15 else "") + (", declining" if a["trend"] == "declining" else "")}
             for a in prof["areas"] if a["status"] == "priority"] + \
            [{"label": f"{s['group']} - {s['skill']}", "detail": f"coach rating {s['rating']}/5"} for s in prof["skills"] if s["status"] == "priority"]
    prios += [{"label": f"{r['group']} - {r['skill']}", "detail": "role skill: Have to improve"} for r in role_skills if STATUS_CLASS[r["status"]] == "priority"][:6]
    strengths += [{"label": f"{r['group']} - {r['skill']}", "detail": f"role skill: {STATUS_LABEL[r['status']]}"}
                  for r in role_skills if STATUS_CLASS[r["status"]] == "strength"][:4]

    return {"player": player["name"], "role": player["role"], "status": status, "readiness": ready, "load_factor": factor,
            "focus_areas": focus, "areas": [{"area": a["area"], "label": a["label"], "percentile": a["percentile"]} for a in areas],
            "profile": {"age": prof["age"], "growth": gr, "training_age": ta, "importance_source": prof["importance_source"],
                        "objective": prof["objective"], "inputs": prof["inputs"], "missing": prof["missing"],
                        "areas": [{k: a[k] for k in ("area", "label", "percentile", "status", "trend", "importance", "note", "source")}
                                  | {"use": a.get("use"), "previous_percentile": a.get("previous_percentile"), "coach_rating": a.get("coach_rating")}
                                  for a in prof["areas"]],
                        "skills": prof["skills"], "role_skills": role_skills},
            "strengths": strengths, "priorities": prios, "goals": goals, "habits": habits, "reviews": reviews,
            "phases": out_phases, "weeks": weeks, "load_summary": load["summary"], "limits": limits,
            "load_violations": verify(load, fast=player["role"] == "fast_bowler", limits=limits), "notes": notes}
