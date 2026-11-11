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
from .load_distribution import build_loads
from .session_plans import ROLE_LABEL, build_session

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
def write_load_sheet(ws, g: dict) -> None:
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
    for cell, text in (("A15", "PART"), ("B15", "DESCRIPTION"), ("C15", "DOSAGE"), ("F15", "ORGANIZATION"), ("G15", "REST"),
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
        _txt(ws, r, 3, f"{p['minutes']} MIN", bold=True, fill=LIGHT, align=CENTER)
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


def build_seasonal_workbook(g: dict, roles: list[str], bowling: set[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Annual plan"
    write_annual_sheet(ws, g)
    write_load_sheet(wb.create_sheet("Load distribution"), g)
    write_component_sheet(wb.create_sheet("Component distribution"), roles, bowling)
    used = {"Annual plan", "Load distribution", "Component distribution"}
    for role in roles:
        for phase in season_phases_of(g):
            write_session_sheet(wb.create_sheet(session_sheet_name(role, phase, used)), build_session(role, phase, bowling))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
