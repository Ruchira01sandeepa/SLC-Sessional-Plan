"""Load distribution sheet: what the weekly percentage means in sessions. Pure module (no database, no Excel).

The supplied rugby sheet lists interval-run volumes per week (100 m, 120 m x 8, ... total metres). The cricket version
lists, for each week of the season:
  * sprint effort and short repeat-sprint conditioning sized for juniors (20 m runs only, taken from the supplied exercise list),
  * easy aerobic running,
  * bowling: training days, overs per bowling day, spells and weekly overs, CAPPED by the workload limits.

Every number is a PROPOSAL for the coaches. Nothing here is prescribed for an individual player, and no heavy or
long-distance running is used. Which kind of work is allowed in which phase follows exercise_kinds.PHASE_KINDS:
speed in pre-competition and in-season, repeat sprints in pre-competition only, easy aerobic in pre-season and
transition, no structured bowling in transition.
"""
from __future__ import annotations

from .annual_grid import COMP, GENERAL, PRECOMP, SPECIAL, TRANS
from .age_groups import profile as age_profile
from .workload_rules import DEFAULT_FAST_LIMITS

SPRINT_M = 20                                   # one sprint or shuttle run is 20 m (the supplied list has 10-20 m sprints)
SPRINT_EFFORT = {PRECOMP: (0.80, 0.90), COMP: (0.90, 0.90)}        # share of maximal effort; never 100%
REPS_MIN, REPS_MAX = 3, 6
SHUTTLE_SETS = 2
AEROBIC_MIN, AEROBIC_MAX = 10, 30
BOWL_DAYS = {GENERAL: 2, SPECIAL: 2, PRECOMP: 3, COMP: 3, TRANS: 0}   # training bowling days before matches are counted
BOWL_OVERS_CAP = {GENERAL: 4, SPECIAL: 6, PRECOMP: 8, COMP: 8, TRANS: 0}   # overs per bowling day, well under the daily limit
BOWL_OVERS_MIN = 2
MAX_BOWL_DAYS = DEFAULT_FAST_LIMITS["max_bowling_days_week"]       # matches count towards this
SPELL_MAX = DEFAULT_FAST_LIMITS["max_spell_overs"]


def _round(x: float) -> int:
    return int(x + 0.5)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def split_spells(overs: int, spell_max: int = SPELL_MAX) -> list[int]:
    """6 overs -> [3, 3]; 8 -> [4, 4]; 5 -> [5]. Spells are as even as possible and never above the spell limit."""
    if overs <= 0:
        return []
    k = -(-overs // spell_max)
    base, extra = divmod(overs, k)
    return [base + 1] * extra + [base] * (k - extra)


def build_loads(g: dict) -> dict:
    """g is annual_grid.build_grid(). Returns rows of per-week values (None = nothing planned that week)."""
    n, kinds, pct, mc = g["weeks"], g["kinds"], g["percentage"], g["match_counts"]
    lim = age_profile(g.get("age_group")).fast_limits                  # fast-bowler limits of the squad's age group
    max_days, spell_max = lim["max_bowling_days_week"], lim["max_spell_overs"]
    effort = [None] * n
    for ph, (lo, hi) in SPRINT_EFFORT.items():
        ws = [w for w in range(n) if kinds[w] == ph]
        for i, w in enumerate(ws):
            effort[w] = round(lo + (hi - lo) * (i / (len(ws) - 1) if len(ws) > 1 else 0), 2)

    reps = [_clamp(_round(pct[w] * 8), REPS_MIN, REPS_MAX) for w in range(n)]
    sprint = [reps[w] if kinds[w] in (PRECOMP, COMP) else None for w in range(n)]
    shuttle = [reps[w] if kinds[w] == PRECOMP else None for w in range(n)]
    aerobic = [_clamp(AEROBIC_MIN + _round(pct[w] * 20), AEROBIC_MIN, AEROBIC_MAX) if kinds[w] in (GENERAL, SPECIAL, TRANS) else None for w in range(n)]
    metres = [(sprint[w] + (shuttle[w] or 0) * SHUTTLE_SETS) * SPRINT_M if sprint[w] else None for w in range(n)]

    days, overs_day, spells, overs_week = [], [], [], []
    for w in range(n):
        k = kinds[w]
        d = min(BOWL_DAYS[k], max(0, max_days - mc[w]))                 # a match is a bowling day: 3 a week in total
        o = _clamp(_round(pct[w] * 10), BOWL_OVERS_MIN, BOWL_OVERS_CAP[k]) if d and BOWL_OVERS_CAP[k] else 0
        days.append(d if BOWL_DAYS[k] else 0)
        overs_day.append(o or None)
        spells.append("+".join(map(str, split_spells(o, spell_max))) if o else None)
        overs_week.append(d * o if d and o else None)
    return {
        "percentage": pct, "effort": effort, "sprint_reps": sprint, "shuttle_reps": shuttle, "aerobic_min": aerobic, "metres": metres,
        "matches": mc, "bowl_days": days, "overs_per_day": overs_day, "spells": spells, "overs_per_week": overs_week,
        "notes": [
            "Every number on this sheet is a PROPOSAL for the coaches. Adjust for each player; stop and refer to the physiotherapist if there is pain.",
            f"Runs are {SPRINT_M} m only. Sprint reps are 3 to 6 with full recovery (walk back and wait). Effort never reaches 100%: it builds from 80% to 90%.",
            "Shuttle runs are used in pre-competition only; easy aerobic running is used in pre-season and transition only (talking pace, no racing).",
            f"Bowling: training bowling days are {BOWL_DAYS[GENERAL]} in preparation and up to {BOWL_DAYS[PRECOMP]} in competition, minus one for every match, "
            f"because a match counts as a bowling day and the limit is {max_days} bowling days in 7.",
            f"Overs per bowling day follow the weekly percentage and stay at or below {BOWL_OVERS_CAP[GENERAL]} (general), {BOWL_OVERS_CAP[SPECIAL]} (special), "
            f"{BOWL_OVERS_CAP[PRECOMP]} (pre-competition and competition). Spells never exceed {spell_max} overs. Match overs are extra and are limited separately "
            f"({lim['max_match_day_overs']} a match day, with a caution at {lim['caution_match_day_overs']}).",
            "Plan bowling days with at least one non-bowling day after each. No structured bowling in transition.",
            "Fast-bowler limits are applied automatically by the workload module (provisional until SLC / provincial approval). Spin bowlers and "
            "all-rounders have no automatic limit; the coach sets one for each player. The same planned overs are shown for every bowler.",
        ],
    }
