"""The annual (seasonal) plan as a week-by-week grid, laid out like the supplied "ANNUAL PLAN FOR U-16 RUGBY TEAM" sheet.

Pure module: no database, no web, no Excel. `build_grid()` turns a season, its phases and the calendar into columns
(one per week) and rows of marks. `annual_grid_excel.py` draws it.

What is data and what is proposal
  * DATA: the weeks, months, phase dates, match weeks, test weeks and weekly hours come from the season and the calendar.
  * PROPOSAL: which training areas are marked in which phase (PHASE_RULES below), the macro block lengths, the planned
    relative load (percentage) and the loading index. They follow the supplied sheet's pattern, adjusted for cricket and
    for junior players (lower peak per age group, no heavy-power work before pre-competition). Coaches review and change them.
  * Every mark that depends on an exercise kind is checked against exercise_kinds.PHASE_KINDS by a test, so the grid and
    the seasonal-plan rows cannot disagree about what is allowed in a phase.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.reference.age_groups import profile as age_profile
from app.planning.season_phases import SHORT_SEASON_DAYS

# The five columns-of-meaning on the sheet's "Phases" row. Our season has four phases; the preparation phase is split
# into general and special preparation like the supplied sheet.
GENERAL, SPECIAL, PRECOMP, COMP, TRANS = "general_prep", "special_prep", "pre_competition", "competition", "transition"
PHASE_LABEL = {GENERAL: "General preparation", SPECIAL: "Special preparation", PRECOMP: "Pre-competition",
               COMP: "Competition", TRANS: "Transition"}
PERIOD_OF = {GENERAL: "Preparation", SPECIAL: "Preparation", PRECOMP: "Competition", COMP: "Competition", TRANS: "Transition"}
GENERAL_SHARE = 0.60            # of the pre-season weeks; the rest is special preparation
MACRO_WEEKS = {GENERAL: 4, SPECIAL: 3, PRECOMP: 2, COMP: 3, TRANS: 2}
PEAK = 0.90                     # U15 default; the supplied sheet peaks at 97%. Each age group sets its own (app/reference/age_groups.py)
START = 0.25
RECOVERY_FACTOR = 0.70          # the last week of a preparation block is lighter (the sheet does the same: 40% -> 28%)
LEVELS = {                      # percentage at the first and last week of the phase, for phases without a ramp
    PRECOMP: (0.70, 0.62), COMP: (0.50, 0.45), TRANS: (0.40, 0.30),
}
LOADING = {                     # (volume, intensity) per phase: volume falls while intensity rises toward competition
    GENERAL: ("High", "low"), SPECIAL: ("High", "Medium"), PRECOMP: ("Medium", "High"),
    COMP: ("low", "High"), TRANS: ("low", "low"),
}
# The supplied sheet typed "Load" by phase and so contradicted its own % row (Medium in the hardest weeks). Here Load is
# read from the Percentage row, so the two always agree.
LOAD_HIGH, LOAD_MEDIUM = 0.75, 0.50


def load_level(p: float) -> str:
    return "" if not p else "High" if p >= LOAD_HIGH else "Medium" if p >= LOAD_MEDIUM else "low"

# rule per phase: "all" every week, "alt" every second week, "non_recovery" every week except the lighter week of a block.
# Missing phase = not marked. Flags: first = also the first week of the season, last = also the last week,
# skip_first = never in week 1.
_G, _S, _P, _C, _T = GENERAL, SPECIAL, PRECOMP, COMP, TRANS
PHASE_RULES: dict[str, list[tuple[str, dict]]] = {
    "Physical": [
        ("Endurance", {_G: "all", _S: "all", _T: "all"}),
        ("Strength", {_G: "non_recovery", _S: "non_recovery", _P: "all", _C: "alt"}),
        ("Speed", {_P: "all", _C: "all"}),
        ("Flexibility", {_G: "all", _S: "all", _P: "all", _C: "all", _T: "all"}),
        ("Coordination", {_G: "all", _S: "all", _P: "all", _C: "all"}),
    ],
    "Mental": [
        ("Concentration", {_S: "all", _P: "all", _C: "all"}),
        ("Relaxation", {_G: "all", _S: "all", _P: "all", _C: "all", "skip_first": True}),
        ("Goal setting", {_S: "all", _P: "all", _C: "all", "first": True, "last": True}),
        ("Focusing", {_G: "all", _S: "all", _P: "all", _C: "all", "skip_first": True, "last": True}),
        ("Imagination", {_G: "all", _S: "all", _P: "all", _C: "all", "skip_first": True, "last": True}),
        ("Confidence", {_S: "all", _P: "all", _C: "all"}),
    ],
    "Technical": [
        ("Basic", {_G: "all", _S: "all"}),
        ("Advance", {_P: "all", _C: "alt"}),
        ("Competition", {_P: "all", _C: "all"}),
        ("Explosive power", {_P: "all", _C: "alt"}),
        ("Reaction speed", {_G: "alt", _S: "alt", _P: "all", _C: "all"}),
        ("Anaerobic endurance", {_P: "alt"}),
    ],
    "Tactical": [
        ("Basic", {_G: "all", _S: "all"}),
        ("Offensive", {_P: "alt", _C: "alt"}),
        ("Defensive", {_P: "alt", _C: "alt"}),
    ],
    # Nutrition: a '*' marks the weeks a nutrient is EMPHASISED (a balanced diet is needed every week). Marking every nutrient
    # every week, as the supplied sheet does, says nothing; these follow the load (see NUTRITION_FOCUS in build_grid).
    "Nutrition": [(n, {_G: "all", _S: "all", _P: "all", _C: "all", _T: "all"})
                  for n in ("Carbohydrate", "Fat", "Protein", "Vitamin", "Minerals", "Electrolytes")],
}
NUTRITION_FOCUS = {
    "Carbohydrate": "fuel: weeks at 60% or more, match weeks, pre-competition and competition",
    "Fat": "energy for growth and high volume: general preparation and transition; recovery days in competition (never on a match day or the day before)",
    "Protein": "repair: weeks with strength work, and transition",
    "Vitamin": "every week (growing players)",
    "Minerals": "every week (calcium and iron for growing players)",
    "Electrolytes": "sweat losses: weeks at 75% or more, match weeks, pre-competition and competition",
}

# Which exercise kinds (exercise_kinds.PHASE_KINDS) a mark stands for. Rows not listed here (flexibility, mental,
# nutrition) are not tied to an exercise kind. Used by the consistency test.
ROW_KINDS: dict[tuple[str, str], set[str]] = {
    ("Physical", "Endurance"): {"aerobic"},
    ("Physical", "Strength"): {"leg_strength", "upper_strength"},
    ("Physical", "Speed"): {"speed"},
    ("Physical", "Coordination"): {"agility", "landing"},
    ("Technical", "Basic"): {"foundation", "catching", "ground_fielding", "throwing"},
    ("Technical", "Advance"): {"variation", "tactical"},
    ("Technical", "Competition"): {"match_prep"},
    ("Technical", "Explosive power"): {"plyometric_power", "rotation_power"},
    ("Technical", "Reaction speed"): {"speed", "agility"},
    ("Technical", "Anaerobic endurance"): {"repeat_sprint"},
    ("Tactical", "Basic"): {"analysis"},
    ("Tactical", "Offensive"): {"tactical"},
    ("Tactical", "Defensive"): {"tactical"},
}
SEASON_PHASE_OF = {GENERAL: "pre_season", SPECIAL: "pre_season", PRECOMP: "pre_competition", COMP: "in_season", TRANS: "transition"}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _weeks(start: date, end: date) -> int:
    return -(-((end - start).days + 1) // 7)


def _phase_for(d: date, phases: list[dict]) -> dict:
    inside = [p for p in phases if p["start_date"] <= d <= p["end_date"]]
    if inside:
        return inside[0]
    before = [p for p in phases if p["end_date"] < d]
    return before[-1] if before else phases[0]


def _mark(rule: str | None, idx: int, recovery: bool) -> bool:
    return rule == "all" or (rule == "alt" and idx % 2 == 0) or (rule == "non_recovery" and not recovery)


YEAR_WEEKS = 52                 # the annual plan covers a whole year (52 weeks, 364 days) from the season's start date
YEAR_TRANSITION_DAYS = 21       # after the season: 3 weeks of transition (active rest), unless the season already ends with one
YEAR_PRECOMP_DAYS = 28          # the year's last 4 weeks: pre-competition, the run-in to next year's season


def year_phases(s0: date, e0: date, phases: list[dict], weeks: int = YEAR_WEEKS) -> tuple[date, list[dict]]:
    """The season's phases followed by the rest of the year: transition after the competition, general and special
    preparation, then pre-competition into next year's season (Zatsiorsky ch. 5: one annual cycle ends where the next
    competition period begins). Returns (last day of the year, phases)."""
    y_end = s0 + timedelta(days=7 * weeks - 1)
    phases = sorted(phases, key=lambda p: p["start_date"])
    if e0 >= y_end:
        return e0, phases
    out, cur = list(phases), e0 + timedelta(days=1)
    left = (y_end - cur).days + 1

    def add(kind: str, days: int):
        nonlocal cur, left
        if days <= 0:
            return
        end = cur + timedelta(days=days - 1)
        if out and out[-1]["phase_type"] == kind and out[-1]["end_date"] == cur - timedelta(days=1):
            out[-1] = {**out[-1], "end_date": end}               # carries on the season's own last phase
        else:
            out.append({"phase_type": kind, "start_date": cur, "end_date": end, "added": True})
        cur, left = end + timedelta(days=1), left - days

    trans = 0 if phases[-1]["phase_type"] == "transition" else min(YEAR_TRANSITION_DAYS, left)
    if left - trans < 14:                                        # too little left for a preparation: it is all transition
        trans = left
    add("transition", trans)
    pre = YEAR_PRECOMP_DAYS if left >= 2 * YEAR_PRECOMP_DAYS else 0
    add("pre_season", left - pre)
    add("pre_competition", pre)
    return y_end, out


def build_grid(*, squad_name: str, season: dict, phases: list[dict], events: list[dict], generated_on: date, age_group: str | None = None,
               year: bool = False) -> dict:
    """season: {name, start_date, end_date}. phases: [{phase_type, start_date, end_date}] using the season phase names
    (pre_season, pre_competition, in_season, transition). events: [{event_type, date, hours|None}].
    year=True: the plan covers a whole year (YEAR_WEEKS weeks) from the season's start; the weeks after the season follow
    year_phases(). Otherwise it covers the season only."""
    s0, e0 = season["start_date"], season["end_date"]
    prof = age_profile(age_group)
    peak = prof.load_peak
    if (e0 - s0).days + 1 < 1:
        raise ValueError("The season ends before it starts")          # short seasons (a tournament) are fine: one column per week
    if not phases:
        raise ValueError("The season has no phases")
    phases = sorted(phases, key=lambda p: p["start_date"])
    season_end = e0
    short = (e0 - s0).days + 1 < SHORT_SEASON_DAYS                    # the season itself is a tournament
    if year:
        e0, phases = year_phases(s0, e0, phases)
        season = {**season, "end_date": e0}
    n = _weeks(s0, e0)
    starts = [s0 + timedelta(days=7 * i) for i in range(n)]

    # --- which phase is each week in (general / special preparation split inside pre-season) ---
    base = [_phase_for(d, phases)["phase_type"] for d in starts]
    kind = [{"pre_season": GENERAL, "pre_competition": PRECOMP, "in_season": COMP, "transition": TRANS}[t] for t in base]
    i = 0
    while i < n:                                                 # each preparation block (a year can have two) is split on its own
        if base[i] != "pre_season":
            i += 1
            continue
        j = i
        while j + 1 < n and base[j + 1] == "pre_season":
            j += 1
        m = j - i + 1
        n_gen = m if m <= 1 else max(1, min(m - 1, round(m * GENERAL_SHARE)))
        for w in range(i + n_gen, j + 1):
            kind[w] = SPECIAL
        i = j + 1

    # --- macro blocks: never cross a phase boundary; a one-week leftover joins the block before it ---
    macro = [0] * n
    blocks: list[tuple[int, int, str]] = []                      # (first, last, phase)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and kind[j + 1] == kind[i]:
            j += 1
        size, a = MACRO_WEEKS[kind[i]], i
        while a <= j:
            b = min(a + size - 1, j)
            if j - b == 1:                                      # never leave a single week on its own
                b = j
            blocks.append((a, b, kind[i]))
            a = b + 1
        i = j + 1
    recovery = [False] * n
    for num, (a, b, k) in enumerate(blocks, 1):
        for w in range(a, b + 1):
            macro[w] = num
        if k in (GENERAL, SPECIAL) and b - a + 1 >= 3:
            recovery[b] = True

    # --- planned relative load ---
    pct = [0.0] * n
    prep = [w for w in range(n) if kind[w] in (GENERAL, SPECIAL)]
    loading_weeks = [w for w in prep if not recovery[w]]
    ramps: list[list[int]] = []                                  # each preparation block ramps from START to the peak on its own
    for w in loading_weeks:
        if ramps and all(kind[x] in (GENERAL, SPECIAL) for x in range(ramps[-1][-1], w + 1)):
            ramps[-1].append(w)
        else:
            ramps.append([w])
    for ramp in ramps:
        for k, w in enumerate(ramp):
            pct[w] = round(START + (peak - START) * (k / (len(ramp) - 1) if len(ramp) > 1 else 0), 2)
    for w in prep:
        if recovery[w]:
            prev = max((x for x in loading_weeks if x < w), default=None)
            pct[w] = round(pct[prev] * RECOVERY_FACTOR, 2) if prev is not None else START
    for ph, (hi, lo) in LEVELS.items():
        ws = [w for w in range(n) if kind[w] == ph]
        for k, w in enumerate(ws):
            pct[w] = round(hi + (lo - hi) * (k / (len(ws) - 1) if len(ws) > 1 else 0), 2)

    # --- calendar facts ---
    def week_of(d: date) -> int | None:
        k = (d - s0).days // 7
        return k if 0 <= k < n and d <= e0 else None
    matches, match_n, hours, tests = set(), [0] * n, [0.0] * n, set()
    for ev in events:
        w = week_of(ev["date"])
        if w is None:
            continue
        if ev["event_type"] == "match":
            matches.add(w)
            match_n[w] += 1
        if ev["event_type"] == "fitness_test":
            tests.add(w)
        if ev["event_type"] in ("training", "match") and ev.get("hours"):
            hours[w] += ev["hours"]
    tests_source = "calendar"
    if not tests and short and year:                            # a tournament, then the year: test at the start of each preparation block
        tests_source = "suggested"
        tests = {next((w for w in range(n) if kind[w] == k), None) for k in (GENERAL, SPECIAL, PRECOMP)} - {None}
    elif not tests and short:                                   # a tournament: test before it, not during it
        tests_source = "none"
    elif not tests:                                             # same suggested times as the seasonal plan's testing schedule
        tests_source = "suggested"
        mid_ph = next((p for p in phases if p["phase_type"] == "in_season"), None)
        mid = (mid_ph["start_date"] + (mid_ph["end_date"] - mid_ph["start_date"]) / 2) if mid_ph else s0 + (season_end - s0) / 2
        tests = {0, week_of(mid), week_of(season_end)} - {None}
        if year:                                                 # and before next year's season
            tests.add(next((w for w in range(n) if kind[w] == PRECOMP and starts[w] > season_end), n - 1))

    # --- rows of marks ---
    sections = []
    for sec, rows in PHASE_RULES.items():
        out = []
        for label, rules in rows:
            marks = []
            seen = {}
            for w in range(n):
                k = kind[w]
                idx = seen.get(k, 0)
                seen[k] = idx + 1
                on = _mark(rules.get(k), idx, recovery[w])
                if w == 0 and rules.get("skip_first"):
                    on = False
                if (w == 0 and rules.get("first")) or (w == n - 1 and rules.get("last")):
                    on = True
                marks.append(on)
            out.append({"label": label, "marks": marks})
        sections.append({"name": sec, "rows": out})
    strength = next(r for s in sections if s["name"] == "Physical" for r in s["rows"] if r["label"] == "Strength")["marks"]
    focus = {
        "Carbohydrate": lambda w: pct[w] >= 0.60 or w in matches or kind[w] in (PRECOMP, COMP),
        "Fat": lambda w: kind[w] in (GENERAL, TRANS, COMP),
        "Protein": lambda w: strength[w] or kind[w] == TRANS,
        "Vitamin": lambda w: True, "Minerals": lambda w: True,
        "Electrolytes": lambda w: pct[w] >= LOAD_HIGH or w in matches or kind[w] in (PRECOMP, COMP),
    }
    for s in sections:
        if s["name"] == "Nutrition":
            for r in s["rows"]:
                r["marks"] = [bool(focus[r["label"]](w)) for w in range(n)]

    def runs(values):                                           # consecutive weeks with the same value -> (first, last, value)
        out, a = [], 0
        for w in range(1, n + 1):
            if w == n or values[w] != values[a]:
                out.append((a, w - 1, values[a]))
                a = w
        return out

    spans_years = starts[0].year != starts[-1].year
    month_key = [(d.year, d.month) for d in starts]
    mesos = [(a, b, f"{MONTHS[m - 1]} {y}" if spans_years and (a == 0 or m == 1) else MONTHS[m - 1], m) for a, b, (y, m) in runs(month_key)]
    g = {
        "title": f"ANNUAL PLAN FOR {squad_name.upper()} ({season['name']})",
        "squad": squad_name, "season": season["name"], "weeks": n, "week_starts": starts, "age_group": prof.code,
        "periods": [(a, b, v) for a, b, v in runs([PERIOD_OF[k] for k in kind])],
        "phases": [(a, b, v) for a, b, v in runs(kind)],
        "mesos": mesos,
        "macros": [(a, b, num) for num, (a, b, _) in enumerate(blocks, 1)],
        "days": [d.day for d in starts], "percentage": pct, "hours": [round(h, 1) if h else None for h in hours],
        "match_weeks": [w in matches for w in range(n)], "match_counts": match_n, "test_weeks": [w in tests for w in range(n)], "tests_source": tests_source,
        "recovery_weeks": recovery, "kinds": kind, "sections": sections,
        "loading": {"Volume": [LOADING[k][0] for k in kind], "Intensity": [LOADING[k][1] for k in kind], "Load": [load_level(p) for p in pct]},
        "generated_on": generated_on, "season_end": e0,
        "notes": [
            "The whole season is ONE macrocycle. The Mesos row shows the calendar months; the numbered blocks in the Macros row are "
            "the training blocks (2 to 6 weeks, shorter toward competition).",
            "Weeks start on the season's start date and run in blocks of seven days. The Dates row shows the day of the month each week starts on.",
            f"Percentage is the planned relative training load, not a measurement. Preparation builds from {int(START * 100)}% to {int(peak * 100)}% with a lighter week at the end of each block; "
            f"the supplied rugby sheet peaks higher, so this is lower for {prof.code} players. Coaches adjust it.",
            "A '*' marks a week in which that area is trained. The marks are a proposal for the coaches to confirm and follow the exercise-to-phase mapping used in the seasonal plan.",
            ("Test weeks are the fitness-test events in the calendar." if tests_source == "calendar"
             else "No test weeks are suggested in a season shorter than 4 weeks (a tournament): test before it starts, or add a fitness-test event to the calendar."
             if tests_source == "none"
             else "Test weeks are SUGGESTED (first week, middle of the in-season phase, last week) because no fitness-test events are in the calendar."),
            "Medical and Field are marked in every test week. Lab is left empty because the system does not schedule laboratory tests.",
            "Competition marks the weeks with a match in the calendar. Week hours add up the training and match hours in the calendar (blank when none have an end time).",
            "Volume falls and Intensity rises toward competition. Load is read from the Percentage row (High from 75%, Medium from 50%), "
            "so the words and the numbers never disagree. They are guidance, not a prescription for any one player.",
            "Nutrition: a '*' marks the weeks a nutrient is EMPHASISED; a balanced diet is needed every week. "
            + "; ".join(f"{k} - {v}" for k, v in NUTRITION_FOCUS.items()) + ".",
        ],
    }
    g["daily"] = build_daily(g, season=season, phases=phases, events=events, kind_of_week=kind, pct_of_week=pct, short=short,
                             season_end=season_end, draw_daily=short and not year)
    if year:
        g["year"], g["season_last_day"] = True, season_end         # season_end stays the plan's last day (the end of the year)
        g["title"] = f"ANNUAL PLAN FOR {squad_name.upper()} ({season['name']}) - {s0:%d %b %Y} TO {e0:%d %b %Y}".upper()
        after = ("then transition (3 weeks of active rest unless the season ends with one), general and special preparation, and "
                 "4 weeks of pre-competition into next year's season. The weeks after the season are a PROPOSAL; set real dates in "
                 "Admin, Seasons. " if any(p.get("added") for p in phases) else "")
        g["notes"][0] = ("The plan covers ONE YEAR (52 weeks) from the season's start: the season's own phases, " + after +
                         "The Mesos row shows the calendar months; the numbered blocks in the Macros row are the training blocks.")
        if not matches and g["daily"]["assumed_matches"]:        # no match in the calendar: show the assumed match weeks
            d = g["daily"]
            cnt = [0] * n
            for i, on in enumerate(d["match_weeks"]):
                if on:
                    cnt[d["week_of_day"][i]] += 1
            g["match_weeks"], g["match_counts"] = [c > 0 for c in cnt], cnt
            g["notes"].append("Competition: no matches are in the calendar, so the competition weeks show ASSUMED matches"
                              + (" (a match every second day of the tournament)." if short else " (Saturdays).")
                              + " Add the matches in Calendar and download again.")
    if not any(g["hours"]):                                     # no session times in the calendar: the planned hours of the week's days
        d = g["daily"]
        g["hours"] = [round(sum(d["hours"][i] or 0 for i in range(d["weeks"]) if d["week_of_day"][i] == w), 1) or None for w in range(n)]
        g["hours_planned"] = True
    return g


# ───────────── the day-by-day grid (the sheets are drawn one column per DAY) ─────────────
# Day kinds. Competition days follow the match days: match, before (day before a match), after (day after a match, no match next
# day), between (between two matches), free (no match the day before or after). Other weeks follow a weekly microcycle template.
WEEK_TEMPLATE = {
    GENERAL: ["heavy", "medium", "light", "heavy", "medium", "practice", "rest"],
    SPECIAL: ["heavy", "medium", "light", "heavy", "medium", "practice", "rest"],
    PRECOMP: ["heavy", "medium", "light", "heavy", "light", "practice", "rest"],
    TRANS: ["active", "rest", "active", "rest", "active", "rest", "rest"],
}
# share of the week's percentage on each kind of day (rule of 60%: the lightest training day is about 60% of the heaviest)
DAY_FACTOR = {"heavy": 1.0, "medium": 0.8, "light": 0.6, "practice": 0.7, "rest": 0.0, "active": 0.6,
              "match": 1.0, "free": 0.8, "before": 0.6, "after": 0.5, "between": 0.5}
DAY_KIND_LABEL = {"heavy": "Heavy training day", "medium": "Medium training day", "light": "Light day", "practice": "Match practice",
                  "rest": "Rest", "active": "Active rest", "match": "Match", "free": "Training day", "before": "Day before a match",
                  "after": "Recovery day", "between": "Between matches"}
TRAINING_DAYS = {"heavy", "medium", "light", "practice", "active", "free", "before", "after", "between"}
# what each row does on each kind of day (weekday names are allowed too); the week's own mark must also be on
DAY_RULES: dict[str, dict[str, set]] = {
    "Physical": {"Endurance": {"medium", "active"}, "Strength": {"heavy", "free", "after", "between"}, "Speed": {"heavy", "free", "before"},
                 "Flexibility": TRAINING_DAYS | {"match"}, "Coordination": {"heavy", "medium", "practice", "before", "after", "between", "free"}},
    "Mental": {"Concentration": {"heavy", "practice", "match", "before"}, "Relaxation": {"light", "after", "between", "rest"},
               "Goal setting": {"Mon", "before", "first", "last"}, "Focusing": {"medium", "practice", "match", "before"},
               "Imagination": {"light", "practice", "before", "between"}, "Confidence": {"practice", "match", "before", "after", "between", "free"}},
    "Technical": {"Basic": {"medium", "practice", "between"}, "Advance": {"medium", "practice", "free"}, "Competition": {"practice", "match", "before"},
                  "Explosive power": {"heavy", "free"}, "Reaction speed": {"heavy", "practice", "free", "before"},
                  "Anaerobic endurance": {"medium"}},
    "Tactical": {"Basic": {"light", "after", "between"}, "Offensive": {"medium", "practice", "match", "before"}, "Defensive": {"medium", "practice", "match", "before"}},
    # nutrition emphasis by day, inside the weeks the weekly grid emphasises it
    "Nutrition": {"Carbohydrate": {"heavy", "medium", "practice", "match", "before", "free"},
                  "Fat": {"heavy", "medium", "light", "practice", "active", "rest", "free", "after", "between"}, "Protein": {"heavy", "free", "after", "between", "active"},
                  "Vitamin": TRAINING_DAYS | {"match", "rest"}, "Minerals": TRAINING_DAYS | {"match", "rest"},
                  "Electrolytes": {"heavy", "medium", "practice", "match", "free"}},
}
# (volume, intensity) for each kind of day; the day's Load is read from its Percentage (load_level), so they always agree
# planned hours for a kind of day, used when the calendar has no session times (a match day is a one-day game)
PLANNED_HOURS = {"heavy": 2.0, "medium": 1.5, "light": 1.0, "practice": 2.0, "rest": 0.0, "active": 1.0,
                 "match": 7.0, "free": 2.0, "before": 1.5, "after": 1.0, "between": 1.0}
DAY_LOADING = {"heavy": ("High", "Medium"), "medium": ("High", "low"), "light": ("low", "low"),
               "practice": ("Medium", "High"), "rest": ("", ""), "active": ("low", "low"),
               "match": ("low", "High"), "free": ("Medium", "High"), "before": ("low", "Medium"),
               "between": ("low", "low"), "after": ("low", "low")}


def build_daily(g: dict, *, season: dict, phases: list[dict], events: list[dict], kind_of_week: list[str], pct_of_week: list[float],
                short: bool = False, season_end: date | None = None, draw_daily: bool | None = None) -> dict:
    """The season with one column per day. Competition days follow the match days (Zatsiorsky ch. 5: the competition microcycle
    matches the competition); preparation and transition weeks follow a weekly microcycle template with the load varied day to day.
    short: the season is a tournament (matches assumed every second day). season_end: the season's last day when the grid runs
    past it (a year plan). draw_daily: whether the sheets are drawn day by day (the "short" key); defaults to short."""
    s0, e0 = season["start_date"], season["end_date"]
    last = season_end or e0
    days = [s0 + timedelta(days=i) for i in range((e0 - s0).days + 1)]
    n = len(days)
    wk = [(d - s0).days // 7 for d in days]
    kind = [kind_of_week[w] for w in wk]
    real = sorted({ev["date"] for ev in events if ev["event_type"] == "match" and s0 <= ev["date"] <= e0})
    mset = set(real)
    assumed: list = []
    comp_weeks = sorted({wk[i] for i in range(n) if kind[i] == COMP})
    for w in comp_weeks:                                         # a competition week with no match in the calendar: assume one
        idx = [i for i in range(n) if wk[i] == w and kind[i] == COMP]
        if any(days[i] in mset for i in idx):
            continue
        if short:
            pick = [days[i] for i in idx if (i - idx[0]) % 2 == 0]           # a tournament: a match every second day
        else:
            pick = [next((days[i] for i in idx if days[i].weekday() == 5), days[idx[-1]])]   # a league week: Saturday
        assumed += pick
        mset |= set(pick)
    if short and real:
        assumed = []
    tests = {ev["date"] for ev in events if ev["event_type"] == "fitness_test"}
    hours = [0.0] * n
    for ev in events:
        if ev["event_type"] in ("training", "match") and ev.get("hours") and s0 <= ev["date"] <= e0:
            hours[(ev["date"] - s0).days] += ev["hours"]

    def day_kind(i: int) -> str:
        d = days[i]
        b, a = d + timedelta(days=1) in mset, d - timedelta(days=1) in mset
        if d in mset:
            return "match"
        if kind[i] == COMP:
            return "free" if not b and not a else "after" if a and not b else "between" if a else "before"
        if b:
            return "before"                                      # a match in a preparation week: the day before is light
        return WEEK_TEMPLATE[kind[i]][d.weekday()]

    dk = [day_kind(i) for i in range(n)]
    if not tests and g.get("tests_source") == "suggested":      # the suggested test weeks: test on the freshest day of the week
        rank = {"heavy": 0, "free": 0, "medium": 1, "light": 2, "practice": 2, "active": 3}
        for w, on in enumerate(g["test_weeks"]):
            idx = [i for i in range(n) if wk[i] == w and dk[i] in rank]
            if on and idx:
                tests.add(days[min(idx, key=lambda i: (rank[dk[i]], i))])
    weekly = {sec["name"]: {r["label"]: r["marks"] for r in sec["rows"]} for sec in g["sections"]}
    sections = []
    for sec in g["sections"]:
        rows = []
        for r in sec["rows"]:
            marks = []
            for i, d in enumerate(days):
                if sec["name"] not in DAY_RULES:                 # nutrition: every day
                    on = weekly[sec["name"]][r["label"]][wk[i]]
                else:
                    want = DAY_RULES[sec["name"]].get(r["label"], set())
                    week_on = (kind[i] == COMP and sec["name"] != "Nutrition") or weekly[sec["name"]][r["label"]][wk[i]]   # competition days follow the matches
                    on = (dk[i] in want or d.strftime("%a") in want) and week_on
                    on = on or (r["label"] == "Goal setting" and ((i == 0 and "first" in want) or (i == n - 1 and "last" in want)))
                marks.append(bool(on))
            rows.append({"label": r["label"], "marks": marks})
        sections.append({"name": sec["name"], "rows": rows})

    def runs(values):
        out, a = [], 0
        for i in range(1, n + 1):
            if i == n or values[i] != values[a]:
                out.append((a, i - 1, values[a]))
                a = i
        return out

    week_pct = [pct_of_week[w] for w in wk]
    pct = [round(week_pct[i] * DAY_FACTOR[dk[i]], 2) for i in range(n)]
    load = [DAY_LOADING[dk[i]] + (load_level(pct[i]),) for i in range(n)]
    macro_of_week = [0] * len(kind_of_week)
    for a, b, num in g["macros"]:
        for w in range(a, b + 1):
            macro_of_week[w] = num
    spans_years = days[0].year != days[-1].year
    notes = [
        "DAY BY DAY: one column per day. Micros groups the days into 7-day microcycles (numbered from the season start); "
        "the Dates row shows the weekday and the day of the month; the Day row says what kind of day it is.",
        ("Competition marks the match days in the calendar." if not assumed else
         f"{len(assumed)} match day(s) are ASSUMED because the calendar has none in those competition weeks"
         + (" (a match every second day of the tournament)" if short else " (Saturday)") + ". Add the matches in Calendar and download again."),
        "Percentage is the week's planned load spread over the days by the rule of 60% (Zatsiorsky ch. 5): heavy day 100% of the week's "
        "value, medium 80%, match practice 70%, light 60%, rest 0. In competition: match day 100%, training day 80%, the day before a "
        "match 60% (activation, no heavy work), recovery days 50%.",
        "Preparation weeks: heavy days Monday and Thursday (strength, speed, explosive power while fresh), medium days Tuesday and Friday "
        "(endurance, technique, tactics), Wednesday light (flexibility, tactical basics, relaxation), Saturday match practice, Sunday rest. "
        "Transition: active rest on Monday, Wednesday and Friday.",
        "Competition days: strength only on training days and the day after a match (upper body and trunk); never on a match day or the day "
        "before. Mental skills follow the matches: concentration and focusing on match days and the day before, relaxation after.",
        "Each day has its session plan in the Session plan sheets. Percentages and '*' marks are a proposal for the coaches to confirm.",
    ] + [x for x in g["notes"] if x.startswith(("The whole season is ONE macrocycle", "Volume falls", "Nutrition:"))] + [
        "Test days: " + ("the fitness-test events in the calendar." if g.get("tests_source") == "calendar" else
                         "SUGGESTED on the freshest day of each suggested test week (after the rest day); add fitness-test events in Calendar to fix them."
                         if tests else "none suggested for a tournament: test before it starts."),
    ] + [x for x in g["notes"] if x.startswith("The season has no phases")]
    return {
        "title": g["title"] + " - DAY BY DAY", "squad": g["squad"], "season": g["season"], "weeks": n, "week_starts": days,
        "periods": [(a, b, v) for a, b, v in runs([PERIOD_OF[k] for k in kind])],
        "phases": [(a, b, v) for a, b, v in runs(kind)],
        "mesos": [(a, b, f"{MONTHS[m - 1]} {y}" if spans_years and (a == 0 or m == 1) else MONTHS[m - 1], m)
                  for a, b, (y, m) in runs([(d.year, d.month) for d in days])],
        "macros": [(a, b, v) for a, b, v in runs([macro_of_week[w] for w in wk])],
        "micros": [(a, b, num + 1) for a, b, num in runs(wk)],
        "kinds": kind, "day_kind_keys": dk, "day_kinds": [DAY_KIND_LABEL[k] for k in dk],
        "weekdays": [d.strftime("%a") for d in days],
        "days": [d.day for d in days], "dates": days, "percentage": pct, "week_percentage": week_pct,
        "hours": ([round(h, 1) if h else None for h in hours] if any(hours) else [PLANNED_HOURS[k] or None for k in dk]),
        "hours_planned": not any(hours), "hours_label": "day hours",
        # a tournament: medical check on the first and last day (and on any test day)
        "medical_days": [d in tests or (short and d in (s0, last)) for i, d in enumerate(days)],
        "match_weeks": [d in mset for d in days], "test_weeks": [d in tests for d in days], "sections": sections,
        "loading": {"Volume": [x[0] for x in load], "Intensity": [x[1] for x in load], "Load": [x[2] for x in load]},
        "generated_on": g["generated_on"], "notes": notes, "assumed_matches": bool(assumed),
        "short": short if draw_daily is None else draw_daily, "tournament": short,
        "age_group": g["age_group"], "week_of_day": wk,
    }
