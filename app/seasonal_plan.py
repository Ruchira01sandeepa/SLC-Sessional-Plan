"""Seasonal plan generator.

Builds a squad's seasonal plan from: the season and its phases, the calendar, the staff assigned to the squad, the roles
of the players, the skill lists in the workbooks, the Scenario sheet, the role-specific measures and the supplied
exercise list. It is a pure function (no database access): the router loads the inputs and passes them in.

Everything here is a PROPOSAL for the coaches to review. Phase texts, the exercise-to-phase mapping and the role
emphasis are deliberately conservative, contain no adult or international pass/fail standards, and set no numeric
targets: targets are "improve on the player's own baseline" or a coach-set benchmark.
"""
import math
import re
from datetime import date, timedelta

from .exercise_kinds import KIND_LABEL
from .exercises import by_kind, exercises_for, groups_for, library
from .role_kpis import kpis_for
from .models import PlayerRole
from .age_groups import profile as age_profile

PHASE_ORDER = ["pre_season", "pre_competition", "in_season", "transition"]
AREAS = ["technical", "tactical", "physical", "mental", "nutrition", "recovery"]
ROLE_LABEL = {"fast_bowler": "Fast bowlers", "spin_bowler": "Spin bowlers", "batter": "Batters",
              "bat_wicketkeeper": "Batting wicketkeepers", "all_rounder": "All-rounders"}
ROLE_ORDER = list(ROLE_LABEL)
EXEC_GROUP = "Role-Specific Skill Execution"

PHASE_INFO = {
    "pre_season": {
        "label": "Pre-season",
        "purpose": "Build the physical base and the technical foundations. Screening and baseline testing. Low volume, low intensity, controlled technique.",
        "workload": "Start low and progress gradually. Technique, landing mechanics and recovery come before intensity. Bowling and throwing volumes stay low and progressive.",
        "intensity": "Low to moderate"},
    "pre_competition": {
        "label": "Pre-competition",
        "purpose": "Raise specificity and intensity step by step. Introduce variations, match scenarios and match-simulation. Mid-block review.",
        "workload": "Progress volume or intensity only when technique, recovery and pain checks are acceptable. Add match-simulation gradually and keep the rest day after every bowling day.",
        "intensity": "Moderate to high"},
    "in_season": {
        "label": "In-season",
        "purpose": "Compete, maintain and recover. Match preparation and recovery routines. Gym work moves to low-volume maintenance. Mid-season testing and review.",
        "workload": "Apply the workload rules every week. Match days count as workload. Keep strength, power and speed at low volume and protect recovery.",
        "intensity": "Match-driven, with planned low days"},
    "transition": {
        "label": "Transition / off-season",
        "purpose": "Active rest and recovery. End-of-season testing and review. Reset goals for the next season.",
        "workload": "Keep activity easy and varied. Little or no structured bowling; confirm with the coach and physiotherapist. Structured bowling returns at the start of the next pre-season.",
        "intensity": "Low"},
}

