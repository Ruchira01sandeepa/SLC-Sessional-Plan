"""Draws the annual plan grid (annual_grid.build_grid) as one Excel sheet laid out like the supplied
"ANNUAL PLAN FOR U-16 RUGBY TEAM" sheet: same rows in the same places, same bands and colours.

Row map (as in the supplied sheet): 2 title, 4 Periods, 5 Phases, 6 Mesos, 7 Macros, 8 Micros, 9 Dates, 10 Percentage,
11 week hours, 12 Competition band, 14 Test band (15-17), 19 Physical (20-24), 26 Mental (27-32), 34 Technical (35-40),
42 Tactical (43-45), 47 Nutrition (48-53), 56 Loading index (57-59), 60 Performance index. Week columns start at B.
Text is stored as text, never as a formula.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.properties import PageSetupProperties

from app.planning.annual_grid import PHASE_LABEL

NAVY, PERIOD_GREY = "002060", "D0CECE"
PHASE_FILL = {"general_prep": "FFF2CC", "special_prep": "FFE699", "pre_competition": "FFD966", "competition": "BF9000", "transition": "FFD966"}
MONTH_FILL = {1: "D9D9D9", 2: "595959", 3: "ADB9CA", 4: "8FAADC", 5: "F8CBAD", 6: "BDD7EE", 7: "C5E0B4", 8: "A9D18E", 9: "548235",
              10: "F4B183", 11: "FFE699", 12: "B4C6E7"}
DARK = {"595959", "548235", "BF9000"}                      # fills that need white text
CENTER = Alignment(horizontal="center", vertical="center")

# fixed rows, copied from the supplied sheet
R_TITLE, R_PERIOD, R_PHASE, R_MESO, R_MACRO, R_MICRO, R_DATE, R_PCT, R_HOURS, R_COMP = 2, 4, 5, 6, 7, 8, 9, 10, 11, 12
R_TEST, R_SECTION = 14, {"Physical": 19, "Mental": 26, "Technical": 34, "Tactical": 42, "Nutrition": 47}
R_LOADING_HEAD, R_PERF, R_NOTES = 56, 60, 63


def _txt(ws, r, c, v, *, fill=None, white=False, align=None, bold=False, fmt=None):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.font = Font(name="Calibri", size=11, color="FFFFFF" if white else None, bold=bold)
    if align:
        cell.alignment = align
    if fmt:
        cell.number_format = fmt
    return cell


def _band(ws, r, last_col, label, marks=None):
    """A navy band across the week columns, with its label in column A. `marks` puts a white * in the weeks given."""
    _txt(ws, r, 1, label)
    for c in range(2, last_col + 1):
        _txt(ws, r, c, "*" if marks and marks[c - 2] else None, fill=NAVY, white=True, align=CENTER)


def _span(ws, r, a, b, text, fill, white=False):
    """Weeks a..b (0-based) merged into one coloured cell. Style the first cell, then merge; the others show its fill."""
    _txt(ws, r, a + 2, text, fill=fill, white=white, align=CENTER)
    if b > a:
        ws.merge_cells(start_row=r, start_column=a + 2, end_row=r, end_column=b + 2)


def write_header(ws, g: dict, pct_label: str = "Percentage", pct_from: str | None = None) -> None:
    """Rows 4 to 10 of the supplied sheets (Periods ... Percentage). The same block heads the annual plan and the load sheet.
    pct_from: the sheet whose Percentage row this one shows, by formula, so the two sheets can never disagree."""
    n = g["weeks"]
    ws.column_dimensions["A"].width = 30
    for c in range(2, n + 2):
        ws.column_dimensions[L(c)].width = 8.7
    for r, label in ((R_PERIOD, "Periods"), (R_PHASE, "Phases"), (R_MESO, "Mesos"), (R_MACRO, "Macros"), (R_MICRO, "Micros"),
                     (R_DATE, "Dates"), (R_PCT, pct_label)):
        _txt(ws, r, 1, label)
    for a, b, name in g["periods"]:
        _span(ws, R_PERIOD, a, b, name, PERIOD_GREY)
    for a, b, k in g["phases"]:
        _span(ws, R_PHASE, a, b, PHASE_LABEL[k], PHASE_FILL[k], white=PHASE_FILL[k] in DARK)
    for a, b, name, month in g["mesos"]:
        _span(ws, R_MESO, a, b, name, MONTH_FILL[month], white=MONTH_FILL[month] in DARK)
    for a, b, num in g["macros"]:
        _span(ws, R_MACRO, a, b, num, None)
    if g.get("micros"):                                         # day-by-day sheet: a micro spans its 7 days
        for a, b, num in g["micros"]:
            _span(ws, R_MICRO, a, b, num, None)
    for w in range(n):
        c = w + 2
        if not g.get("micros"):
            _txt(ws, R_MICRO, c, w + 1, align=CENTER)
        _txt(ws, R_DATE, c, f"{g['weekdays'][w]} {g['days'][w]}" if g.get("weekdays") else g["days"][w], align=CENTER)
        _txt(ws, R_PCT, c, f"='{pct_from}'!{L(c)}{R_PCT}" if pct_from else g["percentage"][w], align=CENTER, fmt="0%")
        if pct_from:
            ws.cell(row=R_PCT, column=c).data_type = "f"


def layout(g: dict) -> tuple[dict[str, int], int, int, int]:
    """Header row of each section, then the loading index, performance index and notes rows. Uses the supplied sheet's rows
    when the content fits (it does for the standard rows) and pushes later blocks down when a section grows, so blocks never overlap."""
    heads, nxt = {}, R_SECTION["Physical"]
    for sec in g["sections"]:
        start = max(R_SECTION.get(sec["name"], nxt), nxt)
        heads[sec["name"]] = start
        nxt = start + len(sec["rows"]) + 2                      # header + rows + one blank row
    loading = max(R_LOADING_HEAD, nxt + 1)
    perf = loading + (R_PERF - R_LOADING_HEAD)
    return heads, loading, perf, perf + (R_NOTES - R_PERF)


def write_annual_sheet(ws, g: dict, notes: bool = True) -> None:
    if g.get("daily", {}).get("short"):                         # a tournament (season under 4 weeks) is drawn day by day
        g = g["daily"]                                          # every other season: one column per week, like the supplied sheet
    n = g["weeks"]
    heads, r_loading, r_perf, r_notes = layout(g)
    last = n + 1
    ws.merge_cells(start_row=R_TITLE, start_column=1, end_row=R_TITLE, end_column=last)
    _txt(ws, R_TITLE, 1, g["title"], align=CENTER, bold=True)
    write_header(ws, g)
    _txt(ws, R_HOURS, 1, g.get("hours_label", "week hours"))
    for w in range(n):
        _txt(ws, R_HOURS, w + 2, g["hours"][w], align=CENTER, fmt="0.0")

    _band(ws, R_COMP, last, "Competition", g["match_weeks"])
    if g.get("day_kinds") and notes:                            # what kind of tournament day it is (not in the supplied structure)
        _txt(ws, R_COMP + 1, 1, "Day")
        for w, k in enumerate(g["day_kinds"]):
            _txt(ws, R_COMP + 1, w + 2, k, align=Alignment(horizontal="center", vertical="center", wrap_text=True))
        ws.row_dimensions[R_COMP + 1].height = 30
    _band(ws, R_TEST, last, "Test")
    for r, label in zip((15, 16, 17), ("Medical", "Lab", "Field")):
        _txt(ws, r, 1, label)
        marks = g.get("medical_days") if label == "Medical" and g.get("medical_days") else g["test_weeks"]
        if label != "Lab":
            for w in range(n):
                if marks[w]:
                    _txt(ws, r, w + 2, "*", align=CENTER)

    for sec in g["sections"]:
        head = heads[sec["name"]]
        _band(ws, head, last, sec["name"])
        for i, row in enumerate(sec["rows"], 1):
            _txt(ws, head + i, 1, row["label"])
            for w, on in enumerate(row["marks"]):
                if on:
                    _txt(ws, head + i, w + 2, "*", align=CENTER)

    _txt(ws, r_loading, 1, "Loading index")
    for i, name in enumerate(("Volume", "Intensity", "Load"), 1):
        _txt(ws, r_loading + i, 1, name)
        for w in range(n):
            _txt(ws, r_loading + i, w + 2, g["loading"][name][w], align=CENTER)
    _txt(ws, r_perf, 1, "Performance index")
    perf = g.get("performance") or ["results" if t else None for t in g["test_weeks"]]   # a player's plan shows their own result
    for w in range(n):
        if perf[w]:
            _txt(ws, r_perf, w + 2, perf[w], align=CENTER)

    if not notes:                                               # the supplied sheet ends at Performance index
        _finish(ws)
        return
    _txt(ws, r_notes, 1, "Notes", bold=True)
    notes = g["notes"] + ["Performance index: enter each test's results in the test columns (Physical > Re-test & progress keeps them)."]
    for i, line in enumerate(notes, 1):
        _txt(ws, r_notes + i, 1, line)
    _txt(ws, r_notes + len(g["notes"]) + 2, 1, f"Generated on {g['generated_on'].strftime('%d %b %Y')}. A proposal for the coaches to review.")

    _finish(ws)


def _finish(ws) -> None:
    ws.freeze_panes = "B1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_cols = "A:A"


def build_grid_workbook(g: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Annual plan"
    write_annual_sheet(ws, g)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
