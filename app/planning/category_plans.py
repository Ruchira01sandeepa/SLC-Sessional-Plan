"""Separate plans per development category (the PDP groups on the player sheet), built FROM the player's individual plan.

    Physical | Nutrition | Batting to Pace | Batting to Spin | Tactical - Batting | Pace Bowl | Spin Bowl | Tactical - Bowling | Field | Wk

The individual plan stays the main plan; this module only regroups and expands it, so the two can never disagree (same
exercises, same doses, same weekly load, same coach edits). Pure module: no database, no web.

  * Physical = the Strength & Conditioning plan, in full: the player's test profile and S&C goals, then per phase the weekly
    schedule and the focus SESSIONS laid out as warm-up / main work / injury prevention / cool-down with each exercise's personal
    dose, then week by week the focus sessions, their load and the dose step for that week.
  * Every other category: its five PDP skills with the coach rating (or "not rated yet"), drills from the supplied list for the
    phase, and the goals of that category. These are deliberately simpler for now.
Every exercise and number is a PROPOSAL for the coach.
"""
from __future__ import annotations

import zlib

from app.reference.exercise_kinds import KIND_LABEL, PHASE_KINDS
from app.reference.exercises import library
from app.planning.individual_plan import HABIT_TIPS, PDP_SKILL_KINDS, SKILL_PREFS
from app.planning.player_profile import PDP_AREA
from app.planning.session_plans import PHASE_LABEL

CATEGORIES = [
    ("physical", "Physical", "Strength & Conditioning"),
    ("nutrition", "Nutrition", "Nutrition and recovery habits"),
    ("batting_pace", "Batting to Pace", "Batting against pace"),
    ("batting_spin", "Batting to Spin", "Batting against spin"),
    ("tactical_batting", "Tactical - Batting", "Batting game sense"),
    ("pace_bowl", "Pace Bowl", "Pace bowling"),
    ("spin_bowl", "Spin Bowl", "Spin bowling"),
    ("tactical_bowling", "Tactical - Bowling", "Bowling game sense"),
    ("field", "Field", "Fielding"),
    ("wk", "Wk", "Wicketkeeping"),
]
GROUP_OF = {k: g for k, g, _ in CATEGORIES}
DRILL_GROUPS = {"Batting to Pace": ["batting"], "Batting to Spin": ["batting"], "Tactical - Batting": ["batting"], "Pace Bowl": ["fast"],
                "Spin Bowl": ["spin"], "Field": ["fielding"], "Wk": ["keeping"]}
BOWLERS = {"fast_bowler", "spin_bowler", "all_rounder"}

# S&C session parts. Main-work kinds that load the legs hard are kept off the session the day after bowling (fast bowlers).
INJURY_KINDS = {"shoulder_prehab", "lower_limb_resilience", "mobility_balance", "grip_wrist"}
HEAVY_LEGS = {"plyometric_power", "landing", "speed", "repeat_sprint", "leg_strength", "agility"}
WARM_UP = {
    "transition": ["Easy jog, skipping or a ball game (5 min)", "Mobility: leg swings, hip openers, thoracic rotations"],
    "default": ["Raise: easy jog or skipping (3 min)", "Activate: glute bridges and band walks (1 set each)",
                "Mobilise: leg swings, hip openers, thoracic rotations, ankle rocks", "Potentiate: 2-3 build-up runs to about 80%"],
}
COOL_DOWN = ["Easy walk or jog (2 min)", "Light stretches: calves, hamstrings, hip flexors, chest (20-30 s each)",
             "Slow breathing (1 min); note soreness and how hard the session felt (RPE 1-10)"]
MINUTES = {"warm": 10, "injury": 5, "cool": 5, "per_exercise": 5}
MAX_MAIN = 6                      # main exercises in one focus session; more than this rotates between session versions
NUTRITION_TIPS = {
    "Skinfolds": "Measured by the S&C coach or physiotherapist only, privately, to follow growth and body composition - never a target for a junior player.",
    "Alcohol intake": "No alcohol: it slows recovery and growth and is not legal at this age.",
}
NUTRITION_GENERAL = {
    "in_season": ["Match day: a carbohydrate-based meal 2-3 hours before play (rice, bread, noodles) and a snack at breaks.",
                  "Drink regularly in the field and between overs; more in hot weather.",
                  "After play: a meal or snack with carbohydrate and protein within an hour."],
    "pre_season": ["Regular meals around training, with a protein food at each meal to support strength work.",
                   "Water bottle at every session."],
    "pre_competition": ["Practise the match-day eating and drinking routine at training games.", "Water bottle at every session."],
    "transition": ["Keep regular meals; enjoy a varied diet while training is lighter."],
}