# (goal, planned activities, measurement method, target outcome) for ALL players, by phase and development area.
COMMON = {
    "pre_season": {
        "technical": ("Assess every player's technique and build repeatable foundations at low intensity.",
                      "Skill-analysis session for each player (video where possible). Micro-plan Monday to Friday for the priority corrections. Slow, controlled repetition. Record the Development grid symbols at baseline.",
                      "Development grid symbols (? / Naturally Good / Have to improve / Improving / Good / Complete). PDP individual rating 1-5.",
                      "Baseline recorded for every core skill. Two or three priority skills chosen for each player."),
        "tactical": ("Teach game awareness, format knowledge and decision-making basics.",
                     "Discussion and video of match situations. Scenario-sheet situations walked through at slow pace. Field-placement awareness for bowlers and fielders.",
                     "PDP tactical ratings (format knowledge, game awareness, decision making). Scenario-sheet completion.",
                     "Each player can explain their role and plan in the scenarios practised."),
        "physical": ("Build the general physical base: trunk, single-leg strength, shoulder and hip stability, easy aerobic base and landing mechanics.",
                     "Two or three strength and stability sessions a week from the role programme. Easy aerobic work, mobility and landing drills. Baseline fitness testing in the first two weeks.",
                     "Fitness tests: height and weight, countermovement jump, squat jump, 5/10/20 m sprint, Yo-Yo IR1, planks, calf raises.",
                     "Baseline recorded for every player. Individual targets set for each player and provisional squad benchmarks set by the coach."),
        "mental": ("Introduce goal-setting and simple routines.",
                   "Goal-setting using the screening trials. A short routine before each delivery or ball. A short weekly check-in with the coach.",
                   "Coach rating 1-5 for focus and routine. Goals recorded on the PDP.",
                   "Every player has written goals that are specific, measurable and achievable, with a timeframe."),
        "nutrition": ("Establish hydration, meal and recovery-nutrition habits.",
                      "Education session for players and parents. Hydration plan for training. Review of diet habits. Skinfolds only where the coach and parents agree.",
                      "PDP nutrition ratings (skinfolds, hydration, diet habits, recovery nutrition).",
                      "A hydration and recovery-nutrition routine in place. Diet habits reviewed for every player."),
        "recovery": ("Teach recovery habits and set up monitoring.",
                     "Sleep and recovery education. A routine for reporting soreness, fatigue and sleep. At least one non-bowling recovery day after every bowling day for fast bowlers. Any pain reported is reviewed with the coach and medical staff.",
                     "Player-reported soreness, fatigue, sleep and effort (RPE). Availability status from medical staff.",
                     "Every player uses the reporting routine. Every pain flag is reviewed with the coach or medical staff."),
    },
    "pre_competition": {
        "technical": ("Add variations and apply skills under light pressure.",
                      "Variation and consistency work. Move technique drills from slow to match speed. Fortnightly video review. Update micro-plans from the analysis.",
                      "Development grid symbols. Role-specific measures (see the role rows). PDP ratings.",
                      "Priority skills move at least one step along the legend. No technique regression when intensity rises."),
        "tactical": ("Apply plans in scenarios and small matches.",
                     "Scenario practices from the Scenario sheet. Adaptability sessions (random practice, match-simulation). Field-setting and batter-plan work.",
                     "Adaptability challenge results. Scenario-sheet completion. PDP tactical ratings.",
                     "Players carry out the planned tactics in simulations."),
        "physical": ("Add power, speed and agility on top of the base.",
                     "Medicine-ball throws, jumps, sprints and agility at low volume. Keep the strength work. High-intensity conditioning only on days with low bowling load.",
                     "Monitored sessions. An optional mid-block fitness test.",
                     "Progress against each player's own baseline and targets. No sudden load spikes."),
        "mental": ("Practise performing under pressure.",
                   "Pressure-over and pressure-fielding drills. Routines used under fatigue. Debrief after match-simulations.",
                   "Coach rating 1-5 for composure under pressure. The mental flag on the Scenario sheet.",
                   "Players use their routine in pressure drills."),
        "nutrition": ("Support the higher training load with fuelling and hydration.",
                      "Match-day eating and hydration plan. Recovery meal and fluids after sessions. Review with players and parents.",
                      "PDP nutrition ratings. Hydration check.",
                      "Players follow their match-day routine."),
        "recovery": ("Protect recovery as the load rises.",
                     "Plan rest days in the weekly plan. Review the weekly wellness and effort reports. No increase in load while a pain or poor-recovery flag is open.",
                     "Weekly review of RPE, soreness, fatigue and sleep. Medical review of any pain flag.",
                     "No unplanned load increases. Every flag acted on within the week."),
    },
    "in_season": {
        "technical": ("Keep technique reliable under match demands.",
                      "Short technique-maintenance blocks. Correct faults exposed in matches with the Skill Analysis micro-plan. Video review of matches.",
                      "Development grid symbols. Role-specific measures from match performance.",
                      "Skills rated Good stay Good. Priority faults corrected."),
        "tactical": ("Prepare for and review every match.",
                     "A plan for each opponent. A short review after each match. Scenario practice drawn from recent matches.",
                     "Match review notes. PDP tactical ratings.",
                     "A plan and a review recorded for each match."),
        "physical": ("Maintain strength, power and speed at low volume while managing match load.",
                     "One or two short maintenance sessions a week. Sprint and power work early in the week. No heavy session the day before a match. Mid-season fitness test.",
                     "Mid-season fitness test compared with baseline.",
                     "Results maintained or improved against baseline. No sudden decline."),
        "mental": ("Handle match pressure and setbacks.",
                   "Set a simple goal for each match. Reflect after each match. Use the routine in matches.",
                   "Coach rating 1-5. Match-goal review.",
                   "Each player sets and reviews a goal for every match."),
        "nutrition": ("Match-day and travel nutrition and hydration.",
                      "Pre-match meal and fluids. Fluids and food during long matches. Recovery meal after the match.",
                      "Coach and parent check against the match-day plan.",
                      "Players follow the match-day plan."),
        "recovery": ("Apply the weekly workload rules and the recovery routines.",
                     "A recovery day after bowling days. A post-match recovery routine (cool-down, food, fluids, sleep). Weekly review of RPE, soreness and sleep. Medical review of pain.",
                     "Weekly workload review against the workload rules. Availability status.",
                     "Workload rules followed. Every pain flag reviewed."),
    },
    "transition": {
        "technical": ("Review the season and set technical goals for next season.",
                      "A season review with each player. Video highlights. No new technique changes during the break.",
                      "Development grid symbols at the end of the season.",
                      "End-of-season symbols recorded. Priorities for next season agreed."),
        "tactical": ("Review what was learned tactically.",
                     "Review the scenarios and match notes. Discuss each player's role for next season.",
                     "Season review notes. PDP tactical ratings.",
                     "Tactical strengths and gaps recorded for each player."),
        "physical": ("Active rest, then end-of-season testing.",
                     "Easy aerobic activity, mobility, other sports and play. End-of-season fitness testing.",
                     "End-of-season fitness tests compared with baseline and mid-season.",
                     "End-of-season results recorded. Change from baseline reported for each player."),
        "mental": ("Rest and reset.",
                   "Enjoyment-focused activities. A season goal review with the player and parents.",
                   "Player and parent feedback. Goals reviewed on the PDP.",
                   "Season goals reviewed. A fresh start for the next season."),
        "nutrition": ("Healthy eating and hydration habits during the break.",
                      "Review diet habits. Keep a regular meal pattern and good hydration. Support healthy growth.",
                      "PDP nutrition ratings.",
                      "Habits reviewed and carried into the next pre-season."),
        "recovery": ("Full physical and mental recovery from the season.",
                     "Planned rest. Any niggles assessed by the physiotherapist before next season. A regular sleep routine.",
                     "Availability status from medical staff.",
                     "Every player starts the next pre-season fit, or with a clear return plan."),
    },
}

