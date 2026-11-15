"""The periodized S&C seasonal plan as a workbook: Macrocycle (weeks as columns, like an annual plan), Mesocycles, Rules.
Text is stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

BLUE, GREY = "1F4E79", "F2F2F2"
FILL = {"accumulation": "C6E0B4", "transmutation": "FFE699", "realization": "F8CBAD", "competition": "BDD7EE", "transition": "D9D9D9"}
THIN = Side(style="thin", color="BFBFBF")


def _s(ws, r, c, v, *, bold=False, fill=None, white=False, wrap=False, center=False):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"
    cell.font = Font(name="Calibri", size=10, bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(wrap_text=wrap, vertical="center" if center else "top", horizontal="center" if center else None)
    cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    return cell


def build_sc_season_workbook(squad: str, p: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Macrocycle"
    wk = p["weeks"]
    _s(ws, 1, 1, f"S&C SEASONAL PLAN (PERIODIZED) - {squad} - {p['season']['name']}", bold=True)
    _s(ws, 2, 1, p["source"])
    rows = [("Week", lambda w: w["week"]), ("Starts", lambda w: w["start"].strftime("%d %b")),
            ("Period", lambda w: w["period"]), ("Mesocycle", lambda w: f"{w['mesocycle']} {w['meso_label']}"),
            ("Microcycle", lambda w: w["microcycle"]), ("Volume (%)", lambda w: w["volume"]),
            ("Workout load", lambda w: w["intensity"]), ("S&C sessions", lambda w: w["sessions"]),
            ("Matches", lambda w: w["matches"] or ""), ("Targets", lambda w: " + ".join(w["targets"]))]
    for i, (label, fn) in enumerate(rows):
        r = 4 + i
        _s(ws, r, 1, label, bold=True, fill=BLUE, white=True)
        for j, w in enumerate(wk):
            _s(ws, r, 2 + j, fn(w), fill=FILL[w["meso_type"]] if label in ("Period", "Mesocycle", "Microcycle") else None, wrap=True, center=True)
    r = 4 + len(rows)                                            # a simple volume bar row
    _s(ws, r, 1, "Volume bar", bold=True, fill=BLUE, white=True)
    for j, w in enumerate(wk):
        _s(ws, r, 2 + j, "|" * max(1, w["volume"] // 10), center=True)
    ws.column_dimensions["A"].width = 16
    for j in range(len(wk)):
        ws.column_dimensions[L(2 + j)].width = 15
    for rr in range(4, r + 1):
        ws.row_dimensions[rr].height = 42 if rr in (6, 7, 8, 10, 13) else 18
    ws.freeze_panes = "B4"
    n = r + 2
    for note in p["notes"]:
        _s(ws, n, 1, note)
        n += 1

    ws = wb.create_sheet("Mesocycles")
    r = 1
    for m in p["mesocycles"]:
        _s(ws, r, 1, f"{m['label']} - {m['start']:%d %b} to {m['end']:%d %b %Y} ({m['weeks']} week{'s' if m['weeks'] != 1 else ''})", bold=True, fill=FILL[m["type"]])
        r += 1
        for k, v in (("Targets", ", ".join(f"{t['label']} ({t['share']})" for t in m["targets"]) or "-"), ("Retained", ", ".join(m["retained"]) or "-"),
                     ("Method", m["method"]), ("Dose", m["dose"]), ("Rest", m["rest"]), ("Frequency", m["frequency"]),
                     ("Session length", m["minutes"] + " min"), ("Workout load", m["intensity"])):
            _s(ws, r, 1, k, bold=True)
            _s(ws, r, 2, v, wrap=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
            r += 1
        for i, h in enumerate(["Order", "Exercise", "Area", "Role", "Sets", "Reps / time"], 1):
            _s(ws, r, i, h, bold=True, fill=BLUE, white=True)
        for i, e in enumerate(m["complex"], 1):
            r += 1
            for c, v in enumerate([i, e["name"], e["area_label"], e["role"], e.get("set") or "", e.get("rep") or e.get("time") or ""], 1):
                _s(ws, r, c, v, wrap=c == 2)
        r += 1
        _s(ws, r, 1, "Week", bold=True, fill=GREY)
        r += 1
        for d in m["microcycle"]:
            _s(ws, r, 1, d["day"])
            _s(ws, r, 2, d["session"], wrap=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
            r += 1
        r += 1
    for col, w in zip("ABCDEF", (16, 46, 22, 10, 8, 18)):
        ws.column_dimensions[col].width = w

    ws = wb.create_sheet("Rules")
    _s(ws, 1, 1, "Session order", bold=True)
    for i, t in enumerate(p["session_order"], 2):
        _s(ws, i, 1, f"{i - 1}. {t}")
    r = len(p["session_order"]) + 3
    _s(ws, r, 1, "Rules", bold=True)
    for t in p["rules"]:
        r += 1
        _s(ws, r, 1, t)
    ws.column_dimensions["A"].width = 110
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
