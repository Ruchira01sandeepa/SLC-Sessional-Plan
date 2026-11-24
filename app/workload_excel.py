"""The weekly workload report as an Excel workbook, laid out like the McGawley workshop notes:
  Squad week | one sheet per player (the example week: Day, Session, Minutes, RPE, Load (AU) - with Total, Mean daily load, SD,
  Monotony and Strain by formula) | Weekly trend (8 weeks) | Test change (pre -> post: % change, effect size) | Formulas | Process.
Charts read plain numbers written on their sheet (they show in any viewer). Text is stored as text, never as a formula."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.hyperlink import Hyperlink

from .workload_calc import ACWR_SPIKE, MONOTONY_HIGH, WEEK_CHANGE_FLAG, ZONE_LABELS

THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = "1F3864"
SUB = "D9E1F2"
FLAG = "FFC7CE"
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _t(ws, r, c, v, *, bold=False, fill=None, white=False, fmt=None, align=None):
    cell = ws.cell(row=r, column=c, value=v)
    if isinstance(v, str):
        cell.data_type = "s"
    cell.font = Font(bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    if fmt:
        cell.number_format = fmt
    if align:
        cell.alignment = align
    return cell


def _f(ws, r, c, formula, fmt=None, bold=False):
    cell = ws.cell(row=r, column=c, value=formula)
    cell.data_type = "f"
    cell.font = Font(bold=bold)
    if fmt:
        cell.number_format = fmt
    return cell


def _title(ws, text, width):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    _t(ws, 1, 1, text, bold=True, fill=HEAD, white=True, align=CENTER)


def _sheet_name(name: str, no, used: set) -> str:
    clean = "".join(ch for ch in name if ch not in set("[]:*?/\\")).strip() or "Player"
    base = (f"{no} {clean}" if no is not None else clean)[:31]
    out, i = base, 2
    while out in used:
        out, i = f"{base[:28]} {i}", i + 1
    used.add(out)
    return out


def _player_sheet(ws, rep: dict) -> None:
    """The workshop's example week (3.3) for one player: Day | Session | Minutes | RPE | Load (AU) = Minutes x RPE, then the
    week's indicators by formula, then heart-rate and external load."""
    p = rep["player"]
    _title(ws, f"{p['name']} - week of {rep['monday']:%d %b %Y} to {rep['sunday']:%d %b %Y}", 13)
    heads = ["Day", "Date", "Session", "Minutes", "RPE (0-10)", "Load (AU)", "Avg HR", "Edwards TRIMP", "Banister TRIMP",
             "Min >= 90% HRmax", "Sprint m", "Volume load kg", "Foot contacts"]
    for c, h in enumerate(heads, 1):
        _t(ws, 3, c, h, bold=True, fill=SUB, align=CENTER)
    widths = [6, 11, 16, 9, 9, 10, 8, 10, 10, 11, 9, 12, 10]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + c)].width = w
    r = 4
    day_rows = []
    for d in rep["days"]:
        first = r
        ses = d["sessions"] or [None]
        for x in ses:
            _t(ws, r, 1, d["day"])
            _t(ws, r, 2, d["date"], fmt="dd-mmm")
            if x is None:
                _t(ws, r, 3, "Rest")
                ws.cell(row=r, column=4, value=0)
                ws.cell(row=r, column=5, value=0)
            else:
                _t(ws, r, 3, (x["type"].replace("_", " ").capitalize()) if x.get("attended", True) else "Absent")
                ws.cell(row=r, column=4, value=x.get("minutes") if x.get("attended", True) else 0)
                rpe = x.get("rpe") if x.get("rpe") is not None else x.get("intensity")
                ws.cell(row=r, column=5, value=rpe if x.get("attended", True) else 0)
                for c, k in ((7, "hr_avg"), (8, "edwards"), (9, "banister"), (10, "hit"), (11, "sprint_m"), (12, "volume_load_kg"), (13, "foot_contacts")):
                    v = x.get(k)
                    if v is not None:
                        ws.cell(row=r, column=c, value=round(v, 1) if isinstance(v, float) else v)
            _f(ws, r, 6, f"=N(D{r})*N(E{r})", fmt="0")
            r += 1
        day_rows.append((first, r - 1))
    last = r - 1
    _t(ws, r, 1, "Total", bold=True)
    for c in (4, 6, 8, 9, 10, 11, 12, 13):
        col = chr(64 + c)
        _f(ws, r, c, f"=SUM({col}4:{col}{last})", fmt="0", bold=True)
    for row in ws.iter_rows(min_row=3, max_row=r, min_col=1, max_col=13):
        for c in row:
            c.border = BOX
    total_row = r
    # daily loads (rest days = 0), then the indicators, as in the worked example
    r += 2
    _t(ws, r, 1, "Daily load (AU)", bold=True, fill=SUB)
    for i, (a, b) in enumerate(day_rows):
        _t(ws, r + 1, 1 + i, rep["days"][i]["day"], bold=True, align=CENTER)
        _f(ws, r + 2, 1 + i, f"=SUM(F{a}:F{b})", fmt="0")
    dl = f"A{r + 2}:G{r + 2}"
    r += 4
    rows = [("Weekly load (AU) = sum of the days", f"=SUM({dl})", "0"),
            ("Mean daily load (AU)", f"=AVERAGE({dl})", "0"),
            ("SD of daily load (AU, sample)", f"=STDEV({dl})", "0"),
            ("Monotony = mean / SD", f'=IF(STDEV({dl})=0,"-",AVERAGE({dl})/STDEV({dl}))', "0.00"),
            ("Strain = weekly load x monotony", f'=IF(STDEV({dl})=0,"-",SUM({dl})*AVERAGE({dl})/STDEV({dl}))', "0")]
    for label, formula, fmt in rows:
        _t(ws, r, 1, label, bold=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        _f(ws, r, 5, formula, fmt=fmt, bold=True)
        r += 1
    info = [("Previous week (AU)", rep["previous_week"]), ("Change on last week (%)", rep["change_pct"]),
            ("Acute:chronic ratio (7 d / 28-d weekly average)", rep["acwr"]), ("ACWR band", rep["acwr_band"]),
            ("Heaviest week so far (AU)", rep["heaviest_week"]), ("Weekly load % (this week / heaviest week)", rep["load_pct"]),
            ("Mean performance decrement, repeated sprints (%)", rep["sdec"]),
            ("HRmax used for TRIMP", f"{p['hr_max_used']} bpm" + (" (estimated 208 - 0.7 x age)" if p["hr_max_estimated"] else "") if p["hr_max_used"] else "-"),
            ("Resting HR", p["hr_rest"] or "-"),
            ("Wellness this week (avg sleep h / soreness / fatigue)",
             " / ".join(str(rep["wellness"][k] if rep["wellness"][k] is not None else "-") for k in ("sleep_hours", "soreness", "fatigue")))]
    for label, v in info:
        _t(ws, r, 1, label)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        _t(ws, r, 5, v if v is not None else "-")
        r += 1
    if rep["flags"]:
        r += 1
        _t(ws, r, 1, "Flags (a conversation, not a diagnosis)", bold=True, fill=FLAG)
        for fl in rep["flags"]:
            r += 1
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
            _t(ws, r, 1, fl, align=WRAP)
    ws.freeze_panes = "A4"
    _ = total_row


def build_workload_workbook(squad: str, monday, reps: list[dict], planned_pct, trend: dict, tests: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Squad week"
    sunday = monday + timedelta(days=6)
    heads = ["No", "Player", "Sessions", "Weekly load (AU)", "Mean daily (AU)", "SD daily (AU)", "Monotony", "Strain", "Previous week",
             "Change %", "ACWR", "ACWR band", "Load % (measured)", "Load % (planned)", "Edwards TRIMP", "Banister TRIMP",
             "Min >= 90% HRmax", "Sprint m", "Volume load kg", "Foot contacts", "Sdec %", "Sleep h", "Soreness", "Fatigue", "Flags"]
    _title(ws, f"WORKLOAD - {squad.upper()} - WEEK OF {monday:%d %b %Y} TO {sunday:%d %b %Y}", len(heads))
    _t(ws, 2, 1, "Load = session RPE (0-10) x minutes (AU). Monotony = mean / SD of the daily load; strain = weekly load x monotony. "
                 f"Flags: change above {WEEK_CHANGE_FLAG:.0f}%, monotony above {MONOTONY_HIGH}, ACWR above {ACWR_SPIKE} (warning flags only).",
       align=WRAP)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(heads))
    ws.row_dimensions[2].height = 30
    for c, h in enumerate(heads, 1):
        _t(ws, 3, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[ws.cell(row=3, column=c).column_letter].width = 26 if c == 2 else 48 if c == len(heads) else 10
    used = {"Squad week", "Weekly trend", "Test change", "Formulas", "Process"}
    for i, rep in enumerate(reps, 4):
        p = rep["player"]
        vals = [p["squad_no"], p["name"], rep["sessions"], rep["total"], rep["mean_daily"], rep["sd_daily"], rep["monotony"], rep["strain"],
                rep["previous_week"], rep["change_pct"], rep["acwr"], rep["acwr_band"], rep["load_pct"], planned_pct, rep["edwards_trimp"],
                rep["banister_trimp"], rep["hit_minutes"], rep["sprint_m"], rep["volume_load_kg"], rep["foot_contacts"], rep["sdec"],
                rep["wellness"]["sleep_hours"], rep["wellness"]["soreness"], rep["wellness"]["fatigue"], " ".join(rep["flags"]) or None]
        for c, v in enumerate(vals, 1):
            cell = _t(ws, i, c, v, align=WRAP if c == len(heads) else None)
            cell.border = BOX
        if rep["flags"]:
            ws.cell(row=i, column=len(heads)).fill = PatternFill("solid", fgColor=FLAG)
        rep["_sheet"] = _sheet_name(p["name"], p["squad_no"], used)
        link = ws.cell(row=i, column=2)
        link.hyperlink = Hyperlink(ref=link.coordinate, location=f"'{rep['_sheet']}'!A1", display=p["name"])
        link.font = Font(color="0563C1", underline="single")
    n = len(reps)
    if n:
        ch = BarChart()
        ch.title, ch.y_axis.title, ch.height, ch.width = "Weekly load by player (AU)", "AU", 9, 26
        ch.add_data(Reference(ws, min_col=4, min_row=3, max_row=3 + n), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=2, min_row=4, max_row=3 + n))
        ch.x_axis.delete = ch.y_axis.delete = False
        ws.add_chart(ch, f"B{n + 6}")
    ws.freeze_panes = "C4"

    for rep in reps:
        _player_sheet(wb.create_sheet(rep["_sheet"]), rep)

    tr = wb.create_sheet("Weekly trend")
    weeks = [monday - timedelta(days=7 * k) for k in range(7, -1, -1)]
    _title(tr, "WEEKLY LOAD (AU), LAST 8 WEEKS - keep the week-to-week change under about 10% unless an overload is planned", 10)
    _t(tr, 3, 1, "Player", bold=True, fill=SUB)
    for j, w in enumerate(weeks, 2):
        _t(tr, 3, j, f"{w:%d %b}", bold=True, fill=SUB, align=CENTER)
    tr.column_dimensions["A"].width = 26
    for i, rep in enumerate(reps, 4):
        _t(tr, i, 1, rep["player"]["name"])
        for j, v in enumerate(trend.get(rep["player"]["id"], []), 2):
            tr.cell(row=i, column=j, value=v)
    avg_row = 4 + n
    _t(tr, avg_row, 1, "Squad average", bold=True)
    for j in range(2, 10):
        col = [trend[r["player"]["id"]][j - 2] for r in reps if trend.get(r["player"]["id"])]
        tr.cell(row=avg_row, column=j, value=round(sum(col) / len(col)) if col else 0)
    lc = LineChart()
    lc.title, lc.y_axis.title, lc.height, lc.width = "Squad average weekly load (AU)", "AU", 8, 24
    lc.add_data(Reference(tr, min_col=1, max_col=9, min_row=avg_row, max_row=avg_row), from_rows=True, titles_from_data=True)
    lc.set_categories(Reference(tr, min_col=2, max_col=9, min_row=3, max_row=3))
    lc.x_axis.delete = lc.y_axis.delete = False
    tr.add_chart(lc, f"B{avg_row + 3}")

    tc = wb.create_sheet("Test change")
    _title(tc, "TEST CHANGE (the same tests before and after): % change = (post - pre) / pre x 100; effect size = (post mean - pre mean) / pre SD", 11)
    if tests.get("post"):
        _t(tc, 2, 1, f"Season {tests['season']}: {tests['pre']} -> {tests['post']} (players with both results). Lower is better for times.", align=WRAP)
    else:
        _t(tc, 2, 1, "Only one test window has results so far: re-test with the same tests (familiarise first) to measure the change." +
           (f" Season {tests['season']}, {tests['pre']}." if tests.get("season") else ""), align=WRAP)
    tc.merge_cells("A2:K2")
    th = ["Test", "Unit", "Players", "Pre mean", "Pre SD", "Post mean", "Post SD", "% change", "Effect size", "Effect", "Improved"]
    for c, h in enumerate(th, 1):
        _t(tc, 4, c, h, bold=True, fill=SUB, align=CENTER)
        tc.column_dimensions[tc.cell(row=4, column=c).column_letter].width = 22 if c == 1 else 11
    for i, row in enumerate(tests.get("rows", []), 5):
        vals = [row["test"], row["unit"], row.get("n"), row.get("pre_mean"), row.get("pre_sd"), row.get("post_mean"), row.get("post_sd"),
                row.get("change_pct"), row.get("effect_size"), row.get("effect"), row.get("improved")]
        for c, v in enumerate(vals, 1):
            _t(tc, i, c, round(v, 2) if isinstance(v, float) else (v if v is not None else "-"))

    fm = wb.create_sheet("Formulas")
    _title(fm, "STANDARD WORKLOAD FORMULAS (general sports science; the workshop shows prescription, recording and evaluation)", 3)
    rows = [("Method", "Formula", "Example"),
            ("Session RPE load (sRPE)", "RPE (CR-10, 0-10) x session minutes. Ask about 30 min after the session; include the warm-up.", "RPE 8 x 90 min = 720 AU"),
            ("Weekly load", "Sum of the daily session loads", "2,955 AU (example week)"),
            ("Monotony", "Mean daily load / SD of daily load (rest days = 0)", "422 / 285 = 1.48 (above ~2.0 = too little variation)"),
            ("Strain", "Weekly load x monotony", "2,955 x 1.48 = about 4,384 AU"),
            ("Edwards TRIMP", "Minutes in each HR zone x weight: " + ", ".join(f"{z} = {w}" for z, w in zip(ZONE_LABELS, range(1, 6))),
             "9 min x 5 + 6 min x 4 + 10 min x 2 = 89 AU"),
            ("Banister TRIMP", "Minutes x HRr x 0.64e^(1.92 HRr) (men; women 0.86e^(1.67 HRr)); HRr = (HRex - HRrest) / (HRmax - HRrest)",
             "30 min, HR 170, rest 60, max 195 -> HRr 0.81 -> about 75 AU"),
            ("Week-to-week change", "(This week - last week) / last week x 100", "Keep under about 10% unless an overload is planned"),
            ("Acute:chronic ratio (ACWR)", "Last 7 days' load / 28-day average weekly load",
             "About 0.8-1.3 often used; above about 1.5 flagged. A warning flag only - its value is debated"),
            ("Weekly load % (annual plan)", "Week's sRPE / heaviest week's sRPE x 100", "Turns the planned load % row into measured data"),
            ("Volume load", "Sets x reps x (%1RM x 1RM)", "2 x 10 at 75% of 99 kg = 1,485 kg"),
            ("% change", "(post - pre) / pre x 100", "Squat 99 -> 117 kg = +18.2%"),
            ("Effect size", "(post mean - pre mean) / pre SD", "(117 - 99) / 15 = 1.2 (large)"),
            ("Performance decrement (Sdec)", "Total sprint time / (best time x number of sprints) x 100 - 100",
             "7.1, 7.3, 7.4, 7.6, 7.8, 7.9 s -> 5.9%")]
    for i, row in enumerate(rows, 3):
        for c, v in enumerate(row, 1):
            _t(fm, i, c, v, bold=i == 3, fill=SUB if i == 3 else None, align=WRAP)
    fm.column_dimensions["A"].width, fm.column_dimensions["B"].width, fm.column_dimensions["C"].width = 30, 70, 50

    pr = wb.create_sheet("Process")
    _title(pr, "THE COMPLETE WORKLOAD PROCESS (organised, purposeful, systematic, controlled, evidence-informed)", 2)
    steps = ["Needs analysis: what the sport demands (physiology, biomechanics, psychology, nutrition, skill, anthropometry).",
             "Athlete assessment: familiarise first, then standardised tests (the SLC U15 battery: sprint, agility, jump, upper-body, core, 2 km).",
             "Gap analysis: pick the priority gaps (the focus areas of each player).",
             "Prescribe the load with clear anchors: % HRmax and % 1RM, sets x reps, work:rest, rest periods, sessions a week (not back to back).",
             "Progress gradually: intensity up, volume down near competition; conditioning minutes up step by step.",
             "Monitor every session: internal load (RPE, HR) and external load (minutes >= 90% HRmax, sprint metres, volume load, foot contacts).",
             "Monitor every week: total load, monotony, strain, % change, acute:chronic ratio as a flag.",
             "Watch the whole person: sleep, soreness, mood, nutrition, hydration, school and family; share with the multidisciplinary team.",
             "Re-test with the same tests: % change, effect size, performance decrement; responses are individual. Plan the next block.",
             "Keep the process organised, purposeful, systematic, controlled and evidence-informed."]
    for i, st in enumerate(steps, 3):
        pr.cell(row=i, column=1, value=i - 2)
        _t(pr, i, 2, st, align=WRAP)
    pr.column_dimensions["B"].width = 120
    _t(pr, len(steps) + 5, 2, "Source: Prof. Kerry McGawley, 'Concepts of Sports Science for Athlete Performance Enhancement and Wellbeing' "
                              "(workshop notes); standard formulas from general sports science (Foster sRPE, Edwards / Banister TRIMP).", align=WRAP)
    wb.calculation.fullCalcOnLoad = True
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