# Role emphasis for the physical row (a proposal; the supplied list has no batting or keeping drills).
PHYSICAL_EMPHASIS = {
    "fast_bowler": "Single-leg strength, hamstring and calf resilience, trunk and shoulder care, landing mechanics. Bowling load follows the workload rules.",
    "spin_bowler": "Trunk rotation and anti-rotation, hip stability and balance, finger and wrist strength, shoulder care.",
    "batter": "Leg strength and rotational power for hitting, speed between the wickets, shoulder and trunk care.",
    "bat_wicketkeeper": "Leg strength and endurance for the keeping stance, quick feet and agility, shoulder and trunk care.",
    "all_rounder": "The combined load of batting, bowling and fielding. Balance the workload across the three and protect recovery.",
}
ADDED_DRILLS_NOTE = ("The supplied exercise list has no batting or wicketkeeping drills, so standard junior batting and keeping drills were ADDED "
                     "(marked as added). Coaches review them and replace any with their own.")
NO_DRILLS_NOTE = ("The supplied exercise list has no batting or wicketkeeping drills, so the fielding and general athletic lists are used. "
                  "Coach to add role drills.")

def fast_bowler_rules(age_group: str | None = None) -> list[dict]:
    """The fast-bowling limits of the squad's age group (app/age_groups.py), written out for the plan."""
    p = age_profile(age_group)
    lim = p.fast_limits
    return [
        {"applies_to": "Fast bowlers", "rule": "At least one non-bowling recovery day after every bowling day."},
        {"applies_to": "Fast bowlers", "rule": f"At most {lim['max_bowling_days_week']} bowling days a week, counting matches and training."},
        {"applies_to": "Fast bowlers", "rule": f"At most {lim['max_spell_overs']} overs in a spell."},
        {"applies_to": "Fast bowlers", "rule": f"At most {lim['max_match_day_overs']} overs on a match day ({p.code}), subject to SLC / provincial approval."
                                               + (" These U17 numbers are placeholders until SLC confirms them." if p.code != "U15" else "")},
    ]


