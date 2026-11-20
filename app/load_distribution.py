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


# ───────────── the supplied sheet's running block (100 m speed + speed endurance + 120 / 150 / 300 m interval runs) ─────────────
# Every phase is filled. What is used where follows the supplied "Example component distribution" table and the youth guidelines
# (Zatsiorsky ch. 5 and 10; NSCA youth position statement):
#   * 100 m at a % of maximal speed: technique strides in general preparation and transition (70-80%), building through special
#     preparation (85-90%) to fast running in pre-competition (95%) and competition (100%). A tournament week: strides at 70%.
#   * Anaerobic endurance (speed): the speed-endurance set of the phase - 60 m runs in general preparation (alactic, technique),
#     100 m intervals in special preparation (table: 100 m interval = S, C), 50 m intervals in pre-competition and competition
#     (table: 50 m interval = P, C). Short, with full recovery: U15 players have a limited glycolytic capacity, so long lactic
#     runs are not used. Transition: speed games (no set).
#   * Interval runs 120 / 150 / 300 m: aerobic-anaerobic conditioning in every phase. Reps fall from preparation to competition
#     (volume falls as intensity rises); transition keeps a light 120 m / 150 m set (active rest); a tournament week keeps 2 x 120 m.
# Reps scale with the week's planned load so each phase's hardest week gets the full reps and lighter weeks fewer.
INTERVAL_RUNS = (120, 150, 300)
SPEED_100M = {GENERAL: (0.75, 0.80), SPECIAL: (0.85, 0.90), PRECOMP: (0.95, 0.95), COMP: (1.00, 1.00), TRANS: (0.70, 0.70)}
STRIDES = 0.70                                   # 100 m strides: transition, and tournament days / weeks (activation, not conditioning)
# reps at each phase's hardest week (120 m, 150 m, 300 m)
INTERVAL_BASE = {GENERAL: (8, 6, 4), SPECIAL: (8, 8, 4), PRECOMP: (7, 4, 3), COMP: (4, 4, 2), TRANS: (4, 2, 2)}   # transition: easy pace
TOURNAMENT_RUNS = (2, 0, 0)                      # a week of a tournament: the matches carry the load ("match" in the empty rows)
TOURNAMENT_SE = (30, 3)                           # 30 m x 3 activation runs (alactic; table: 30 m = S, P, C)
SPEED_ENDURANCE = {GENERAL: (60, 4), SPECIAL: (100, 4), PRECOMP: (50, 6), COMP: (50, 4)}   # (metres, reps at the hardest week)
LEAD_IN_WEEKS = 2                                # kept for the notes: the supplied sheet opened its block 2 weeks before special prep

# Each player's own running, from their test ranks (player_season_plan.classify): a WEAK area gets more, a STRONG area keeps the
# squad's full work so it keeps improving. Never more than the extra below, so the plan stays safe for a 14-15-year-old.
PLAYER_EXTRA = {
    "endurance": "+1 rep of 120 m and 150 m every week they are run, +1 x 300 m in general and special preparation",
    "speed": "+2 reps of the speed-endurance set (row 13) in special preparation, pre-competition and competition",
}

# The player's other qualities, per week (rows under the running block): what the Annual plan marks, as a weekly dose.
# Squad dose at each phase's hardest week; a WEAK area adds the development extra. Youth guidelines: plyometric contacts low to
# moderate (NSCA: about 50-100 a session for trained youth, 2 non-consecutive days), 1-3 sets per exercise 2-3 times a week.
FOCUS_ROWS = [  # (area, row label, unit, grid row it follows, squad dose per phase, weak extra)
    # leg power: landing and jump technique in preparation (Coordination), explosive power in pre-competition and competition
    ("power", "Leg power (jump contacts)", "contacts", (("Physical", "Coordination"), ("Technical", "Explosive power")),
     {GENERAL: 30, SPECIAL: 50, PRECOMP: 80, COMP: 40, TRANS: 0}, 20),
    ("upper_strength", "Upper-body strength (push / pull sets)", "sets", (("Physical", "Strength"),),
     {GENERAL: 8, SPECIAL: 10, PRECOMP: 8, COMP: 6, TRANS: 4}, 4),
    ("core", "Core (minutes)", "min", (("Physical", "Strength"),),
     {GENERAL: 30, SPECIAL: 30, PRECOMP: 25, COMP: 20, TRANS: 15}, 15),
    ("agility", "Agility (change-of-direction reps)", "reps", (("Physical", "Coordination"),),
     {GENERAL: 10, SPECIAL: 16, PRECOMP: 20, COMP: 12, TRANS: 6}, 8),   # transition: games
]
TOURNAMENT_FOCUS = {"power": 0, "upper_strength": 4, "core": 15, "agility": 6}