def relevant(group: str, role: str, bowling_types: set[str] | None) -> tuple[bool, str]:
    """Is this category part of the player's role? Every category stays viewable; the irrelevant ones are listed after."""
    bt = bowling_types or set()
    if group == "Pace Bowl":
        ok = role == "fast_bowler" or (role == "all_rounder" and ("fast" in bt or not bt))
        return ok, "Pace bowlers and pace-bowling all-rounders"
    if group == "Spin Bowl":
        ok = role == "spin_bowler" or (role == "all_rounder" and ("spin" in bt or not bt))
        return ok, "Spin bowlers and spin-bowling all-rounders"
    if group == "Tactical - Bowling":
        return role in BOWLERS, "Bowlers and all-rounders"
    if group == "Wk":
        return role == "bat_wicketkeeper", "Wicketkeepers"
    return True, "Every player"


def _drills(group: str, skill: str, phase: str, role: str, bowling_types: set[str] | None, seed: str, n: int = 2) -> tuple[list[dict], str | None]:
    groups = DRILL_GROUPS.get(group) or ([g for g in ("fast", "spin") if g in (bowling_types or set())]
                                         or (["fast"] if role == "fast_bowler" else ["spin"] if role == "spin_bowler" else ["fast", "spin"]))
    kinds = [k for k in PDP_SKILL_KINDS.get(skill, []) if k in set(PHASE_KINDS[phase])]
    if not kinds:
        return [], f"No drill for this skill in {PHASE_LABEL[phase].lower()}: it is worked on in another phase or by the coach."
    prefs = SKILL_PREFS.get((group, skill)) or SKILL_PREFS.get(skill, ())
    cands, seen = [], set()
    for g in groups:
        for d in library()["groups"][g]["skill"]:
            if d["kind"] in kinds and d["name"] not in seen:
                seen.add(d["name"])
                cands.append(d)
    cands.sort(key=lambda d: (-(any(w in d["name"].lower() for w in prefs)), kinds.index(d["kind"]), zlib.crc32((seed + skill + d["name"]).encode()) % 97))
    out = [{"name": d["name"], "purpose": d["purpose"], "kind_label": KIND_LABEL[d["kind"]]} for d in cands[:n]]
    return out, (None if out else "No drill in the supplied list fits this skill yet: the coach sets 2-3 drills.")