WORKLOAD_RULES_COMMON = [
    {"applies_to": "Spin bowlers", "rule": "Track balls, overs, spells, spell length and rest days. The fast-bowling limits are NOT applied automatically; the coach sets limits for each player."},
    {"applies_to": "Batters", "rule": "Track balls faced, session length and intensity, and rest days."},
    {"applies_to": "Batting wicketkeepers", "rule": "Track keeping minutes, throws, balls faced and intensity, and rest days."},
    {"applies_to": "All-rounders", "rule": "Track batting, bowling and fielding together. Do not apply the fast-bowling limits automatically."},
    {"applies_to": "All players", "rule": "Increase load gradually and individually. Progress only when the planned work is done with acceptable technique, recovery and no pain flags."},
    {"applies_to": "All players", "rule": "Compare this week with last week and with the four-week average, and this month with last month."},
    {"applies_to": "All players", "rule": "Strength-training load does not progress until technique is acceptable."},
    {"applies_to": "All players", "rule": "No high-intensity conditioning after a high bowling-load day."},
    {"applies_to": "All players", "rule": "Reported pain or poor recovery: reduce load and review with the coach and medical staff."},
]


def workload_rules_for(age_group: str | None = None) -> list[dict]:
    return fast_bowler_rules(age_group) + WORKLOAD_RULES_COMMON


WORKLOAD_RULES = workload_rules_for("U15")
WORKLOAD_NOTE = ("These are guidance rules taken from the project brief. The Workload tab checks logged sessions against them and raises "
                 "alerts for the coach and physiotherapist. The fast-bowling limits are provisional until SLC / provincial approval.")

_TACTICAL = re.compile(r"tactic|plan\b|plans\b|field-setting|crease|matchup|game|awareness|role|clarity|support", re.I)
_PHYSICAL = re.compile(r"workload|recovery|capacity|under fatigue|shoulder and trunk", re.I)


def _split_skills(dev: list[tuple[str, str]]):
    """Development-sheet skills -> (technical, tactical, physical) lists of (group, skill)."""
    tech, tact, phys = [], [], []
    for g, s in dev:
        if g == EXEC_GROUP:
            continue
        if _PHYSICAL.search(s):
            phys.append((g, s))
        elif _TACTICAL.search(g) or _TACTICAL.search(s):
            tact.append((g, s))
        else:
            tech.append((g, s))
    return tech, tact, phys


def _skill_text(skills: list[tuple[str, str]]) -> str:
    if not skills:
        return "none listed"
    groups: dict[str, list[str]] = {}
    for g, s in skills:
        groups.setdefault(g, []).append(s)
    if len(skills) > 14:                          # long lists (the batter sheet): groups only
        return "; ".join(f"{g} ({len(v)})" for g, v in groups.items()) + " - see the Development sheet for each skill"
    return "; ".join(f"{g}: {', '.join(v)}" if g != "Ungrouped" else ", ".join(v) for g, v in groups.items())


def _phase_slice(items: list, phase: str, *, tactical: bool = False) -> list:
    """Which part of a skill list a phase works on: the first half in pre-season (foundations), the second half in
    pre-competition (extend and apply; tactical skills are all used), everything in-season (maintain), nothing in transition."""
    if not items:
        return []
    half = max(1, math.ceil(len(items) / 2))
    if phase == "pre_season":
        return items[:half]
    if phase == "pre_competition":
        return items if tactical else (items[half:] or items)
    if phase == "in_season":
        return items
    return []


def _kind_text(by: dict[str, list[str]], per_kind: int = 4) -> str:
    return "; ".join(f"{k}: {', '.join(v[:per_kind])}" for k, v in by.items()) or "none"


def _names(staff: dict, *roles: str) -> str:
    seen, out = set(), []
    for r in roles:
        for n in staff.get(r, []):
            if n not in seen:
                seen.add(n)
                out.append(n)
    return ", ".join(out) or "To be assigned"


def _weeks(s: date, e: date) -> int:
    return math.ceil(((e - s).days + 1) / 7)


def _in(d: date, s: date, e: date) -> bool:
    return s <= d <= e