def _player_areas(g: dict) -> tuple[set[str], set[str]]:
    p = g.get("player") or {}
    return {a["area"] for a in p.get("weak", [])}, {a["area"] for a in p.get("strong", [])}


def build_interval_loads(g: dict, extra_reps: int | None = None) -> dict:
    """Week-by-week running block laid out like the supplied "load distribution" sheet, filled in every phase, plus the player's
    other qualities as weekly doses. g: a grid from annual_grid.build_grid, or a player's (player_season_plan.personal_grid), whose
    weak / strong areas change the numbers. Total metres are worked out by the sheet (formula)."""
    n, kinds, pct = g["weeks"], g["kinds"], g["percentage"]
    weak, _strong = _player_areas(g)
    if extra_reps is None:
        extra_reps = 1 if "endurance" in weak else 0
    dk = g.get("day_kind_keys")                                  # a tournament drawn day by day
    tour_week = [False] * n
    if not dk and (g.get("daily") or {}).get("tournament"):
        d = g["daily"]
        for i, w in enumerate(d["week_of_day"]):
            if d["day_kind_keys"][i] == "match":
                tour_week[w] = True                              # a week of the tournament (matches every second day)
    train = [True] * n
    if dk:
        train = [dk[w] in ("heavy", "medium", "free", "practice") for w in range(n)]
    top = {k: max((pct[w] for w in range(n) if kinds[w] == k and train[w] and not tour_week[w]), default=1) or 1 for k in INTERVAL_BASE}

    def scale(base: int, w: int) -> int:
        return max(1, int(base * pct[w] / top[kinds[w]] + 0.5)) if base else 0

    speed = [None] * n
    for ph, (lo, hi) in SPEED_100M.items():
        ws = [w for w in range(n) if kinds[w] == ph and train[w] and not tour_week[w]]
        half = max(1, -(-len(ws) // 2))
        for i, w in enumerate(ws):
            speed[w] = round(lo + (hi - lo) * (i // half), 2) if len(ws) > 1 else lo
    for w in range(n):
        if tour_week[w] or (dk and kinds[w] == COMP and dk[w] in ("before", "between")):
            speed[w] = STRIDES

    runs = {m: [None] * n for m in INTERVAL_RUNS}
    se_m, se_reps = [None] * n, [None] * n
    for w in range(n):
        k = kinds[w]
        if not train[w]:
            continue
        base = TOURNAMENT_RUNS if tour_week[w] else INTERVAL_BASE[k]
        for m, b in zip(INTERVAL_RUNS, base):
            reps = (b if tour_week[w] else scale(b, w))
            if reps and m in (120, 150) and not tour_week[w]:
                reps += extra_reps
            if m == 300 and "endurance" in weak and k in (GENERAL, SPECIAL):
                reps += 1
            runs[m][w] = reps or None
        if tour_week[w]:
            se_m[w], se_reps[w] = TOURNAMENT_SE
        elif k in SPEED_ENDURANCE:
            dist, b = SPEED_ENDURANCE[k]
            r = scale(b, w) + (2 if "speed" in weak and k in (SPECIAL, PRECOMP, COMP) else 0)
            se_m[w], se_reps[w] = dist, r
    total = [sum(m * (runs[m][w] or 0) for m in INTERVAL_RUNS) + (se_m[w] or 0) * (se_reps[w] or 0) or None for w in range(n)]

    # the player's other qualities, in the weeks the (player's own) Annual plan marks them
    marks = {(s["name"], r["label"]): r["marks"] for s in g["sections"] for r in s["rows"]}
    focus = []
    for area, label, unit, rows, dose, extra in FOCUS_ROWS:
        on = [any(marks.get(r, [False] * n)[w] for r in rows) for w in range(n)]
        vals = [None] * n
        for w in range(n):
            if not train[w]:
                continue
            if tour_week[w]:
                v = TOURNAMENT_FOCUS[area]
            else:
                v = int(dose[kinds[w]] * min(1.0, pct[w] / top[kinds[w]] + 0.25) + 0.5) if dose[kinds[w]] else 0
                if not (on[w] or kinds[w] == TRANS):
                    v = int(v / 2 + 0.5)                     # a lighter week the plan does not mark: half the dose (maintenance)
                if v and area in weak:
                    v += extra
            vals[w] = v or None
        focus.append({"area": area, "label": label, "unit": unit, "values": vals, "weak": area in weak})
    return {"speed_100m": speed, "runs": runs, "speed_endurance_m": se_m, "speed_endurance_reps": se_reps, "total": total,
            "focus": focus, "tournament_weeks": tour_week}