# ───────────── Physical: the Strength & Conditioning plan ─────────────
def _sessions(phase: dict, fast: bool, n_weeks: int = 0) -> list[dict]:
    """Spread the phase's exercises over its focus sessions. At most MAX_MAIN main exercises per session: when the phase has
    more, each session alternates between versions week by week (A1 in weeks 1, 3, ...; A2 in weeks 2, 4, ...), so every
    exercise is still trained. Each session gets a mix of areas (priorities first). For a fast bowler the session on the day
    after bowling gets upper body and trunk only when another session can take the leg work."""
    n = max(1, phase["sessions_per_week"])
    days = [(d["day"], i) for d in phase["typical_week"] for i in d["items"] if i.startswith("Focus session")][:n]
    while len(days) < n:
        days.append((None, f"Focus session {chr(65 + len(days))}"))
    rows = []
    for a in sorted(phase["areas"], key=lambda a: (not a["priority"], -(a.get("importance") or 1))):
        rows += [{**e, "area": a["area"], "area_label": a["label"], "priority": a["priority"]} for e in a["exercises"]]
    main = [r for r in rows if r["kind"] not in INJURY_KINDS]
    injury = [r for r in rows if r["kind"] in INJURY_KINDS]
    n_free = sum(1 for _, item in days if not (fast and "no jumps" in item)) or n
    heavy = sum(1 for r in main if fast and r["kind"] in HEAVY_LEGS)
    versions = max(1, -(-len(main) // (n * MAX_MAIN)), -(-heavy // (n_free * MAX_MAIN)))   # leg work only fits the free sessions
    slots = [{"base": i, "version": v, "day": day, "label": item.split(" (")[0], "restricted": fast and "no jumps" in item, "main": [], "injury": []}
             for v in range(versions) for i, (day, item) in enumerate(days)]
    free = [k for k, sl in enumerate(slots) if not sl["restricted"]] or list(range(len(slots)))
    is_heavy = lambda r: fast and r["kind"] in HEAVY_LEGS
    for r in [x for x in main if is_heavy(x)] + [x for x in main if not is_heavy(x)]:      # leg work first: it has fewer places to go
        pool = free if is_heavy(r) else list(range(len(slots)))
        target = min(pool, key=lambda j: (len(slots[j]["main"]), j))           # fill evenly, so no session goes above the cap
        slots[target]["main"].append(r)
    for sl in slots:                                                           # back in priority order inside each session
        sl["main"].sort(key=lambda r: main.index(r))
    for k, r in enumerate(injury):
        slots[k % len(slots)]["injury"].append(r)
    out = []
    warm = WARM_UP["transition" if phase["phase"] == "transition" else "default"]
    for sl in slots:
        name = sl["label"] + (str(sl["version"] + 1) if versions > 1 else "")
        if versions == 1:
            weeks = "every week of this phase"
        else:
            nums = list(range(sl["version"] + 1, (n_weeks or versions * 3) + 1, versions))
            weeks = ("week " if len(nums) == 1 else "weeks ") + ", ".join(map(str, nums)) + (" of this phase" if n_weeks else " ... of this phase")
        minutes = MINUTES["warm"] + MINUTES["cool"] + MINUTES["injury"] * bool(sl["injury"]) + MINUTES["per_exercise"] * len(sl["main"])
        note = "Day after bowling: upper body, trunk and injury prevention only - no jumps, sprints or heavy leg work." if sl["restricted"] else None
        out.append({"name": name, "day": sl["day"], "version": sl["version"] + 1, "versions": versions, "when": weeks, "minutes": minutes, "note": note,
                    "parts": [{"part": "Warm-up", "minutes": MINUTES["warm"], "items": [{"name": w} for w in warm]},
                              {"part": "Main work", "minutes": MINUTES["per_exercise"] * len(sl["main"]), "items": sl["main"]},
                              {"part": "Injury prevention", "minutes": MINUTES["injury"] if sl["injury"] else 0, "items": sl["injury"]},
                              {"part": "Cool-down", "minutes": MINUTES["cool"], "items": [{"name": c} for c in COOL_DOWN]}]})
    return out


def _dose_step(week_in_phase: int, easy: bool, status: str) -> str:
    if status == "hold":
        return "On hold: no focus sessions until cleared."
    if easy:
        return "Easy week: one set fewer on every exercise; keep the technique sharp."
    step = week_in_phase // 2
    return "Start doses (first number of each range)." if step == 0 else f"Step {step}: add one rep per set (or one set once reps reach the target) if technique is good and there is no pain."


def physical_plan(plan: dict, pdp_skills: list[str], fast: bool) -> dict:
    prof = plan["profile"]
    rated = {s["skill"]: s for s in prof.get("skills", []) if s["group"] == "Physical"}       # Recovery practices
    by_area = {a["area"]: a.get("coach_rating") for a in prof["areas"] if a.get("coach_rating") is not None}
    for skill, areas in PDP_AREA.items():                            # Speed, Endurance, Functional Strength, Agility -> test areas
        r = next((by_area[a] for a in areas if a in by_area), None)
        if r is not None and skill not in rated:
            rated[skill] = {"rating": r, "status": "priority" if r <= 2 else "strength" if r >= 4 else "solid"}
    phases = []
    for p in plan["phases"]:
        phases.append({"phase": p["phase"], "label": p["label"], "sessions_per_week": p["sessions_per_week"], "typical_week": p["typical_week"],
                       "sessions": [] if p["sessions_per_week"] == 0 else _sessions(p, fast, sum(1 for w in plan["weeks"] if w["phase"] == p["phase"])),
                       "areas": [{"area": a["area"], "label": a["label"], "percentile": a["percentile"], "priority": a["priority"], "status": a["status"],
                                  "note": a["note"], "exercises": len(a["exercises"])} for a in p["areas"]]})
    versions = {p["phase"]: (p["sessions"][0]["versions"] if p["sessions"] else 1) for p in phases}
    names = {p["phase"]: p["sessions"] for p in phases}
    weeks, seen = [], {}
    for w in plan["weeks"]:
        k = seen.get(w["phase"], 0)
        seen[w["phase"]] = k + 1
        v = k % versions.get(w["phase"], 1) + 1
        run = [s["name"] for s in names.get(w["phase"], []) if s["version"] == v] if plan["status"] != "hold" else []
        weeks.append({"sessions": run, "week": w["week"], "start": w["start"], "phase": w["phase"], "phase_label": w["phase_label"],
                      "focus_sessions": w.get("focus_sessions"), "focus_load": w.get("focus_load"), "planned_load": w.get("planned_load"),
                      "matches": w.get("matches"), "bowl_days": w.get("bowl_days"), "easy_week": w.get("easy_week"),
                      "dose_step": _dose_step(k, bool(w.get("easy_week")), plan["status"]), "flags": w.get("flags", [])})
    return {
        "test_profile": [{k: a.get(k) for k in ("area", "label", "percentile", "status", "trend", "age_label", "coach_rating", "use")} for a in prof["areas"]],
        "pdp": [{"skill": s, "rating": rated[s]["rating"] if s in rated else None, "status": rated[s]["status"] if s in rated else "not_rated"} for s in pdp_skills],
        "goals": [g for g in plan["goals"] if g["kind"] in ("test", "maintain", "rating")],
        "growth": prof["growth"]["label"], "training_age": prof["training_age"]["label"],
        "phases": phases, "weeks": weeks,
        "rules": ["Focus sessions are on top of squad training; they never replace it.",
                  "No hard leg work the day after bowling and nothing hard the day before a match.",
                  "Progress only when the reps are done with good technique and without pain; hold or step back when sore or tired.",
                  "Stop and refer to the physiotherapist if there is pain."],
    }


# ───────────── the other categories ─────────────
def skill_plan(plan: dict, group: str, pdp_skills: list[str], role: str, bowling_types: set[str] | None) -> dict:
    rated = {s["skill"]: s for s in plan["profile"].get("skills", []) if s["group"] == group}
    skills = [{"skill": s, "rating": rated[s]["rating"] if s in rated else None, "status": rated[s]["status"] if s in rated else "not_rated"}
              for s in pdp_skills]
    order = {"priority": 0, "not_rated": 1, "solid": 2, "strength": 3}
    skills.sort(key=lambda s: (order.get(s["status"], 1), s["rating"] or 0))
    phases = []
    for p in plan["phases"]:
        if group == "Nutrition":
            items = [{"skill": s["skill"], "rating": s["rating"], "status": s["status"],
                      "action": HABIT_TIPS.get(s["skill"]) or NUTRITION_TIPS.get(s["skill"]), "drills": [], "note": None} for s in skills]
            phases.append({"phase": p["phase"], "label": p["label"], "items": items, "general": NUTRITION_GENERAL.get(p["phase"], [])})
            continue
        items = []
        for s in skills:
            d, note = _drills(group, s["skill"], p["phase"], role, bowling_types, plan["player"])
            items.append({"skill": s["skill"], "rating": s["rating"], "status": s["status"], "drills": d, "note": note})
        phases.append({"phase": p["phase"], "label": p["label"], "items": items, "general": []})
    prefix = group + " - "
    goals = [g for g in plan["goals"] if g["kind"] in ("skill", "role_skill") and g["label"].startswith(prefix)]
    if group == "Nutrition":
        goals += [g for g in plan["goals"] if g["kind"] == "habit"]
    notes = []
    if not rated:
        notes.append("No coach ratings yet for this category: rate the five skills on the PDP (1-5) and the priority skills will lead this plan.")
    notes.append("A first version: ratings, drills from the supplied list and goals. A fuller plan for this category will follow.")
    return {"skills": skills, "phases": phases, "goals": goals, "notes": notes}


def build_category_plans(plan: dict, pdp: dict[str, list[str]], role: str, bowling_types: set[str] | None = None) -> dict:
    """plan: the individual plan in use. pdp: {group: [the 5 skill names]} from the PDP rubric. Returns the 10 category plans,
    the ones that belong to the player's role first."""
    cats = []
    for key, group, title in CATEGORIES:
        ok, who = relevant(group, role, bowling_types)
        skills = pdp.get(group, [])
        body = physical_plan(plan, skills, role == "fast_bowler") if key == "physical" else skill_plan(plan, group, skills, role, bowling_types)
        rated = [s for s in body["pdp" if key == "physical" else "skills"] if s["rating"] is not None]
        cats.append({"key": key, "group": group, "title": title, "relevant": ok, "for": who, "detail": "full" if key == "physical" else "basic",
                     "rated": len(rated), "priorities": sum(1 for s in rated if s["status"] == "priority"), **body})
    cats.sort(key=lambda c: (not c["relevant"], [k for k, _, _ in CATEGORIES].index(c["key"])))
    return {"player": plan["player"], "role": role, "status": plan["status"], "readiness": plan["readiness"],
            "season": plan.get("season"), "summary": plan.get("summary"), "categories": cats,
            "note": "These plans are built from the player's individual plan (the main plan) and change with it. Physical (Strength & "
                    "Conditioning) is the full plan; the other categories are a first version."}