def build_plan(*, squad_name: str, season: dict, phases: list[dict], phases_source: str, events: list[dict],
               staff: dict, roles: list[str], bowling_types: set[str] | None, skills: dict, scenarios: dict,
               generated_on: date, age_group: str | None = None) -> dict:
    """season: {name, start_date, end_date}. phases: [{phase_type, start_date, end_date, focus}].
    events: [{event_type, title, date}]. staff: {'coach': [names], 'sc_coach': [...], 'physio': [...]}.
    skills: {role: [(group, skill), ...] in sheet order}. scenarios: {role: [(title, skill), ...]}."""
    phases = sorted(phases, key=lambda p: p["start_date"])
    roles = [r for r in ROLE_ORDER if r in roles]
    resp = {"technical": _names(staff, "coach"), "tactical": _names(staff, "coach"), "mental": _names(staff, "coach"),
            "physical": _names(staff, "sc_coach", "coach"), "nutrition": _names(staff, "sc_coach", "coach"),
            "recovery": _names(staff, "physio", "sc_coach")}

    # ---- phases and key dates ----
    ph_out = []
    for p in phases:
        t, s, e = p["phase_type"], p["start_date"], p["end_date"]
        evs = [x for x in events if _in(x["date"], s, e)]
        ph_out.append({**PHASE_INFO[t], "phase_type": t, "start_date": s, "end_date": e, "weeks": _weeks(s, e),
                       "focus": p.get("focus") or PHASE_INFO[t]["purpose"],
                       "matches": sum(x["event_type"] == "match" for x in evs),
                       "fitness_tests": [{"date": x["date"], "title": x["title"]} for x in evs if x["event_type"] == "fitness_test"],
                       "rest_days": sum(x["event_type"] == "rest" for x in evs),
                       "training_sessions": sum(x["event_type"] == "training" for x in evs)})

    s0, e0 = season["start_date"], season["end_date"]
    mid_ph = next((p for p in phases if p["phase_type"] == "in_season"), None)
    mid = (mid_ph["start_date"] + (mid_ph["end_date"] - mid_ph["start_date"]) / 2) if mid_ph else s0 + (e0 - s0) / 2
    tests = [x for x in events if x["event_type"] == "fitness_test"]
    testing = [
        {"test": "Baseline", "from": s0, "to": min(e0, s0 + timedelta(days=13)), "source": "suggested: first two weeks of the season"},
        {"test": "Mid-season", "from": mid - timedelta(days=3), "to": mid + timedelta(days=3), "source": "suggested: middle of the in-season phase"},
        {"test": "End-season", "from": max(s0, e0 - timedelta(days=13)), "to": e0, "source": "suggested: last two weeks of the season"},
    ]
    for t in testing:
        scheduled = [x for x in tests if _in(x["date"], t["from"], t["to"])]
        if scheduled:
            t["scheduled"] = [{"date": x["date"], "title": x["title"]} for x in scheduled]
            t["source"] = "fitness-test events already in the calendar"

    # ---- plan rows ----
    rows = []

    def add(phase, area, applies_to, goal, activities, measure, target, responsible):
        p = next(x for x in phases if x["phase_type"] == phase)
        rows.append({"key": f"{phase}|{area}|{applies_to or 'all'}", "phase": phase, "phase_label": PHASE_INFO[phase]["label"],
                     "applies_to": applies_to, "applies_to_label": ROLE_LABEL.get(applies_to, "All players"),
                     "development_area": area, "goal": goal, "start_date": p["start_date"], "end_date": p["end_date"],
                     "planned_activities": activities, "responsible": responsible, "measurement_method": measure,
                     "target_outcome": target, "status": "not_started", "coach_review": None, "plan_item_id": None})

    programmes = []
    for p in phases:
        ph = p["phase_type"]
        for area in AREAS:
            goal, act, meas, tgt = COMMON[ph][area]
            add(ph, area, None, goal, act, meas, tgt, resp[area])
        for role in roles:
            dev = skills.get(role, [])
            tech, tact, phys_items = _split_skills(dev)
            kpi_txt = ", ".join(f"{m.label} ({m.unit})" for m in kpis_for(PlayerRole(role)))
            groups = groups_for(role, bowling_types)
            exs = exercises_for(groups, ph)
            skill_by = by_kind(exs, "skill")
            phys_by = by_kind(exs, "physical")
            has_role_drills = any(g in ("spin", "fast", "batting", "keeping") for g in groups)
            label = ROLE_LABEL[role]
            for e in exs:
                programmes.append({"role": role, "role_label": label, "phase": ph, "phase_label": PHASE_INFO[ph]["label"],
                                   "category": e["category"], "name": e["name"], "purpose": e["purpose"], "areas": e["areas"],
                                   "kind": KIND_LABEL[e["kind"]], "source_list": e["group"]})

            # technical
            t_now = _phase_slice(tech, ph)
            tech_kinds = {k: v for k, v in skill_by.items() if k in ("Action and accuracy foundations", "Variations", "Catching", "Ground fielding", "Throwing", "Video review")}
            if ph == "transition":
                goal, act = f"{label}: review the season and agree technical priorities for next season.", "Season review of each player's Development grid. No new technique changes during the break."
            else:
                focus = {"pre_season": "Foundations", "pre_competition": "Extend and apply", "in_season": "Maintain and correct"}[ph]
                goal = f"{label}: {focus.lower()} - {_skill_text(t_now) if t_now else 'coach to list the skills for this role'}."
                act = "Practice activities: " + (_kind_text(tech_kinds, 5) if tech_kinds else "none in the supplied list") + "."
                if not has_role_drills:
                    act += " " + NO_DRILLS_NOTE
            add(ph, "technical", role, goal, act,
                f"Development grid symbols for the listed skills. Role-specific measures: {kpi_txt}.",
                "Each listed skill moves at least one step along the legend (for example Have to improve to Improving). Measures improve on the player's own baseline.",
                resp["technical"])

            # tactical
            sc = scenarios.get(role, [])
            sc_txt = "; ".join(f"{t}" + (f" ({s})" if s else "") for t, s in sc[:2])
            tact_now = _phase_slice(tact, ph, tactical=True)
            tact_kinds = {k: v for k, v in skill_by.items() if k in ("Tactical", "Pressure and match-simulation")}
            if ph == "transition":
                goal, act = f"{label}: review tactical learning and the role for next season.", "Review the scenarios and match notes with each player."
            else:
                goal = f"{label}: {_skill_text(tact_now) if tact_now else 'game awareness and role clarity'}."
                act = (f"Scenario from the Scenario sheet: {sc_txt}. " if sc_txt else "") + ("Practice activities: " + _kind_text(tact_kinds, 5) + "." if tact_kinds else "")
            add(ph, "tactical", role, goal, act.strip(),
                "Scenario-sheet completion. Adaptability challenge results. PDP tactical ratings.",
                "Players carry out the planned tactics in scenarios and in matches.", resp["tactical"])

            # physical
            extra = f" Skill-sheet physical items: {', '.join(s for _, s in phys_items)}." if phys_items and ph != "transition" else ""
            add(ph, "physical", role,
                f"{label}: {PHYSICAL_EMPHASIS[role]}",
                f"Exercises: {_kind_text(phys_by, 3)}. The full list with purpose and areas improved is in the Role Programmes sheet.{extra}"
                + ("" if ph == "transition" else " Keep bowling volumes low and progressive; controlled technique, landing mechanics and recovery come before intensity."),
                "Fitness tests relevant to the role (countermovement jump, squat jump, sprints, Yo-Yo IR1, planks, calf raises) compared with the player's baseline.",
                "Improve on own baseline and individual targets, or meet the coach's provisional benchmark. No adult standards are applied.",
                resp["physical"])

    lib = library()
    return {
        "squad": squad_name, "season": {"name": season["name"], "start_date": s0, "end_date": e0},
        "generated_on": generated_on, "phases_source": phases_source, "roles": roles,
        "roles_label": [ROLE_LABEL[r] for r in roles],
        "staff": {k: staff.get(k, []) for k in ("coach", "sc_coach", "physio")},
        "phases": ph_out, "testing": testing, "events": sorted(events, key=lambda x: (x["date"], x["title"])), "rows": rows, "programmes": programmes,
        "workload_rules": workload_rules_for(age_group), "workload_note": WORKLOAD_NOTE, "age_group": age_profile(age_group).code,
        "session_template": lib["session_template"], "session_guidance": lib["guidance"],
        "notes": [
            "This plan is a proposal generated from the season, the calendar, the workbook skill lists and the supplied exercise list. Coaches review and adjust it.",
            "No adult or international standards are used. Fitness targets are each player's own baseline, individual targets or coach benchmarks (provisional).",
            ("Phase dates are a SUGGESTED split of the season. Set the real dates in Admin, Seasons." if phases_source == "suggested"
             else "Phase dates are the ones set for this season."),
            "Which exercises belong to which phase is a proposal for the coaches to confirm.",
        ] + ([ADDED_DRILLS_NOTE] if any(r in ("batter", "bat_wicketkeeper", "all_rounder") for r in roles) else []),
    }
