"""The whole seasonal plan as one workbook, laid out like the supplied rugby workbook:
   Annual plan | Load distribution | Component distribution | one Session plan sheet per player role and season phase.
Text is always stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.properties import PageSetupProperties

from .annual_grid import PHASE_LABEL as GRID_PHASE_LABEL, SEASON_PHASE_OF
from .annual_grid_excel import CENTER, R_DATE, R_MACRO, R_MESO, R_PCT, R_PERIOD, R_PHASE, _txt, write_annual_sheet, write_header
from .component_distribution import COLUMNS, build_components
from .load_distribution import SHUTTLE_SETS, SPRINT_M, build_daily_loads, build_loads
from .session_plans import ROLE_LABEL, build_day_session, build_session

_thin = Side(style="thin", color="000000")
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
BLUE, LIGHT = "2E75B6", "DDEBF7"
ROLE_SHORT = {"fast_bowler": "Fast", "spin_bowler": "Spin", "batter": "Batter", "bat_wicketkeeper": "Bat-WK", "all_rounder": "All-rounder"}
PHASE_SHORT = {"pre_season": "Pre-season", "pre_competition": "Pre-comp", "in_season": "In-season", "transition": "Transition"}
SEASON_PHASE_ORDER = ["pre_season", "pre_competition", "in_season", "transition"]


def _box(ws, r1, r2, c1, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).border = BOX


def _landscape(ws, fit_height=0):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, fit_height
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


# ───────────── load distribution ─────────────
def write_daily_load_sheet(ws, g: dict) -> None:
    d = g["daily"]
    ld = build_daily_loads(g)
    n = d["weeks"]
    linked = "Annual plan" if ws.parent and "Annual plan" in ws.parent.sheetnames else None
    write_header(ws, d, "Session(Percentage)", pct_from=linked)   # one load row: this sheet shows the Annual plan's by formula
    for c in range(2, n + 2):
        ws.column_dimensions[L(c)].width = 9.5
    _txt(ws, 11, 1, "Day")
    for i, k in enumerate(d["day_kinds"]):
        _txt(ws, 11, i + 2, k, align=Alignment(horizontal="center", vertical="center", wrap_text=True))
    ws.row_dimensions[11].height = 30
    # Runs are stored as NUMBERS (the format shows "20m*6"), so the totals can be real formulas, not typed sums.
    rows = [
        (13, "Sprint 20 m - effort (% of max)", ld["effort"], "0%"),
        (14, "Running conditioning", None, None),
        (15, "Sprint 20 m (runs)", ld["sprint_reps"], f'"{SPRINT_M}m*"0'),
        (17, f"Shuttle runs 20 m (runs*{SHUTTLE_SETS} sets)", ld["shuttle_reps"], f'"{SPRINT_M}m*"0"*{SHUTTLE_SETS}"'),
        (19, "Easy aerobic run", ld["aerobic_min"], '0" min"'),
        (25, "Bowling load (all bowlers)", None, None),
        (26, "Match", ["Match" if v else None for v in ld["matches"]], None),
        (27, "Training overs (bowling day)", ld["overs"], None),
        (28, "Spells (overs)", ld["spells"], None),
    ]
    for r, label, vals, fmt in rows:
        _txt(ws, r, 1, label, bold=vals is None)
        for i in range(n if vals else 0):
            if vals[i] is not None:
                _txt(ws, r, i + 2, vals[i], align=CENTER, fmt=fmt)

    def formula(r, c, f, fmt=None):
        cell = _txt(ws, r, c, f, align=CENTER, fmt=fmt, bold=True)
        cell.data_type = "f"

    _txt(ws, 22, 1, "Total meter (sprints + shuttles)")
    for i in range(n):
        if ld["metres"][i]:
            c = L(i + 2)
            formula(22, i + 2, f"=N({c}15)*{SPRINT_M}+N({c}17)*{SPRINT_M * SHUTTLE_SETS}", '0"m"')
    _txt(ws, 29, 1, "Training overs this week")
    for i in range(n):
        if ld["week_overs"][i]:
            first = d["week_of_day"].index(d["week_of_day"][i])          # first day of that week
            formula(29, i + 2, f"=SUM({L(first + 2)}27:{L(i + 2)}27)")
    if ws.parent is not None:
        ws.parent.calculation.fullCalcOnLoad = True                     # Excel works the formulas out when the file opens
    _box(ws, 4, 29, 1, n + 1)
    _txt(ws, 32, 1, "Notes", bold=True)
    notes = ld["notes"] + ["Session(Percentage) is the Annual plan's Percentage row (a formula), so the two sheets always agree. "
                           "Total meter and Training overs this week are formulas: change a run or an over and they update."]
    for i, line in enumerate(notes, 1):
        _txt(ws, 32 + i, 1, line)
    ws.freeze_panes = "B1"
    _landscape(ws)


def write_load_sheet(ws, g: dict) -> None:
    if g.get("daily"):
        return write_daily_load_sheet(ws, g)
    ld = build_loads(g)
    n = g["weeks"]
    last = n + 1
    write_header(ws, g, "Session(Percentage)")
    rows = [
        (12, "Sprint 20 m - effort (% of max)", ld["effort"], "0%"),
        (13, "Repeat-sprint conditioning", None, None),
        (15, "Sprint 20 m (runs)", [f"20m*{v}" if v else None for v in ld["sprint_reps"]], None),
        (17, "Shuttle runs 20 m (runs*sets)", [f"20m*{v}*2" if v else None for v in ld["shuttle_reps"]], None),
        (19, "Easy aerobic run", [f"{v} min" if v else None for v in ld["aerobic_min"]], None),
        (22, "Total meter (sprints + shuttles)", [f"{v}m" if v else None for v in ld["metres"]], None),
        (25, "Bowling load (all bowlers)", None, None),
        (26, "Matches in the week", [v or None for v in ld["matches"]], None),
        (27, "Training bowling days", [v if v else None for v in ld["bowl_days"]], None),
        (28, "Overs per bowling day", ld["overs_per_day"], None),
        (29, "Spells (overs)", ld["spells"], None),
        (30, "Training overs per week", ld["overs_per_week"], None),
    ]
    for r, label, vals, fmt in rows:
        _txt(ws, r, 1, label, bold=vals is None)
        for w in range(n if vals else 0):
            if vals[w] is not None:
                _txt(ws, r, w + 2, vals[w], align=CENTER, fmt=fmt)
    _box(ws, 4, 30, 1, last)
    _txt(ws, 33, 1, "Notes", bold=True)
    for i, line in enumerate(ld["notes"], 1):
        _txt(ws, 33 + i, 1, line)
    ws.freeze_panes = "B1"
    _landscape(ws)


# ───────────── component distribution ─────────────
def write_component_sheet(ws, roles: list[str], bowling: set[str] | None) -> None:
    comp = build_components(roles, bowling)
    for col, w in zip("ABCDEFGHI", (30, 38, 52, 34, 12, 12, 14, 12, 12)):
        ws.column_dimensions[col].width = w
    heads = ["Type of work", "Exercise / activity", "What it is for", "Areas improved"] + [GRID_PHASE_LABEL[p] for p in COLUMNS]
    for c, h in enumerate(heads, 1):
        _txt(ws, 4, c, h, bold=True, align=Alignment(wrap_text=True, vertical="center", horizontal="center" if c > 4 else None))
    ws.row_dimensions[4].height = 32
    r = 6
    for block in comp["blocks"]:
        _txt(ws, r, 1, block["label"], bold=True)
        r += 1
        for row in block["rows"]:
            _txt(ws, r, 1, row["type"], align=Alignment(wrap_text=True, vertical="top"))
            _txt(ws, r, 2, row["name"], align=Alignment(wrap_text=True, vertical="top"))
            _txt(ws, r, 3, row["purpose"], align=Alignment(wrap_text=True, vertical="top"))
            _txt(ws, r, 4, row["areas"], align=Alignment(wrap_text=True, vertical="top"))
            for i, on in enumerate(row["marks"]):
                if on:
                    _txt(ws, r, 5 + i, "x", align=CENTER)
            r += 1
        r += 2
    _txt(ws, r, 1, "Notes", bold=True)
    for i, line in enumerate(comp["notes"], 1):
        _txt(ws, r + i, 1, line)
    ws.freeze_panes = "E5"
    _landscape(ws)


# ───────────── session plan ─────────────
def write_session_sheet(ws, s: dict) -> None:
    for col, w in zip("ABCDEFG", (20, 52, 24, 14, 10, 24, 26)):
        ws.column_dimensions[col].width = w
    ws.merge_cells("A2:G3")
    _txt(ws, 2, 1, s["title"], align=CENTER, bold=True)
    r = 7
    for label, value in s["header"]:
        _txt(ws, r, 1, label, fill=BLUE, white=True, bold=True, align=Alignment(vertical="top"))
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
        _txt(ws, r, 2, value, fill=BLUE, white=True, align=Alignment(wrap_text=True, vertical="top"))
        if len(value) > 90:
            ws.row_dimensions[r].height = 32
        r += 1
    # table header (rows 15-16), as in the supplied sheet
    for rng in ("A15:A16", "B15:B16", "C15:E15", "F15:F16", "G15:G16"):
        ws.merge_cells(rng)
    for cell, text in (("A15", "PART"), ("B15", "DESCRIPTION"), ("C15", "DOSIFICATION"), ("F15", "ORGANIZATION"), ("G15", "REST"),
                       ("C16", "TIME"), ("D16", "REP"), ("E16", "SET")):
        c = ws[cell]
        _txt(ws, c.row, c.column, text, fill=LIGHT, bold=True, align=CENTER)
    for r_ in (15, 16):
        for c in range(1, 8):
            ws.cell(row=r_, column=c).fill = PatternFill("solid", fgColor=LIGHT)
    r = 17
    wrap = Alignment(wrap_text=True, vertical="top")
    part_label = {"initial": "INITIAL PART", "main": "MAIN PART", "final": "FINAL PART"}
    groups: dict[str, list[int]] = {}
    last_key = None
    for p in s["parts"]:
        start = r
        _txt(ws, r, 2, f"{p['name']}", bold=True, fill=LIGHT)
        _txt(ws, r, 3, f"{p['minutes']} MIN" if p["minutes"] else None, bold=True, fill=LIGHT, align=CENTER)
        for c in (4, 5, 6, 7):
            _txt(ws, r, c, None, fill=LIGHT)
        r += 1
        for it in p["items"]:
            _txt(ws, r, 2, it["desc"], fill=LIGHT, align=wrap)
            _txt(ws, r, 3, it["time"] or None, fill=LIGHT, align=Alignment(horizontal="center", vertical="top", wrap_text=True))
            _txt(ws, r, 4, it["rep"] or None, fill=LIGHT, align=Alignment(horizontal="center", vertical="top"))
            _txt(ws, r, 5, it["set"] or None, fill=LIGHT, align=Alignment(horizontal="center", vertical="top"))
            _txt(ws, r, 6, it["org"] or None, fill=LIGHT, align=wrap)
            _txt(ws, r, 7, it["rest"] or None, fill=LIGHT, align=wrap)
            if len(it["desc"]) > 55 or len(it["time"] or "") > 26:
                ws.row_dimensions[r].height = 30
            r += 1
        groups.setdefault(p["key"], []).append((start, r - 1))
    for key, spans in groups.items():                      # PART column: one merged cell per stage, as in the supplied sheet
        a, b = spans[0][0], spans[-1][1]
        _txt(ws, a, 1, part_label[key], fill=LIGHT, bold=True, align=Alignment(horizontal="center", vertical="center"))
        if b > a:
            ws.merge_cells(start_row=a, start_column=1, end_row=b, end_column=1)
    _box(ws, 15, r - 1, 1, 7)
    r += 1
    if s["notes"]:
        _txt(ws, r, 1, "Notes", bold=True)
    for note in s["notes"]:
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        _txt(ws, r, 1, note, align=Alignment(wrap_text=True, vertical="top"))
        ws.row_dimensions[r].height = 30 if len(note) > 120 else 16
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def session_sheet_name(role: str, phase: str, used: set[str]) -> str:
    base = f"{ROLE_SHORT[role]} {PHASE_SHORT[phase]}"[:31]
    name, i = base, 2
    while name in used:
        name, i = f"{base[:28]} {i}", i + 1
    used.add(name)
    return name


def season_phases_of(g: dict) -> list[str]:
    present = {SEASON_PHASE_OF[k] for k in g["kinds"]}
    return [p for p in SEASON_PHASE_ORDER if p in present]


DAY_SHORT = {"heavy": "Heavy", "medium": "Medium", "light": "Light", "practice": "Practice", "active": "Active rest", "match": "Match",
             "free": "Training", "before": "Pre-match", "after": "Recovery", "between": "Between"}
GRID_SHORT = {"general_prep": "Gen prep", "special_prep": "Spec prep", "pre_competition": "Pre-comp", "competition": "Comp", "transition": "Transition"}


def day_sessions(g: dict, roles: list[str], bowling: set[str] | None = None) -> list[tuple[str, dict]]:
    """(sheet name, session) for the Session plan sheets. A tournament: one sheet per day. A longer season: one sheet per kind of
    day in each phase (the Day row of the Annual plan says which one a date uses), from the first such day."""
    d = g["daily"]
    ld = build_daily_loads(g)
    marks = {r["label"]: r["marks"] for sec in d["sections"] for r in sec["rows"]}
    if "Explosive power" not in marks:                           # a category plan without the Technical section
        marks["Explosive power"] = marks.get("Speed", [False] * d["weeks"])
    out, seen, used = [], set(), {"Annual plan", "Load distribution", "Component distribution"}
    for i, k in enumerate(d["day_kind_keys"]):
        if k == "rest":
            continue
        key = i if d["short"] else (d["kinds"][i], k)
        if key in seen:
            continue
        seen.add(key)
        date = d["dates"][i]
        phase = SEASON_PHASE_OF[d["kinds"][i]]
        if d["short"]:
            name, title = f"Day {i + 1} {date:%a %d %b}", f"Day {i + 1} - {date:%A %d %B %Y}"
        else:
            name = f"{GRID_SHORT[d['kinds'][i]]} {DAY_SHORT[k]}"
            title = f"{GRID_PHASE_LABEL[d['kinds'][i]]} - {d['day_kinds'][i]} (first: {date:%a %d %b %Y})"
        base, j = name[:31], 2
        while base in used:
            base, j = f"{name[:28]} {j}", j + 1
        used.add(base)
        meso = next(m[2] for m in d["mesos"] if m[0] <= i <= m[1])
        micro = next(f"Micro {m[2]}" for m in d["micros"] if m[0] <= i <= m[1])
        day_marks = {lbl: v[i] for lbl, v in marks.items()}
        load = {"sprint_reps": ld["sprint_reps"][i], "shuttle_reps": ld["shuttle_reps"][i], "aerobic_min": ld["aerobic_min"][i],
                "overs": ld["overs"][i], "effort": ld["effort"][i]}
        out.append((base, build_day_session(roles, phase, k, title=title, meso=meso, micro=micro, pct=d["percentage"][i],
                                            marks=day_marks, load=load, bowling_types=bowling)))
    return out


# ───────────── the supplied workbook's own layout: four sheets, week by week ─────────────
SHEETS = ["Annual plan", "Load distribution", "Component distribution", "Session plan"]


def drawn(g: dict) -> dict:
    """The grid the sheets are drawn from: one column per week, or per day for a tournament (season under 4 weeks)."""
    return g["daily"] if g.get("daily", {}).get("short") else g


def write_interval_load_sheet(ws, g: dict, annual: str = "Annual plan") -> None:
    """The supplied "load distribution" sheet: the Annual plan's header block (its % row by formula), 100 m at a % of maximal
    speed, interval runs of 120 / 150 / 300 m written as distance*reps, and Total meter worked out by formula."""
    from .load_distribution import INTERVAL_RUNS, build_interval_loads
    extra = (g.get("player") or {}).get("extra_endurance_reps", 0)
    g = drawn(g)
    ld = build_interval_loads(g, extra)
    n = g["weeks"]
    linked = annual if ws.parent and annual in ws.parent.sheetnames else None
    write_header(ws, g, "Session(Percentage)", pct_from=linked)
    _txt(ws, 12, 1, "100m")
    _txt(ws, 13, 1, "Anaerobic endurance(speed)")
    row_of = {120: 15, 150: 17, 300: 19}
    for m in INTERVAL_RUNS:
        _txt(ws, row_of[m], 1, f"Interval run {m}m")
    _txt(ws, 22, 1, "Total meter")
    for w in range(n):
        c = w + 2
        if ld["speed_100m"][w]:
            _txt(ws, 12, c, ld["speed_100m"][w], align=CENTER, fmt="0%")
        for m in INTERVAL_RUNS:
            if ld["runs"][m][w]:
                _txt(ws, row_of[m], c, ld["runs"][m][w], align=CENTER, fmt=f'"{m}m*"0')   # a number, shown as 120m*8
        if ld["total"][w]:
            col = L(c)
            cell = _txt(ws, 22, c, "=" + "+".join(f"N({col}{row_of[m]})*{m}" for m in INTERVAL_RUNS), align=CENTER, fmt='0"m"')
            cell.data_type = "f"
    _box(ws, 4, 23, 1, n + 1)
    ws.freeze_panes = "B1"
    if ws.parent is not None:
        ws.parent.calculation.fullCalcOnLoad = True
    _landscape(ws)


# (quality, method, phases) - the supplied "Example component distribution" table
CLASSIC_COMPONENTS = [
    ("Aerobic endurance", [("Continue slow run", "GT"), ("Fartlek", "GT"), ("Tempo run", "SP"), ("Steady state run", "SPC"),
                           ("Hill run", "GT"), ("Beach run", "GT"), ("Games", "SP"), ("Long interval run", "SP")]),
    ("Anaerobic endurance", [("Speed games", ""), ("50m interval", "PC"), ("100m interval", "SC"), ("200m interval", "PC"),
                             ("300m interval", "S"), ("400m interval", "GSP")]),
    ("Alactic endurance", [("30m", "SPC"), ("40m", "SPC"), ("50m", "PC"), ("60m", "SPC"), ("80m", "SPC"), ("100m", "SPC"), ("120m", "GSP")]),
]
CLASSIC_PHASES = [("G", "General"), ("S", "Special"), ("P", "Precompetition"), ("C", "Competition"), ("T", "Transition")]


def write_classic_component_sheet(ws) -> None:
    """The supplied component distribution: an Excel table, quality and method in A-B, an x under each phase that uses it."""
    from openpyxl.worksheet.table import Table, TableStyleInfo
    heads = ["Quality", "Method"] + [label for _, label in CLASSIC_PHASES]
    for c, (h, w) in enumerate(zip(heads, (22, 20, 13, 13, 15, 13, 13)), 1):
        _txt(ws, 1, c, h, bold=True)
        ws.column_dimensions[L(c)].width = w
    r = 3
    for quality, methods in CLASSIC_COMPONENTS:
        _txt(ws, r, 1, quality)
        for name, phases in methods:
            _txt(ws, r, 2, name)
            for i, (code, _) in enumerate(CLASSIC_PHASES):
                if code in phases:
                    _txt(ws, r, 3 + i, "x", align=CENTER)
            r += 1
        r += 2                                                   # blank rows between the groups, as on the sheet
    table = Table(displayName="ComponentDistribution", ref=f"A1:{L(len(heads))}{r - 2}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)


def write_classic_session_sheet(ws, g: dict) -> None:
    from .session_plans import classic_session
    ses = classic_session()
    if g.get("player"):
        ses["header"][0] = ("TOPIC", f"Monday session plan - {g['player']['name']}")
    write_session_sheet(ws, ses)


def build_seasonal_workbook(g: dict, roles: list[str] | None = None, bowling: set[str] | None = None) -> bytes:
    """The seasonal plan exactly as the supplied workbook: Annual plan | Load distribution | Component distribution | Session plan.
    One column per week (per day for a tournament). g may be the squad grid or a player's (player_season_plan.personal_grid)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Annual plan"
    write_annual_sheet(ws, g, notes=False)
    write_interval_load_sheet(wb.create_sheet("Load distribution"), g)
    write_classic_component_sheet(wb.create_sheet("Component distribution"))
    write_classic_session_sheet(wb.create_sheet("Session plan"), g)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def player_sheet_name(name: str, squad_no: int | None, used: set[str]) -> str:
    bad = set("[]:*?/\\")                                       # characters Excel refuses in a sheet name
    clean = "".join(ch for ch in name if ch not in bad).strip() or "Player"
    base = (f"{squad_no} {clean}" if squad_no is not None else clean)[:31]
    out, i = base, 2
    while out in used:
        out, i = f"{base[:28]} {i}", i + 1
    used.add(out)
    return out


def build_players_workbook(squad_grid: dict, players: list[tuple[str, dict]]) -> bytes:
    """Every player's plan in ONE Excel: one Annual-plan sheet per player (named after the player), then the squad's Load
    distribution, Component distribution and Session plan. players: [(sheet name, personal grid)]."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, pg in players:
        write_annual_sheet(wb.create_sheet(name), pg, notes=False)
    if not players:
        write_annual_sheet(wb.create_sheet("Annual plan"), squad_grid, notes=False)
    first = wb.sheetnames[0]
    write_interval_load_sheet(wb.create_sheet("Load distribution"), squad_grid, annual=first)
    write_classic_component_sheet(wb.create_sheet("Component distribution"))
    write_classic_session_sheet(wb.create_sheet("Session plan"), squad_grid)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
