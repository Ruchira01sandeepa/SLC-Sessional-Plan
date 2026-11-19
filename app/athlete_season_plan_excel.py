"""The 16-step athlete seasonal plan as a workbook, in the STEP 15 output order. Text is stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

BLUE = "1F4E79"
FILL = {"accumulation": "C6E0B4", "transmutation": "FFE699", "realization": "F8CBAD", "competition": "BDD7EE", "transition": "D9D9D9"}
OKF = {True: "C6EFCE", False: "FFC7CE", None: "FFEB9C"}
THIN = Side(style="thin", color="BFBFBF")


def _s(ws, r, c, v, *, bold=False, fill=None, white=False, wrap=True):
    cell = ws.cell(row=r, column=c)
    cell.value = v.strftime("%d %b %Y") if hasattr(v, "strftime") else v
    if isinstance(cell.value, str):
        cell.data_type = "s"
    cell.font = Font(name="Calibri", size=10, bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    return cell


def _head(ws, r, cols):
    for i, h in enumerate(cols, 1):
        _s(ws, r, i, h, bold=True, fill=BLUE, white=True)


def _widths(ws, ws_):
    for i, w in enumerate(ws_, 1):
        ws.column_dimensions[chr(64 + i)].width = w


def build_athlete_workbook(p: dict) -> bytes:
    wb = Workbook()
    who = f"{p['player']['name']} - {p['season']['name']}"

    # 1. inputs + assumptions
    ws = wb.active
    ws.title = "1 Inputs"
    _s(ws, 1, 1, f"SEASONAL PLAN (16 STEPS) - {who}", bold=True)
    _s(ws, 2, 1, p["source"] + ". Every number is a proposal for the coach.")
    _head(ws, 4, ["#", "STEP 0 question", "Answer"])
    r = 5
    for x in p["inputs"]:
        _s(ws, r, 1, x["n"]); _s(ws, r, 2, x["q"]); _s(ws, r, 3, x["a"])
        r += 1
    r += 1
    _s(ws, r, 1, "Assumptions", bold=True)
    for t in p["assumptions"] or ["None - every question was answered."]:
        r += 1
        _s(ws, r, 2, t)
    _widths(ws, (5, 40, 110))

    # steps 1-14 (the work)
    ws = wb.create_sheet("Steps 1-14")
    r = 1
    for st in p["steps"]:
        _s(ws, r, 1, f"STEP {st['n']} - {st['title']}", bold=True, fill="DDEBF7")
        for t in st["lines"]:
            r += 1
            _s(ws, r, 1, t)
        if st.get("table"):
            r += 1
            _head(ws, r, ["Weeks", "Period", "Mesocycle", "Main goal"])
            ws.cell(row=r, column=1)
            for row in st["table"]:
                r += 1
                _s(ws, r, 1, row["weeks"]); _s(ws, r, 2, row["period"]); _s(ws, r, 3, row["mesocycle"]); _s(ws, r, 4, row["goal"])
        r += 2
    _widths(ws, (110, 22, 30, 50))

    # 2. overview + 3. load curve
    ws = wb.create_sheet("2 Overview")
    _head(ws, 1, ["Weeks", "Dates", "Period", "Mesocycle type", "Targets", "Methods", "Relative load (%)", "Tests / competitions"])
    r = 2
    tests = p["testing"]
    for m in p["mesocycles"]:
        tc = [f"{t['date']:%d %b}: {t['kind']}" for t in tests if m["start"] <= t["date"] <= m["end"]]
        vals = [m["weeks"], f"{m['start']:%d %b} - {m['end']:%d %b %Y}", m["period"], m["label"],
                " + ".join(m["targets"]) + (" (+ technique: " + m["technique"] + ")" if m["type"] != "transition" else ""),
                ", ".join(m["methods"]), m["relative_load"], "; ".join(tc) or "-"]
        for c, v in enumerate(vals, 1):
            _s(ws, r, c, v, fill=FILL[m["type"]] if c == 4 else None)
        r += 1
    r += 1
    _s(ws, r, 1, "Week by week", bold=True)
    r += 1
    _head(ws, r, ["Week", "Starts", "Period", "Mesocycle", "Volume (%)", "S&C sessions", "Targets", "Competitions / exams"])
    for w in p["weeks"]:
        r += 1
        m = p["mesocycles"][w["mesocycle"] - 1]
        for c, v in enumerate([w["week"], w["start"], w["period"], m["label"], w["volume"], w["sessions"], " + ".join(w["targets"]),
                               "; ".join(w["competitions"] + ([w["exam"]] if w["exam"] else [])) or ""], 1):
            _s(ws, r, c, v, fill=FILL[w["meso_type"]] if c == 4 else None)
    r += 2
    _s(ws, r, 1, "3. Load curve", bold=True)
    for t in p["load_curve"]:
        r += 1
        _s(ws, r, 1, t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    _widths(ws, (8, 24, 18, 26, 40, 32, 12, 40))

    # 4. complexes + 5. microcycles
    ws = wb.create_sheet("4-5 Complexes & weeks")
    r = 1
    for m in p["mesocycles"]:
        _s(ws, r, 1, f"{m['label']} - {m['start']:%d %b} to {m['end']:%d %b %Y} - complex {m['block']}"
                     + (" (NEW complex from this date)" if m["new_complex"] else " (same complex)"), bold=True, fill=FILL[m["type"]])
        r += 1
        _head(ws, r, ["#", "Exercise", "Ability", "Role", "Sets x reps / load", "Rest"])
        for i, e in enumerate(m["complex"], 1):
            r += 1
            for c, v in enumerate([i, e["name"], e["ability_label"], e["role"], e["dose"], e["rest"]], 1):
                _s(ws, r, c, v)
        r += 1
        if m["microcycle"]:
            _s(ws, r, 1, "Sample microcycle", bold=True)
            r += 1
            _head(ws, r, ["Day", "When", "Load %", "Exercises (sets x reps)", "Restoration", ""])
            for d in m["microcycle"]:
                r += 1
                _s(ws, r, 1, d["day"]); _s(ws, r, 2, d["when"] or d.get("note", "")); _s(ws, r, 3, d["load"] or "")
                _s(ws, r, 4, "\n".join(f"{x['name']}: {x['dose']}" + (f" (rest {x['rest']})" if x["rest"] else "") for x in d["items"]) or d.get("note", ""))
                _s(ws, r, 5, d["restoration"])
        if m["competition_microcycle"]:
            _s(ws, r, 1, f"Competition microcycle ({len(m['competition_microcycle'])} days)", bold=True)
            r += 1
            _head(ws, r, ["Date", "Day", "Session", "Restoration", "", ""])
            for d in m["competition_microcycle"]:
                r += 1
                _s(ws, r, 1, d["date"]); _s(ws, r, 2, d["day"]); _s(ws, r, 3, d["session"]); _s(ws, r, 4, d["restoration"])
            if m["competition_note"]:
                r += 1
                _s(ws, r, 1, m["competition_note"])
        r += 2
    _widths(ws, (14, 40, 24, 16, 60, 34))

    # 6. taper, 7. transition
    ws = wb.create_sheet("6-7 Taper & transition")
    r = 1
    for t in p["tapers"]:
        _s(ws, r, 1, f"Taper - last 14 days before {t['competition']} ({t['start']:%d %b %Y})", bold=True, fill=FILL["realization"])
        r += 1
        _head(ws, r, ["Date", "Days out", "Session", "Exercises", "Load %", "Restoration"])
        for d in t["rows"]:
            r += 1
            for c, v in enumerate([d["date"], d["days_out"], d["session"] + (" (past)" if d["past"] else ""),
                                   ", ".join(f"{e['name']} {e['dose']}" for e in d["exercises"]), d["load"], d["restoration"]], 1):
                _s(ws, r, c, v)
        r += 2
    tr = p["transition"]
    _s(ws, r, 1, f"Transition: {tr['weeks']} week(s)" + (f" from {tr['from']:%d %b %Y}" if tr["from"] else ""), bold=True, fill=FILL["transition"])
    for t in tr["guidelines"] + [tr["body_weight"]]:
        r += 1
        _s(ws, r, 1, t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    _widths(ws, (14, 9, 50, 50, 8, 20))

    # 8. monitoring + STEP 16
    ws = wb.create_sheet("8 Monitoring & check")
    _head(ws, 1, ["Date", "Mesocycle", "Test / competition", "What", "If below expectation"])
    r = 1
    for t in p["testing"]:
        r += 1
        for c, v in enumerate([t["date"], t["mesocycle"], t["kind"], t["what"], t["if_below"]], 1):
            _s(ws, r, c, v)
    r += 2
    _s(ws, r, 1, "STEP 16 - Self-check", bold=True)
    r += 1
    _head(ws, r, ["Result", "Check", "Detail", "", ""])
    for c in p["self_check"]:
        r += 1
        _s(ws, r, 1, {True: "OK", False: "FIX", None: "LIMITED"}[c["ok"]], fill=OKF[c["ok"]], bold=True)
        _s(ws, r, 2, c["item"]); _s(ws, r, 3, c["detail"])
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
    _widths(ws, (14, 50, 40, 50, 60))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
