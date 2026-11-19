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


def build_daily_loads(g: dict) -> dict:
    """The weekly loads placed on the days they happen (g is build_grid(); its "daily" grid decides the days):
    sprints on speed days, shuttles on anaerobic-endurance days, easy aerobic on endurance days, training bowling on the best days
    of the week (never the day before a match, never two bowling days in a row), matches on match days."""
    d = g["daily"]
    wl = build_loads(g)
    n, wk, dk = d["weeks"], d["week_of_day"], d["day_kind_keys"]
    mark = {(sec["name"], r["label"]): r["marks"] for sec in d["sections"] for r in sec["rows"]}
    off = [False] * n                                            # a category plan may leave a section out
    speed, endu, anaer = (mark.get(("Physical", "Speed"), off), mark.get(("Physical", "Endurance"), off),
                          mark.get(("Technical", "Anaerobic endurance"), off))
    effort = [wl["effort"][wk[i]] if speed[i] and wl["sprint_reps"][wk[i]] else None for i in range(n)]
    sprint = [wl["sprint_reps"][wk[i]] if speed[i] else None for i in range(n)]
    shuttle = [wl["shuttle_reps"][wk[i]] if anaer[i] else None for i in range(n)]
    aerobic = [wl["aerobic_min"][wk[i]] if endu[i] else None for i in range(n)]
    metres = [((sprint[i] or 0) + (shuttle[i] or 0) * SHUTTLE_SETS) * SPRINT_M or None for i in range(n)]
    match = [1 if k == "match" else None for k in dk]
    bowl = [None] * n
    pref = {"medium": 0, "free": 0, "practice": 1, "heavy": 2, "after": 3, "light": 4}
    for w in sorted(set(wk)):
        idx = [i for i in range(n) if wk[i] == w]
        want = wl["bowl_days"][w] or 0
        taken = {i for i in idx if match[i]}
        for i in sorted((i for i in idx if dk[i] in pref), key=lambda i: (pref[dk[i]], i)):
            if want <= 0:
                break
            if any(j in taken for j in (i - 1, i + 1)) or (i + 1 < n and match[i + 1]):
                continue                                         # a non-bowling day after each bowling day; fresh for a match
            bowl[i] = wl["overs_per_day"][w]
            taken.add(i)
            want -= 1
    spells = ["+".join(map(str, split_spells(o))) if o else None for o in bowl]
    week_overs = [None] * n
    for w in sorted(set(wk)):
        idx = [i for i in range(n) if wk[i] == w]
        tot = sum(bowl[i] or 0 for i in idx)
        if tot:
            week_overs[idx[-1]] = tot
    return {"percentage": d["percentage"], "effort": effort, "sprint_reps": sprint, "shuttle_reps": shuttle, "aerobic_min": aerobic,
            "metres": metres, "matches": match, "overs": bowl, "spells": spells, "week_overs": week_overs,
            "notes": ["DAY BY DAY: each column is one day. The weekly volumes are placed on the days the Annual plan marks for them "
                      "(sprints on speed days, shuttle runs on anaerobic-endurance days, easy aerobic running on endurance days)."] + wl["notes"]
                     + ["Training bowling days are placed on medium or training days, never the day before a match and never two days in a row. "
                        "'Overs this week' is shown on the last day of each week."]}


# ───────────── the supplied sheet's running block (100 m speed + 120 / 150 / 300 m interval runs, week by week) ─────────────
INTERVAL_RUNS = (120, 150, 300)
SPEED_100M = {SPECIAL: (0.85, 0.90), PRECOMP: (0.95, 0.95), COMP: (1.00, 1.00)}   # % of max speed; the block opens at 80%
# reps at the season's highest load, per phase (120 m, 150 m, 300 m); 0 = not used in that phase
INTERVAL_BASE = {GENERAL: (8, 6, 4), SPECIAL: (8, 8, 4), PRECOMP: (7, 4, 3), COMP: (4, 6, 0)}
STRIDES = 0.70                                   # 100 m strides on tournament days before a match (activation, not conditioning)
LEAD_IN_WEEKS = 2                                # the block starts in the last 2 weeks of general preparation, as on the sheet


def build_interval_loads(g: dict, extra_reps: int = 0) -> dict:
    """Week-by-week running block laid out like the supplied "load distribution" sheet: 100 m at a % of maximal speed and interval
    runs of 120, 150 and 300 m (reps per week). It runs from the end of general preparation to competition and scales with the week's
    planned load, so each phase's hardest week gets the full reps and lighter weeks fewer. Total metres are worked out by the sheet (formula)."""
    n, kinds, pct = g["weeks"], g["kinds"], g["percentage"]
    gen = [w for w in range(n) if kinds[w] == GENERAL]
    block = set(gen[-LEAD_IN_WEEKS:]) | {w for w in range(n) if kinds[w] in (SPECIAL, PRECOMP, COMP)}
    if g.get("day_kind_keys"):                                   # a tournament drawn day by day: runs only on real training days
        block = {w for w in block if g["day_kind_keys"][w] in ("heavy", "medium", "free", "practice")}
    top = {k: max((pct[w] for w in block if kinds[w] == k), default=1) or 1 for k in (GENERAL, SPECIAL, PRECOMP, COMP)}   # each phase's hardest week
    speed = [None] * n
    for w in [w for w in gen[-LEAD_IN_WEEKS:] if w in block]:
        speed[w] = 0.80
    for ph, (lo, hi) in SPEED_100M.items():
        ws = [w for w in range(n) if kinds[w] == ph and w in block]
        for i, w in enumerate(ws):
            speed[w] = round(lo + (hi - lo) * (i // max(1, -(-len(ws) // 2))), 2) if len(ws) > 1 else lo
    if g.get("day_kind_keys"):                                   # tournament days: 100 m strides at 70% to activate before a match
        for w in range(n):
            if kinds[w] == COMP and g["day_kind_keys"][w] in ("before", "between"):
                speed[w] = STRIDES
    runs = {m: [None] * n for m in INTERVAL_RUNS}
    for w in sorted(block):
        for m, base in zip(INTERVAL_RUNS, INTERVAL_BASE[kinds[w]]):
            if base:
                runs[m][w] = max(1, int(base * pct[w] / top[kinds[w]] + 0.5)) + (extra_reps if m in (120, 150) else 0)
    total = [sum(m * (runs[m][w] or 0) for m in INTERVAL_RUNS) or None for w in range(n)]
    return {"speed_100m": speed, "runs": runs, "total": total}
