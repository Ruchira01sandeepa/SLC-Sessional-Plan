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

from .age_groups import profile as age_profile

# The five columns-of-meaning on the sheet's "Phases" row. Our season has four phases; the preparation phase is split
# into general and special preparation like the supplied sheet.
GENERAL, SPECIAL, PRECOMP, COMP, TRANS = "general_prep", "special_prep", "pre_competition", "competition", "transition"
PHASE_LABEL = {GENERAL: "General preparation", SPECIAL: "Special preparation", PRECOMP: "Pre-competition",
               COMP: "Competition", TRANS: "Transition"}
PERIOD_OF = {GENERAL: "Preparation", SPECIAL: "Preparation", PRECOMP: "Competition", COMP: "Competition", TRANS: "Transition"}
GENERAL_SHARE = 0.60            # of the pre-season weeks; the rest is special preparation
MACRO_WEEKS = {GENERAL: 4, SPECIAL: 3, PRECOMP: 2, COMP: 3, TRANS: 2}
PEAK = 0.90                     # U15 default; the supplied sheet peaks at 97%. Each age group sets its own (app/age_groups.py)
START = 0.25
RECOVERY_FACTOR = 0.70          # the last week of a preparation block is lighter (the sheet does the same: 40% -> 28%)
LEVELS = {                      # percentage at the first and last week of the phase, for phases without a ramp
    PRECOMP: (0.70, 0.62), COMP: (0.50, 0.45), TRANS: (0.40, 0.30),
}
LOADING = {                     # (volume, intensity, load), as on the supplied sheet
    GENERAL: ("High", "low", "High"), SPECIAL: ("High", "low", "Medium"), PRECOMP: ("Medium", "Medium", "low"),
    COMP: ("low", "High", "low"), TRANS: ("low", "low", "low"),
}

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
    "Nutrition": [(n, {_G: "all", _S: "all", _P: "all", _C: "all", _T: "all"})
                  for n in ("Carbohydrate", "Fat", "Protein", "Vitamin", "Minerals", "Electrolytes")],
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


def build_grid(*, squad_name: str, season: dict, phases: list[dict], events: list[dict], generated_on: date, age_group: str | None = None) -> dict:
    """season: {name, start_date, end_date}. phases: [{phase_type, start_date, end_date}] using the season phase names
    (pre_season, pre_competition, in_season, transition). events: [{event_type, date, hours|None}]."""
    s0, e0 = season["start_date"], season["end_date"]
    prof = age_profile(age_group)
    peak = prof.load_peak
    if (e0 - s0).days + 1 < 28:
        raise ValueError("A season shorter than 4 weeks cannot be shown as an annual plan")
    if not phases:
        raise ValueError("The season has no phases")
    phases = sorted(phases, key=lambda p: p["start_date"])
    n = _weeks(s0, e0)
    starts = [s0 + timedelta(days=7 * i) for i in range(n)]

    # --- which phase is each week in (general / special preparation split inside pre-season) ---
    base = [_phase_for(d, phases)["phase_type"] for d in starts]
    pre_idx = [i for i, t in enumerate(base) if t == "pre_season"]
    m = len(pre_idx)
    n_gen = m if m <= 1 else max(1, min(m - 1, round(m * GENERAL_SHARE)))
    kind = []
    for i, t in enumerate(base):
        if t == "pre_season":
            kind.append(GENERAL if pre_idx.index(i) < n_gen else SPECIAL)
        else:
            kind.append({"pre_competition": PRECOMP, "in_season": COMP, "transition": TRANS}[t])

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
    for k, w in enumerate(loading_weeks):
        pct[w] = round(START + (peak - START) * (k / (len(loading_weeks) - 1) if len(loading_weeks) > 1 else 0), 2)
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
    if not tests:                                               # same suggested times as the seasonal plan's testing schedule
        tests_source = "suggested"
        mid_ph = next((p for p in phases if p["phase_type"] == "in_season"), None)
        mid = (mid_ph["start_date"] + (mid_ph["end_date"] - mid_ph["start_date"]) / 2) if mid_ph else s0 + (e0 - s0) / 2
        tests = {0, week_of(mid), n - 1} - {None}

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
    return {
        "title": f"ANNUAL PLAN FOR {squad_name.upper()} ({season['name']})",
        "squad": squad_name, "season": season["name"], "weeks": n, "week_starts": starts, "age_group": prof.code,
        "periods": [(a, b, v) for a, b, v in runs([PERIOD_OF[k] for k in kind])],
        "phases": [(a, b, v) for a, b, v in runs(kind)],
        "mesos": mesos,
        "macros": [(a, b, num) for num, (a, b, _) in enumerate(blocks, 1)],
        "days": [d.day for d in starts], "percentage": pct, "hours": [round(h, 1) if h else None for h in hours],
        "match_weeks": [w in matches for w in range(n)], "match_counts": match_n, "test_weeks": [w in tests for w in range(n)], "tests_source": tests_source,
        "recovery_weeks": recovery, "kinds": kind, "sections": sections,
        "loading": {"Volume": [LOADING[k][0] for k in kind], "Intensity": [LOADING[k][1] for k in kind], "Load": [LOADING[k][2] for k in kind]},
        "generated_on": generated_on,
        "notes": [
            "Weeks start on the season's start date and run in blocks of seven days. The Dates row shows the day of the month each week starts on.",
            f"Percentage is the planned relative training load, not a measurement. Preparation builds from {int(START * 100)}% to {int(peak * 100)}% with a lighter week at the end of each block; "
            f"the supplied rugby sheet peaks higher, so this is lower for {prof.code} players. Coaches adjust it.",
            "A '*' marks a week in which that area is trained. The marks are a proposal for the coaches to confirm and follow the exercise-to-phase mapping used in the seasonal plan.",
            ("Test weeks are the fitness-test events in the calendar." if tests_source == "calendar"
             else "Test weeks are SUGGESTED (first week, middle of the in-season phase, last week) because no fitness-test events are in the calendar."),
            "Medical and Field are marked in every test week. Lab is left empty because the system does not schedule laboratory tests.",
            "Competition marks the weeks with a match in the calendar. Week hours add up the training and match hours in the calendar (blank when none have an end time).",
            "Volume, Intensity and Load follow the supplied sheet's pattern for each phase. They are guidance, not a prescription for any one player.",
        ],
    }
