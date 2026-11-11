"""The Excel template the admin fills in for the SLC U15 SOP tests: one sheet per level, one row per player (pre-filled with the
system's player ID and name), three trial columns per test. Text is stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

from .test_battery import ANTHRO, LEVEL_LABEL, LEVELS, TRIALS, WINDOW_LABEL, format_mmss, tests_for
from .test_import import META_SHEET, SHEET_OF, columns

NAVY, LIGHT, LOCKED = "002060", "DDEBF7", "F2F2F2"


def _s(ws, r, c, v, **kw):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"                    # never a formula
    if kw.get("fill"):
        cell.fill = PatternFill("solid", fgColor=kw["fill"])
    cell.font = Font(name="Calibri", size=11, bold=kw.get("bold", False), color="FFFFFF" if kw.get("white") else None)
    if kw.get("wrap"):
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    return cell


def build_template(*, squad: dict, season: dict, window: str, players: list[dict]) -> bytes:
    """squad {id, name}; season {id, name}; window one of test_battery.WINDOWS; players [{id, name}] (active players of the squad)."""
    wb = Workbook()
    ins = wb.active
    ins.title = META_SHEET
    ins.column_dimensions["A"].width = 26
    ins.column_dimensions["B"].width = 100
    rows = [("squad_id", squad["id"]), ("season_id", season["id"]), ("window", window),
            ("Squad", squad["name"]), ("Season", season["name"]), ("Test window", WINDOW_LABEL[window])]
    for i, (k, v) in enumerate(rows, 1):
        _s(ins, i, 1, k, bold=True)
        _s(ins, i, 2, v)
    help_lines = [
        "SLC National U15 Physical Testing. Fill the sheet for each level; leave a player's row blank if they were not tested at that level.",
        "Do not change the Player ID or name columns, the header row, or the first six rows of this sheet. Rows are matched by Player ID.",
        "Medical clearance is required before testing. Enter Yes in the Cleared column. A row marked No is rejected.",
        "Enter up to three trials for each test. The system picks the best valid trial (lowest time, highest reps or distance) and keeps all trials.",
        "Never estimate a missing result: leave the cell blank.",
        "Results use two decimals. Times in minutes are mm.ss, so 8.25 means 8 minutes 25 seconds. The part after the dot is seconds (00 to 59): 8.75 is rejected.",
        "Bronco is for Provincial players, the 2 km run for Super Provincial players. They are different tests and are not compared with each other.",
        "Record the push-up and inverted-row set-up (depth, bar height) in the set-up column. The national protocol fixes these details.",
        "Height and body weight are recorded for every player. They are not ranked.",
        "Results are confidential and are shared only with authorised staff.",
        "Plausible ranges (to catch typing errors, not standards):",
    ]
    for i, t in enumerate(help_lines, 8):
        _s(ins, i, 1, t)
    r = 8 + len(help_lines)
    for lv in LEVELS:
        for t in tests_for(lv):
            lo, hi = (format_mmss(t.lo), format_mmss(t.hi)) if t.kind == "mmss" else (t.lo, t.hi)
            _s(ins, r, 1, f"{LEVEL_LABEL[lv]}: {t.label}")
            _s(ins, r, 2, f"{lo} to {hi} {t.unit}")
            r += 1
    for key, (lab, unit, lo, hi) in ANTHRO.items():
        _s(ins, r, 1, lab)
        _s(ins, r, 2, f"{lo} to {hi} {unit}")
        r += 1

    for lv in LEVELS:
        ws = wb.create_sheet(SHEET_OF[lv])
        cols = columns(lv)
        for c, h in enumerate(cols, 1):
            _s(ws, 1, c, h, fill=NAVY, white=True, bold=True, wrap=True)
            ws.column_dimensions[L(c)].width = 30 if c == 2 else (14 if c > 2 else 11)
        ws.row_dimensions[1].height = 48
        yes_no = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
        ws.add_data_validation(yes_no)
        for i, p in enumerate(players, 2):
            _s(ws, i, 1, p["id"], fill=LOCKED)
            _s(ws, i, 2, p["name"], fill=LOCKED)
            yes_no.add(ws.cell(row=i, column=3))
            for c in range(3, len(cols) + 1):
                ws.cell(row=i, column=c).fill = PatternFill("solid", fgColor=LIGHT)
            ws.cell(row=i, column=4).number_format = "yyyy-mm-dd"
            for c, h in enumerate(cols, 1):
                if "(mm.ss)" in h or "(s)" in h or "(cm)" in h or "(kg)" in h:
                    ws.cell(row=i, column=c).number_format = "0.00"
        ws.freeze_panes = "C2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
