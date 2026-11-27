"""The periodized annual plan (periodized_plan.build) as an Excel workbook, Phase 9 of the ANNUAL PLAN BUILDER instructions:
Inputs | Annual plan | Week data | Load chart | Methods by phase | Mesocycles | Microcycles | Conditioning detail |
Resistance detail | Session plans | Checks. One source of truth: the Annual plan's load row; every other sheet references it.
Every total and every check is a formula. Text is always stored as text, never as a formula."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.planning import periodized_plan as pp

THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="1F3864")
SUB = PatternFill("solid", fgColor="D9E1F2")
PHASE_FILL = {"H": "C6E0B4", "B": "A9D08E", "S": "F8CBAD", "U": "FFE699", "P": "FF9999", "M": "9BC2E6", "T": "D9D9D9"}
PERIOD_FILL = {"Preparatory": "A9D08E", "First transition": "FFE699", "Competition": "FF9999", "Second transition": "D9D9D9"}
COMP_FILL = {"MAIN": "FF0000", "SECONDARY": "FFA500", "LEAGUE": "4F81BD"}
LEVEL_FILL = {1: "DDEBF7", 2: "9BC2E6", 3: "2F5597"}
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _t(ws, r, c, v, *, bold=False, fill=None, white=False, fmt=None, align=None):
    cell = ws.cell(row=r, column=c, value=v)
    if isinstance(v, str) and not v.startswith("="):
        cell.data_type = "s"
    cell.font = Font(bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill) if isinstance(fill, str) else fill
    if fmt:
        cell.number_format = fmt
    if align:
        cell.alignment = align
    return cell


def _f(ws, r, c, formula, fmt=None, align=CENTER):
    cell = ws.cell(row=r, column=c, value=formula)
    cell.data_type = "f"
    if fmt:
        cell.number_format = fmt
    cell.alignment = align
    return cell


def _name(wb, name, ref):
    wb.defined_names[name] = DefinedName(name, attr_text=ref)


def _runs(values):
    out, a = [], 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[a]:
            out.append((a, i - 1, values[a]))
            a = i
    return out


def _merge(ws, r, a, b, text, fill=None, white=False):
    if b > a:
        ws.merge_cells(start_row=r, start_column=a, end_row=r, end_column=b)
    _t(ws, r, a, text, bold=True, fill=fill, white=white, align=CENTER)


# ───────────── sheets ─────────────
def _inputs(wb, p) -> dict:
    ws = wb.active
    ws.title = "Inputs"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 34, 70, 30
    _t(ws, 1, 1, f"PERIODIZED ANNUAL PLAN - INPUTS ({p['squad']}, {p['season']['name']})", bold=True)
    _t(ws, 2, 1, "Built by the ANNUAL PLAN BUILDER rules (Zatsiorsky & Kraemer ch. 1, 5, 10; NSCA Essentials, periodization and program design).")
    _t(ws, 4, 1, "Named cells", bold=True, fill=SUB)
    named = [("StartDate", "Plan start date", p["plan_start"], "dd-mmm-yyyy"), ("Weeks", "Weeks in the plan", p["weeks"], "0"),
             ("MaxLoad", "Maximum load (100%)", 1.0, "0%"), ("RefBodyMass", "Reference body mass (kg, assumption)", pp.REF_BODY_MASS, "0"),
             ("PlyoMax", "Plyometric contacts a session, maximum (beginner)", pp.PLYO_MAX_CONTACTS, "0"),
             ("TaperWeeks", "Taper length for a normal load rise (weeks)", pp.TAPER_FOR_RISE[pp.LOAD_RISE], "0"), ("Youth", "Youth plan (under 18)", True, None)]
    for i, (nm, label, val, fmt) in enumerate(named, 5):
        _t(ws, i, 1, label)
        c = ws.cell(row=i, column=2, value=val)
        if fmt:
            c.number_format = fmt
        _t(ws, i, 3, nm)
        _name(wb, nm, f"Inputs!$B${i}")
    r = 5 + len(named) + 1
    pl = p.get("player")
    if pl:                                                   # a player's own plan
        _t(ws, r, 1, f"PLAYER: {pl['name']} ({pl['role']})", bold=True, fill=HEAD, white=True)
        rows = [("Focus (weak, below the 50th percentile)", ", ".join(f"{a['label']} {a['percentile']:g}" for a in pl["weak"]) or "none"),
                ("Strong (75th percentile or more)", ", ".join(f"{a['label']} {a['percentile']:g}" for a in pl["strong"]) or "none")]
        rows += [(f"Extra for {k}", v) for k, v in pl["extras"]]
        rows += [(f"Test: {k}", v) for k, v in pl["results"]]
        rows.append(("Rule", "Weak areas are raised one level (max 3) in every week the squad trains them, with the extras above; strong "
                             "areas keep the full squad work; the youth limits and every check still apply."))
        for i, (k, v) in enumerate(rows, r + 1):
            _t(ws, i, 1, k, align=WRAP)
            _t(ws, i, 2, v, align=WRAP)
        r += len(rows) + 2
    _t(ws, r, 1, "Phase 0 - inputs (from the app; ASSUMPTIONS where the app holds no data)", bold=True, fill=SUB)
    comps = "; ".join(f"{c['type']}: {c['name']} {c['start']:%d %b %Y}" + (f" to {c['end']:%d %b %Y}" if c["end"] != c["start"] else "")
                      + (" (assumed)" if c.get("assumed") else "") for c in p["competitions"])
    answers = [
        ("1. Sport, group, age, sex", f"Cricket (team). {p['squad']}: {p['players']} players, {p['age_group']} boys (about 14-15 years)."),
        ("2. Training age and level", "About 1-3 years; beginner-intermediate in the gym (ASSUMPTION)."),
        ("3. Start, end, first day of the week", f"{p['plan_start']:%d %b %Y} to {p['plan_start'] + timedelta(days=7 * p['weeks'] - 1):%d %b %Y}; "
                                                 f"weeks start on {p['plan_start']:%A}."),
        ("4. Competition calendar", comps),
        ("5. Days, sessions, length", "5-6 days a week after school (PM), Saturday AM; 1 session a day; 60-120 min (ASSUMPTION)."),
        ("6. Facilities, coach ratio", f"Cricket ground, field or track, basic gym; coach ratio {pp.COACH_RATIO} (ASSUMPTION; youth rule)."),
        ("7. Latest test results", "; ".join(f"{a}: {b}" for a, b in p["tests"]) or "No results in the latest window."),
        ("8. Injury history, clearance", "Not used here (medical privacy). Each player needs clearance before testing."),
        ("9. School / work limits", "Not in the system: put unloading weeks on exam weeks (ASSUMPTION)."),
        ("10. Limiting abilities", "Speed and acceleration, change of direction, leg and rotational power, trunk strength, aerobic recovery."),
        ("11. Language and units", "English; kg and metres."),
    ]
    for i, (q, a) in enumerate(answers, r + 1):
        _t(ws, i, 1, q, align=WRAP)
        _t(ws, i, 2, a, align=WRAP)
    r += len(answers) + 2
    _t(ws, r, 1, "Needs analysis", bold=True, fill=SUB)
    for i, (k, v) in enumerate(p["needs"], r + 1):
        _t(ws, i, 1, k, align=WRAP)
        _t(ws, i, 2, v, align=WRAP)
    r += len(p["needs"]) + 2
    _t(ws, r, 1, "Assumptions", bold=True, fill=SUB)
    for i, a in enumerate(p["assumptions"], r + 1):
        _t(ws, i, 2, a, align=WRAP)
    r += len(p["assumptions"]) + 2
    _t(ws, r, 1, "Model", bold=True, fill=SUB)
    _t(ws, r + 1, 2, p["model"], align=WRAP)
    r += 3
    _t(ws, r, 1, "Test order (NSCA: most rested to most fatiguing)", bold=True, fill=SUB)
    _t(ws, r, 2, "U15 SOP test", bold=True, fill=SUB)
    _t(ws, r, 3, "Order", bold=True, fill=SUB)
    tests = [("Non-fatiguing: anthropometry", "Height, body weight"), ("Non-fatiguing: jump", "Standing broad jump"),
             ("Agility", "5-10-5 shuttle"), ("Maximal power and strength", "No 1RM for U15: estimated from multi-rep sets"),
             ("Sprint", "20 m sprint"), ("Local muscular endurance", "Push-ups, inverted row, plank"),
             ("Aerobic capacity (last or another day)", "2 km run")]
    first = r + 1
    for i, (a, b) in enumerate(tests, r + 1):
        _t(ws, i, 1, a)
        _t(ws, i, 2, b)
        ws.cell(row=i, column=3, value=i - r)
    return {"test_order": (first, first + len(tests) - 1)}


def _annual(wb, p) -> dict:
    ws = wb.create_sheet("Annual plan")
    W, codes = p["weeks"], p["codes"]
    last = L(W + 1)
    ws.column_dimensions["A"].width = 34
    for w in range(W):
        ws.column_dimensions[L(w + 2)].width = 7.5
    _merge(ws, 1, 1, W + 1, f"PERIODIZED ANNUAL PLAN - {p['squad'].upper()} ({p['season']['name']}) - "
                            f"{p['plan_start']:%d %b %Y} TO {p['plan_start'] + timedelta(days=7 * W - 1):%d %b %Y}", fill=HEAD, white=True)
    labels = {2: "Periods", 3: "Phases", 4: "Mesocycle # and type", 5: "Month", 6: "Microcycle #", 7: "Week start", 8: "Competitions",
              9: "Tests", 10: "Medical", 11: "Lab", 12: "Field", 13: "Load %", 14: "Volume", 15: "Intensity", 16: "Load", 17: "Peaking index (1-5)",
              18: "Sessions per week"}
    for r, t in labels.items():
        _t(ws, r, 1, t, bold=r in (9, 18), fill=SUB if r in (9, 18) else None)
    for a, b, per in _runs([pp.PHASES[c][0] for c in codes]):
        _merge(ws, 2, a + 2, b + 2, per, fill=PERIOD_FILL[per])
    for a, b, c in _runs(codes):
        _merge(ws, 3, a + 2, b + 2, pp.PHASES[c][1], fill=PHASE_FILL[c])
    for m in p["mesos"]:
        _merge(ws, 4, m["first"] + 2, m["last"] + 2, f"Meso {m['no']} - {m['type']}", fill=PHASE_FILL[m['codes'][0]])
    months = [(p["plan_start"] + timedelta(days=7 * w)).strftime("%b %Y") for w in range(W)]
    for a, b, mth in _runs(months):
        _merge(ws, 5, a + 2, b + 2, mth)
    for w in range(W):
        c = w + 2
        ws.cell(row=6, column=c, value=w + 1).alignment = CENTER
        _f(ws, 7, c, f"=StartDate+7*({L(c)}6-1)", fmt="dd-mmm")
        if p["comp_week"][w]:
            _t(ws, 8, c, p["comp_week"][w], bold=True, white=True, fill=COMP_FILL[p["comp_week"][w]], align=CENTER)
        if p["medical"][w]:
            _t(ws, 10, c, "x", align=CENTER)
        if p["test_due"][w]:
            _t(ws, 12, c, "x", align=CENTER)
        ws.cell(row=13, column=c, value=p["loads"][w]).number_format = "0%"
        v, i = pp.VOL_INT[codes[w]]
        _t(ws, 14, c, v, align=CENTER)
        _t(ws, 15, c, i, align=CENTER)
        _f(ws, 16, c, f'=IF({L(c)}13>=0.75,"High",IF({L(c)}13>=0.5,"Medium","Low"))')
        ws.cell(row=17, column=c, value=5 if p["comp_week"][w] == "MAIN" else pp.PEAKING_INDEX[codes[w]]).alignment = CENTER
    _t(ws, 11, W + 3, "Lab: no laboratory tests (facilities). Field = the U15 SOP battery.")
    r = 19
    rows = {}
    for i, name in enumerate(pp.SESSION_TYPES):
        _t(ws, r, 1, name)
        rows[name] = r
        for w in range(W):
            ws.cell(row=r, column=w + 2, value=p["sessions"][i][w]).alignment = CENTER
        r += 1
    _t(ws, r, 1, "Matches")
    for w in range(W):
        ws.cell(row=r, column=w + 2, value=p["matches_per_week"][w]).alignment = CENTER
    r += 1
    _t(ws, r, 1, "Training factors (0 not trained, 1 retaining, 2 developing, 3 main focus)", bold=True, fill=SUB)
    r += 1
    factor_rows, f_first = {}, r
    for sec, frows in p["factors"]:
        _t(ws, r, 1, sec, bold=True, fill=SUB)
        r += 1
        for label, vals in frows:
            _t(ws, r, 1, label)
            factor_rows[label] = r
            for w, v in enumerate(vals):
                ws.cell(row=r, column=w + 2, value=v).alignment = CENTER
            r += 1
    f_last = r - 1
    rng = f"B{f_first}:{last}{f_last}"
    for lv, col in LEVEL_FILL.items():
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[str(lv)], fill=PatternFill("solid", fgColor=col),
                                                      font=Font(color="FFFFFF" if lv == 3 else "000000")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=["0"], fill=PatternFill("solid", fgColor="FFFFFF")))
    _t(ws, r, 1, "Nutrition and recovery", bold=True)
    for a, b, c in _runs(codes):
        _merge(ws, r, a + 2, b + 2, pp.NUTRITION[c])
        ws.cell(row=r, column=a + 2).alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
    ws.row_dimensions[r].height = 90
    for row in ws.iter_rows(min_row=2, max_row=r, min_col=1, max_col=W + 1):
        for c in row:
            c.border = BOX
    ws.freeze_panes = "B8"
    tech = [factor_rows[l] for l in ("Basic technique", "Advanced technique", "Competition technique", "Basic tactics",
                                     "Team offensive / defensive", "Game-plan specific")]
    return {"last": last, "f_first": f_first, "f_last": f_last, "rows": rows, "factor_rows": factor_rows, "tech": (min(tech), max(tech))}


def _week_data(wb, p, ap) -> int:
    ws = wb.create_sheet("Week data")
    heads = ["Week", "Start", "Period", "Phase", "Code", "Meso #", "Meso type", "Load %", "Volume (1-3)", "Intensity (1-3)", "Load text",
             "Competition", "MAIN next week", "Realization", "Days to MAIN", "Heavy lower body", "Resistance sessions", "Level-3 factors",
             "Technical + tactical", "Conditioning m", "Previous loading week m", "Rise", "Rise counted", "Stress microcycle",
             "Plyo contacts / session", "Field test", "Test due", "Macro", "Unloading week", "Expected load text", "Plyo sessions", "Max strength level"]
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[L(c)].width = 12
    W, codes = p["weeks"], p["codes"]
    pre_main = {w - 1 for w in range(1, W + 1) if (w == W and any(c.get("next_year") for c in p["competitions"]))
                or (w < W and p["comp_week"][w] == "MAIN" and p["comp_week"][w - 1] != "MAIN")}
    cond_last = 1 + sum(len(x) for x in p["conditioning"])
    prev_loading = None
    for w in range(W):
        r, col = w + 2, L(w + 2)
        m = p["meso_of"][w]
        rows = p["conditioning"][w]
        counted = bool(rows and rows[0]["counted"])
        vals = [w + 1, None, pp.PHASES[codes[w]][0], pp.PHASES[codes[w]][1], codes[w], m["no"], m["type"], None,
                pp.LEVEL_NUM[pp.VOL_INT[codes[w]][0]], pp.LEVEL_NUM[pp.VOL_INT[codes[w]][1]], None, None, int(w in pre_main),
                int(m["type"] == "Realization"), p["days_to_main"][w], p["heavy_legs"][w]]
        for c, v in enumerate(vals, 1):
            if v is not None:
                _t(ws, r, c, v)
        _f(ws, r, 2, f"=StartDate+7*(A{r}-1)", fmt="dd-mmm-yy")
        _f(ws, r, 8, f"='Annual plan'!{col}13", fmt="0%")
        _f(ws, r, 11, f"='Annual plan'!{col}16")
        _f(ws, r, 12, f"=\"\"&'Annual plan'!{col}8")
        _f(ws, r, 17, f"='Annual plan'!{col}{ap['rows']['Resistance']}")
        _f(ws, r, 18, f"=COUNTIF('Annual plan'!{col}{ap['f_first']}:{col}{ap['f_last']},3)")
        _f(ws, r, 19, f"=SUM('Annual plan'!{col}{ap['tech'][0]}:{col}{ap['tech'][1]})")
        _f(ws, r, 20, f"=SUMPRODUCT(('Conditioning detail'!$A$2:$A${cond_last}=A{r})*'Conditioning detail'!$F$2:$F${cond_last}*'Conditioning detail'!$G$2:$G${cond_last})")
        if counted and not p["unload"][w] and prev_loading is not None:
            _f(ws, r, 21, f"=T{prev_loading}")
            _f(ws, r, 22, f"=T{r}/U{r}-1", fmt="0%")
            _t(ws, r, 23, 1)
        else:
            _t(ws, r, 23, 0)
        if not counted:
            prev_loading = None
        elif not p["unload"][w]:
            prev_loading = r
        _t(ws, r, 24, 0)
        _t(ws, r, 25, p["plyo"][w])
        _f(ws, r, 26, f"=\"\"&'Annual plan'!{col}12")
        _t(ws, r, 27, int(p["test_due"][w]))
        _t(ws, r, 28, m["macro"])
        _t(ws, r, 29, int(p["unload"][w]))
        _f(ws, r, 30, f'=IF(H{r}>=0.75,"High",IF(H{r}>=0.5,"Medium","Low"))')
        _f(ws, r, 31, f"='Annual plan'!{col}{ap['rows']['Plyometrics']}")
        _f(ws, r, 32, f"='Annual plan'!{col}{ap['factor_rows']['Maximal strength']}")
    ws.freeze_panes = "B2"
    return W + 1


def _load_chart(wb, p):
    ws = wb.create_sheet("Load chart")
    for c, h in enumerate(["Week", "Load %", "Volume (1-3)", "Intensity (1-3)"], 1):
        _t(ws, 1, c, h, bold=True, fill=SUB)
    for w in range(p["weeks"]):
        r = w + 2
        _t(ws, r, 1, f"W{w + 1}" + (f" {p['comp_week'][w]}" if p["comp_week"][w] else ""))
        _f(ws, r, 2, f"='Week data'!H{r}", fmt="0%")
        _f(ws, r, 3, f"='Week data'!I{r}")
        _f(ws, r, 4, f"='Week data'!J{r}")
    # The charts read cells that hold NUMBERS (the Annual plan's load row, the Week data volume / intensity levels), not the
    # formulas in the table above: a formula has no value until the spreadsheet recalculates, and a file opened in Protected View,
    # a phone preview or a viewer that does not recalculate would show an empty chart.
    n, W = p["weeks"] + 1, p["weeks"]
    cats = Reference(ws, min_col=1, min_row=2, max_row=n)
    lc = LineChart()
    lc.title, lc.y_axis.title, lc.height, lc.width = "Weekly load % (competition weeks labelled)", "Load %", 9, 30
    lc.add_data(Reference(wb["Annual plan"], min_col=1, max_col=W + 1, min_row=13, max_row=13), from_rows=True, titles_from_data=True)
    lc.set_categories(cats)
    lc.y_axis.number_format, lc.y_axis.scaling.min, lc.y_axis.scaling.max = "0%", 0, 1
    lc.y_axis.delete = lc.x_axis.delete = False
    ws.add_chart(lc, "F2")
    bc = BarChart()
    bc.title, bc.y_axis.title, bc.height, bc.width = "Volume vs intensity by week (1 low, 2 medium, 3 high)", "Level", 9, 30
    bc.add_data(Reference(wb["Week data"], min_col=9, max_col=10, min_row=1, max_row=n), titles_from_data=True)
    bc.set_categories(cats)
    bc.y_axis.scaling.min, bc.y_axis.scaling.max = 0, 3
    bc.y_axis.delete = bc.x_axis.delete = False
    ws.add_chart(bc, "F22")


def _methods(wb):
    ws = wb.create_sheet("Methods by phase")
    heads = ["Group", "Method", "Work:rest / load"] + pp.METHOD_PHASES
    letters = "GBSPMT"
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True)
        ws.column_dimensions[L(c)].width = [20, 36, 52, 13, 14, 14, 15, 13, 12][c - 1]
    for r, (g, m, note, ph) in enumerate(pp.METHODS, 2):
        _t(ws, r, 1, g)
        _t(ws, r, 2, m)
        _t(ws, r, 3, note)
        for i, l in enumerate(letters):
            if l in ph:
                _t(ws, r, 4 + i, "x", align=CENTER)
    t = Table(displayName="MethodsByPhase", ref=f"A1:{L(len(heads))}{len(pp.METHODS) + 1}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(t)
    _t(ws, len(pp.METHODS) + 3, 1, "Order through the year: general to specific, long to short (aerobic base, long intervals, short intervals, sprints).")


META = {  # code -> (targets, methods, expected adaptations)
    "H": ("Hypertrophy / strength-endurance; aerobic base; technique: batting and bowling basics",
          "Repeated-effort resistance (youth: not to failure), continuous and tempo runs, 300 m intervals, low plyometrics",
          "Muscle and tendon tolerance, movement quality, aerobic base"),
    "B": ("Maximal strength (submaximal effort); aerobic-anaerobic; technique: fielding and throwing",
          "Submaximal-effort resistance, 300 / 150 m intervals, moderate plyometrics", "Strength, work capacity"),
    "S": ("Power; speed; technique: advanced skills under pressure",
          "Dynamic-effort and submaximal resistance, 150 / 120 m intervals, 30 m sprints, moderate-high plyometrics", "Power, speed, specific fitness"),
    "U": ("Unloading; then speed and competition readiness", "Reduced volume, intensity kept; short sprints", "Fatigue dissipates, gains appear (delayed transformation)"),
    "P": ("Competition readiness; match skills", "Short sprints, competition technique, game plans; short strength (no squats 10-12 days out)",
          "Peak performance at the MAIN competition"),
    "M": ("Retain strength and power; match skills", "2 short strength sessions, short sprints, practice", "Fitness retained through the season"),
    "T": ("Recovery; recreational activity", "Games, swimming, easy runs", "Physical and mental recovery; body weight kept"),
}


def _mesocycles(wb, p, wd_last) -> dict:
    ws = wb.create_sheet("Mesocycles")
    heads = ["Meso #", "Macro", "Type", "Phase(s)", "First week", "Last week", "Weeks", "Start", "End", "Loading pattern", "Targets",
             "Methods", "Exercise complex", "Planned tests", "Expected adaptations", "Weekly volume target", "Average intensity",
             "Sessions a week", "Max load", "Min load", "Average load", "Lightest / heaviest", "Unloading week OK", "Shorter toward competition",
             "Preparatory", "Taper", "Taper weeks required"]
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[L(c)].width = 30 if c in (11, 12, 13, 15, 16) else 12
    mesos = p["mesos"]
    rn = len(mesos) + 1
    wd = f"'Week data'!$H$2:$H${wd_last}"
    wf = f"'Week data'!$F$2:$F${wd_last}"
    for i, m in enumerate(mesos):
        r = i + 2
        code = m["codes"][0] if m["codes"][0] != "U" else "U"
        main = m["codes"][-1] if code == "U" else code
        n = len(m["codes"])
        cx = pp.COMPLEX_FOR[main]
        ws_ = [w for w in range(m["first"], m["last"] + 1)]
        metres = max(sum(x["distance"] * x["reps"] for x in p["conditioning"][w]) for w in ws_)
        tests = ", ".join(f"week {w + 1}" for w in ws_ if p["test_due"][w])
        res = [x for x in p["resistance"] if x["meso"] == m["no"]]
        pct = max((x["pct"] for x in res if x["pct"]), default=None)
        sp = max((x["speed"] for w in ws_ for x in p["conditioning"][w]), default=0)
        sess = pp.SESSIONS[main]
        vals = [m["no"], m["macro"], m["type"], " + ".join(dict.fromkeys(pp.PHASES[c][1] for c in m["codes"])), m["first"] + 1, m["last"] + 1, None, None, None,
                pp.LOADING_PATTERN.get(n, f"{n} weeks") if main in pp.PREP else ("taper" if m.get("taper") else "-"),
                META[main][0], META[main][1], (f"Complex {cx}: " + ", ".join(e[0] for e in pp.COMPLEXES[cx])) if cx else "None (active rest)",
                ("Field tests (SOP) " + tests) if tests else "-", META[main][2],
                f"up to {metres} m running; {pp.PLYO_CONTACTS[main]} contacts a plyometric session"
                + (f"; resistance {res[0]['sets']} x {res[0]['reps']}" if res else ""),
                (f"{int(pct * 100)}% 1RM; " if pct else "") + f"up to {int(sp * 100)}% max speed", f"{sess[0]} resistance, {sess[3]} conditioning, {sess[4]} practice"]
        for c, v in enumerate(vals, 1):
            if v is not None:
                _t(ws, r, c, v, align=WRAP)
        _f(ws, r, 7, f"=F{r}-E{r}+1")
        _f(ws, r, 8, f"=INDEX('Week data'!$B$2:$B${wd_last},E{r})", fmt="dd-mmm-yy")
        _f(ws, r, 9, f"=INDEX('Week data'!$B$2:$B${wd_last},F{r})+6", fmt="dd-mmm-yy")
        _f(ws, r, 19, f"=_xlfn.MAXIFS({wd},{wf},A{r})", fmt="0%")
        _f(ws, r, 20, f"=_xlfn.MINIFS({wd},{wf},A{r})", fmt="0%")
        _f(ws, r, 21, f"=AVERAGEIFS({wd},{wf},A{r})", fmt="0%")
        _f(ws, r, 22, f"=T{r}/S{r}", fmt="0%")
        prep = int(main in pp.PREP)
        _t(ws, r, 25, prep)
        _f(ws, r, 23, f"=IF(AND(Y{r}=1,G{r}>1),INDEX({wd},F{r})<S{r},TRUE)")
        if r < rn:
            _f(ws, r, 24, f"=IF(AND(Y{r}=1,Y{r + 1}=1,B{r + 1}=B{r}),G{r + 1}<=G{r},TRUE)")
        else:
            _f(ws, r, 24, "=TRUE")
        _t(ws, r, 26, int(bool(m.get("taper"))))
        if m.get("taper"):
            _t(ws, r, 27, pp.TAPER_FOR_RISE[pp.LOAD_RISE] if not m.get("mini") else 3)
    ws.freeze_panes = "B2"
    return {"last": rn}


def _microcycles(wb, p) -> dict:
    ws = wb.create_sheet("Microcycles")
    heads = ["Template", "Day", "AM", "PM", "Content", "Load", "Day load %", "Restoration", "Heavy lower body", "Plyometrics", "Match",
             "Passive rest", "Rest run", "Matches in next 2 days", "No heavy legs within 48 h", "Plyo 48 h apart", "Season"]
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[L(c)].width = [34, 8, 26, 40, 46, 9, 10, 20, 9, 9, 7, 8, 8, 9, 11, 10, 10][c - 1]
    r = 2
    for mc in p["microcycles"]:
        season = "In season" if mc["phase"].startswith(("Maintenance", "Peaking")) else "-"
        for d in mc["days"]:
            vals = [mc["name"], d["day"], d["am"], d["pm"], d["content"], d["load"], d["pct"] / 100, d["restoration"], d["heavy_legs"],
                    d["plyo"], d["match"], d["off"]]
            for c, v in enumerate(vals, 1):
                cell = _t(ws, r, c, v, align=WRAP)
            ws.cell(row=r, column=7).number_format = "0%"
            _f(ws, r, 13, f"=IF(L{r}=1,IF(A{r - 1}=A{r},M{r - 1}+1,1),0)" if r > 2 else f"=L{r}")
            _f(ws, r, 14, f"=IF(A{r + 1}=A{r},K{r + 1},0)+IF(A{r + 2}=A{r},K{r + 2},0)")
            _f(ws, r, 15, f"=NOT(AND(I{r}=1,N{r}>0))")
            _f(ws, r, 16, f"=NOT(AND(J{r}=1,A{r + 1}=A{r},J{r + 1}=1))")
            _t(ws, r, 17, season)
            r += 1
    last = r - 1
    r += 1
    _t(ws, r, 1, "Template", bold=True, fill=SUB)
    _t(ws, r, 2, "Lightest / heaviest training day", bold=True, fill=SUB)
    _t(ws, r, 3, "Plyometric sessions", bold=True, fill=SUB)
    _t(ws, r, 4, "Longest passive rest (days)", bold=True, fill=SUB)
    first_sum = r + 1
    for mc in p["microcycles"]:
        r += 1
        _t(ws, r, 1, mc["name"])
        _f(ws, r, 2, f'=_xlfn.MINIFS($G$2:$G${last},$A$2:$A${last},A{r},$G$2:$G${last},">0")/_xlfn.MAXIFS($G$2:$G${last},$A$2:$A${last},A{r})', fmt="0%")
        _f(ws, r, 3, f"=SUMIFS($J$2:$J${last},$A$2:$A${last},A{r})")
        _f(ws, r, 4, f"=_xlfn.MAXIFS($M$2:$M${last},$A$2:$A${last},A{r})")
    _t(ws, r + 2, 1, "Rules: heavy days alternate with light days; the lightest training day is about 60% of the heaviest; large-muscle heavy work 48 h "
                     "apart; speed, power and maximal strength when fresh (start of the session); in season no heavy lower-body work within 48 h "
                     "before a match, a recovery session the day after, main strength 2-3 days after the match. A tournament microcycle matches the "
                     "tournament's length.", align=WRAP)
    return {"last": last, "sum": (first_sum, r)}


def _conditioning(wb, p) -> int:
    ws = wb.create_sheet("Conditioning detail")
    heads = ["Week", "Week start", "Phase", "Method", "Energy system", "Distance (m)", "Reps", "% max speed", "Work (s)", "Rest (s)",
             "Work:rest", "W:R min", "W:R max", "W:R OK", "Metres"]
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[L(c)].width = [7, 11, 26, 28, 24, 11, 6, 10, 8, 8, 10, 8, 8, 8, 9][c - 1]
    r = 2
    for w, rows in enumerate(p["conditioning"]):
        for x in rows:
            _t(ws, r, 1, w + 1)
            _f(ws, r, 2, f"='Week data'!B{w + 2}", fmt="dd-mmm-yy")
            _t(ws, r, 3, pp.PHASES[p["codes"][w]][1])
            _t(ws, r, 4, x["method"])
            _t(ws, r, 5, x["system"] if not x["continuous"] else "Oxidative (continuous)")
            for c, v in ((6, x["distance"]), (7, x["reps"]), (9, x["work_s"]), (10, x["rest_s"]), (12, x["wr_lo"]), (13, x["wr_hi"])):
                ws.cell(row=r, column=c, value=v)
            ws.cell(row=r, column=8, value=x["speed"]).number_format = "0%"
            if x["continuous"]:
                _t(ws, r, 11, "continuous")
                _f(ws, r, 14, "=TRUE")
            else:
                _f(ws, r, 11, f'="1:"&TEXT(J{r}/I{r},"0.0")')
                _f(ws, r, 14, f"=AND(J{r}/I{r}>=L{r},J{r}/I{r}<=M{r})")
            _f(ws, r, 15, f"=F{r}*G{r}")
            r += 1
    _t(ws, r + 1, 1, f"Bout times are estimated from an assumed U15 maximal speed of {pp.MAX_SPEED} m/s. Weekly totals: Week data, column T "
                     "(SUMPRODUCT of distance and reps). Volume never rises more than 10% on the previous loading week.")
    ws.freeze_panes = "A2"
    return r - 1


def _resistance(wb, p) -> int:
    ws = wb.create_sheet("Resistance detail")
    heads = ["Meso #", "Complex", "Exercise", "Category", "Load type", "Sets", "Reps (or s)", "% 1RM", "Rest (s)", "Body-mass ratio",
             "Est. 1RM / load (kg)", "Volume load (kg)", "Max reps at % 1RM", "Reps within table", "Player focus"]
    for c, h in enumerate(heads, 1):
        _t(ws, 1, c, h, bold=True, fill=SUB, align=CENTER)
        ws.column_dimensions[L(c)].width = [7, 8, 38, 9, 9, 6, 9, 8, 8, 10, 12, 12, 10, 10, 18][c - 1]
    r = 2
    for x in p["resistance"]:
        for c, v in ((1, x["meso"]), (2, x["complex"]), (3, x["exercise"]), (4, x["category"]), (5, x["load_type"]), (6, x["sets"]),
                     (7, x["reps"]), (9, x["rest"]), (10, x["ratio"])):
            _t(ws, r, c, v)
        if x["pct"]:
            ws.cell(row=r, column=8, value=x["pct"]).number_format = "0%"
            ws.cell(row=r, column=13, value=pp.max_reps(x["pct"]))
        _f(ws, r, 11, f'=IF(OR(E{r}="%1RM",E{r}="BW"),RefBodyMass*J{r},"")', fmt="0.0")
        _f(ws, r, 12, f'=IF(E{r}="%1RM",F{r}*G{r}*H{r}*K{r},IF(E{r}="BW",F{r}*G{r}*K{r},0))', fmt="0")
        _f(ws, r, 14, f'=IF(H{r}="",TRUE,G{r}<=M{r})')
        if x.get("extra"):
            _t(ws, r, 15, "+1 set (focus area)")
        r += 1
    _t(ws, r + 1, 1, "U15: the 1RM is ESTIMATED (reference body mass x ratio) - never tested maximally. Replace RefBodyMass on Inputs, or the "
                     "estimates per player. Change the exercise complex every 2-4 months (A general, B basic strength, C specific and taper, "
                     "D in-season).")
    ws.freeze_panes = "A2"
    return r - 1


def _week_for(p, kind):
    codes, W = p["codes"], p["weeks"]
    if kind == "tournament":
        return next((w for w in range(W) if p["tournament"][w]), None)
    if kind == "taper":
        return next((m["first"] + 1 for m in p["mesos"] if m.get("taper") and len(m["codes"]) > 1), None)
    code = {"general": "H", "specific": "S", "inseason": "M", "transition": "T"}[kind]
    return next((w for w in range(W) if codes[w] == code), None)


def _sessions(wb, p) -> dict:
    ws = wb.create_sheet("Session plans")
    for c, wdt in enumerate([16, 46, 6, 10, 14, 9, 8, 8, 9, 34, 9, 9, 11, 7, 7, 9, 9, 12], 1):
        ws.column_dimensions[L(c)].width = wdt
    kinds = ["general", "specific", "taper", "inseason", "tournament", "transition"]
    r = 1
    for s, kind in zip(p["session_plans"], kinds):
        w = _week_for(p, kind)
        m = p["meso_of"][w] if w is not None else None
        _t(ws, r, 1, s["name"].upper(), bold=True, fill=HEAD, white=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=12)
        r += 1
        head = [("Team", f"{p['squad']} ({p['age_group']})"),
                ("Week of", f"=INDEX('Week data'!$B$2:$B${p['weeks'] + 1},{w + 1})" if w is not None else "no such week in this plan"),
                ("Microcycle #", w + 1 if w is not None else "-"), ("Mesocycle", f"Meso {m['no']} - {m['type']}" if m else "-"),
                ("Period / phase", f"{pp.PHASES[p['codes'][w]][0]} / {pp.PHASES[p['codes'][w]][1]}" if w is not None else "-"),
                ("Microcycle template", s["micro"]), ("Session goal", s["goal"]), ("Equipment", s["equipment"]), ("Intensity range", s["intensity"]),
                ("Coach : athlete", pp.COACH_RATIO)]
        for k, v in head:
            _t(ws, r, 1, k, bold=True)
            if isinstance(v, str) and v.startswith("="):
                _f(ws, r, 2, v, fmt="dd-mmm-yyyy", align=Alignment(horizontal="left"))
            else:
                _t(ws, r, 2, v)
            r += 1
        _t(ws, r, 1, "Planned duration (min)", bold=True)
        ws.cell(row=r, column=2, value=s["duration"])
        dur_row = r
        r += 1
        cols = ["Part", "Exercise", "Sets", "Reps / time", "Load", "Tempo", "Work (s)", "Rest (s)", "Minutes", "Organisation / cues",
                "Order category", "Order OK", "Rest goal", "Rest min", "Rest max", "Rest OK"]
        for c, h in enumerate(cols, 1):
            _t(ws, r, c, h, bold=True, fill=SUB, align=CENTER)
        r += 1
        first = r
        for x in s["rows"]:
            for c, v in ((1, x["part"]), (2, x["exercise"]), (3, x["sets"]), (4, x["reps"]), (5, x["load"]), (6, x["tempo"]), (7, x["work"]),
                         (8, x["rest"]), (10, x["cues"]), (11, x["cat"])):
                _t(ws, r, c, v)
            _f(ws, r, 9, f"=C{r}*(G{r}+H{r})/60", fmt="0.0")
            _f(ws, r, 12, f'=IF(AND(A{r}="Main",A{r - 1}="Main"),K{r}>=K{r - 1},TRUE)')
            if x["goal"]:
                lo, hi = pp.REST_BY_GOAL[x["goal"]]
                _t(ws, r, 13, x["goal"])
                ws.cell(row=r, column=14, value=lo)
                ws.cell(row=r, column=15, value=hi)
                _f(ws, r, 16, f"=AND(H{r}>=N{r},H{r}<=O{r})")
            else:
                _f(ws, r, 16, "=TRUE")
            r += 1
        _t(ws, r, 8, "Total", bold=True)
        _f(ws, r, 9, f"=SUM(I{first}:I{r - 1})", fmt="0")
        _t(ws, r, 10, "Time check (total within 5 min of the planned duration)", bold=True)
        _f(ws, r, 18, f'=IF(ABS(I{r}-B{dur_row})<=5,"PASS","FAIL")')
        r += 3
    _t(ws, r, 1, "Order: speed / agility / power first (fresh), plyometrics, power lifts, core strength lifts, assistance, trunk, conditioning last. "
                 "Same reps every set (no pyramids). Warm-up RAMP: raise, activate and mobilise, potentiate; dynamic stretching before, static "
                 "(15-30 s) after. Progress with the 2-for-2 rule. Spot overhead, over-face and bar-on-back lifts; never spot power cleans.", align=WRAP)
    return {"last": r}


# fixes applied while building the generator (Phase 10: rule -> fix)
FIXES = {
    2: "A 1-week first transition before a league is folded into the last specific mesocycle (its unloading week).",
    3: "Mesocycles are sized together (4, 4, 3 weeks); leftover weeks lengthen the first specific mesocycles, never a later one.",
    4: "A league final gets a 3-week realization block (2 lighter weeks + the final).",
    16: "Volume rounding changed so the continuous run takes the remaining metres (100 m steps); unloading weeks capped at 65%.",
    20: "Plyometric drills get their own rest range (45-180 s); trunk holds rest 30 s.",
}


def _checks(wb, p, wd_last, meso, micro, cond_last, res_last, sess):
    ws = wb.create_sheet("Checks")
    for c, (h, wdt) in enumerate([("#", 4), ("Rule", 62), ("Result", 10), ("How it is checked", 70), ("Python check", 12), ("Fix applied", 50)], 1):
        _t(ws, 1, c, h, bold=True, fill=SUB)
        ws.column_dimensions[L(c)].width = wdt
    WD = lambda col: f"'Week data'!{col}2:{col}{wd_last}"
    MS = lambda col: f"Mesocycles!{col}2:{col}{meso['last']}"
    MC = lambda col: f"Microcycles!{col}2:{col}{micro['last']}"
    ms1, ms2 = micro["sum"]
    to = p["_test_order"]
    ap_last = L(p["weeks"] + 1)
    rows = [
        ("Every week has a period, phase, mesocycle and microcycle; months are labelled Month",
         f"=IF(AND(COUNTBLANK({WD('C')})=0,COUNTBLANK({WD('D')})=0,COUNTBLANK({WD('F')})=0,COUNT('Annual plan'!B6:{ap_last}6)=Weeks,'Annual plan'!A5=\"Month\"),\"PASS\",\"FAIL\")",
         "No blank period, phase or mesocycle; one microcycle number a week; row 5 is called Month."),
        ("Each mesocycle is 2-6 weeks", f"=IF(AND(MIN({MS('G')})>=2,MAX({MS('G')})<=6),\"PASS\",\"FAIL\")", "Mesocycles, Weeks column."),
        ("Mesocycles get shorter toward competition", f"=IF(COUNTIF({MS('X')},FALSE)=0,\"PASS\",\"FAIL\")",
         "Each preparatory mesocycle is no longer than the one before it in the same macrocycle."),
        ("A realization block (taper) sits directly before each MAIN competition",
         f"=IF(COUNTIFS({WD('M')},1,{WD('N')},0)=0,\"PASS\",\"FAIL\")", "The week before each MAIN start is in a realization mesocycle."),
        ("Taper length matches the size of the load rise", f"=IF(SUMPRODUCT(({MS('Z')}=1)*({MS('G')}<>{MS('AA')}))=0,\"PASS\",\"FAIL\")",
         "Normal rise (no stress microcycles) -> 4 weeks (TaperWeeks); before a league final 2 weeks + the final."),
        ("Peak load in the last specific-preparation mesocycle, before the taper",
         f"=IF(INDEX({WD('E')},MATCH(MAX({WD('H')}),{WD('H')},0))=\"S\",\"PASS\",\"FAIL\")", "The heaviest week is a specific-preparation week."),
        ("Step loading: every preparatory mesocycle ends with an unloading week", f"=IF(COUNTIF({MS('W')},FALSE)=0,\"PASS\",\"FAIL\")",
         "The last week of each preparatory mesocycle is lighter than its heaviest week (3:1, 2:1)."),
        ("Rule of 60% for days, weeks and mesocycles",
         f"=IF(AND(COUNTIFS({MS('C')},\"<>Transition\",{MS('V')},\"<0.6\")=0,_xlfn.MINIFS({MS('U')},{MS('C')},\"<>Transition\")/MAX({MS('U')})>=0.6,"
         f"COUNTIF(Microcycles!B{ms1}:B{ms2},\"<0.6\")=0),\"PASS\",\"FAIL\")",
         "Lightest/heaviest week in each mesocycle, lightest/heaviest mesocycle average (transition excepted), lightest/heaviest training day."),
        ("Volume, Intensity and Load text agree with the load %; volume falls as intensity rises",
         f"=IFERROR(IF(AND(SUMPRODUCT(--({WD('K')}<>{WD('AD')}))=0,AVERAGEIFS({WD('I')},{WD('E')},\"H\")>AVERAGEIFS({WD('I')},{WD('E')},\"S\"),"
         f"AVERAGEIFS({WD('J')},{WD('E')},\"H\")<AVERAGEIFS({WD('J')},{WD('E')},\"S\")),\"PASS\",\"FAIL\"),\"FAIL\")",
         "Load = High from 75%, Medium from 50%; general prep has more volume and less intensity than specific prep."),
        ("At most 3 factors at level 3 in any week", f"=IF(MAX({WD('R')})<=3,\"PASS\",\"FAIL\")", "COUNTIF of level 3 in each week's factor column."),
        ("Strength is retained in-season", f"=IF(AND(COUNTIFS({WD('C')},\"Competition\",{WD('Q')},\"<2\")=0,COUNTIFS({WD('C')},\"Competition\",{WD('AF')},0)=0),\"PASS\",\"FAIL\")",
         "Competition weeks: 2 or more short resistance sessions; maximal strength at level 1 or more."),
        ("Technical and tactical work continue through competition", f"=IF(COUNTIFS({WD('C')},\"Competition\",{WD('S')},0)=0,\"PASS\",\"FAIL\")",
         "Technical + tactical levels never 0 in competition weeks."),
        ("No heavy lower-body work in the last 10-12 days before a MAIN competition", f"=IF(COUNTIFS({WD('O')},\"<=12\",{WD('P')},1)=0,\"PASS\",\"FAIL\")",
         "Weeks ending 12 days or less before a MAIN start have no heavy lower-body work."),
        ("No heavy legs within 48 h of a match", f"=IF(COUNTIF({MC('O')},FALSE)=0,\"PASS\",\"FAIL\")", "Microcycles: a heavy lower-body day never has a match in the next 2 days."),
        ("Stress microcycles: none for youth (3-4 a year at most otherwise)", f"=IF(OR(AND(Youth,SUM({WD('X')})=0),AND(NOT(Youth),SUM({WD('X')})<=4)),\"PASS\",\"FAIL\")", ""),
        ("Conditioning volume rises at most 10% a week", f"=IF(COUNTIFS({WD('W')},1,{WD('V')},\">0.1001\")=0,\"PASS\",\"FAIL\")",
         "Each loading week against the previous loading week inside a training block (unloading weeks are lower)."),
        ("Work:rest matches the target energy system", f"=IF(COUNTIF('Conditioning detail'!N2:N{cond_last},FALSE)=0,\"PASS\",\"FAIL\")",
         "Phosphagen 1:12-1:20, fast glycolysis 1:3-1:5, glycolysis + oxidative 1:3-1:4."),
        ("Plyometric contacts within the limit; 48-72 h between sessions",
         f"=IF(AND(MAX({WD('Y')})<=PlyoMax,MAX({WD('AE')})<=3,COUNTIF({MC('P')},FALSE)=0),\"PASS\",\"FAIL\")", "Contacts a session <= PlyoMax; at most 3 a week, never on consecutive days."),
        ("Tests in the NSCA order and at the right points",
         f"=IF(AND(SUMPRODUCT(--(Inputs!C{to[0] + 1}:C{to[1]}<=Inputs!C{to[0]}:C{to[1] - 1}))=0,COUNTIFS({WD('AA')},1,{WD('Z')},\"<>x\")=0),\"PASS\",\"FAIL\")",
         "Inputs test order ascends; every due test week (baseline, end of each phase, before the taper, in-season) has a Field mark."),
        ("Session order, rest by goal, no pyramids, session time adds up",
         f"=IF(AND(COUNTIF('Session plans'!L1:L{sess['last']},FALSE)=0,COUNTIF('Session plans'!P1:P{sess['last']},FALSE)=0,"
         f"COUNTIF('Session plans'!R1:R{sess['last']},\"FAIL\")=0),\"PASS\",\"FAIL\")", "Main-part order categories ascend; rests fit the goal; minutes add up."),
        ("No passive rest over 3 days in season; transition 1-4 weeks",
         f"=IF(AND(_xlfn.MAXIFS({MC('M')},{MC('Q')},\"In season\")<=3,COUNTIFS({MS('C')},\"Transition\",{MS('G')},\">4\")=0),\"PASS\",\"FAIL\")", ""),
        ("All totals are formulas and the sheets agree",
         f"=IF(AND(ABS(SUM({WD('H')})-SUM('Annual plan'!B13:{ap_last}13))<0.0001,SUM({WD('T')})=SUM('Conditioning detail'!O2:O{cond_last})),\"PASS\",\"FAIL\")",
         "Week data load = Annual plan load row; weekly metres = the conditioning rows."),
        ("Resistance loads within the %1RM / max-reps table", f"=IF(COUNTIF('Resistance detail'!N2:N{res_last},FALSE)=0,\"PASS\",\"FAIL\")", ""),
        ("Youth rules applied", f"=IF(OR(NOT(Youth),AND(SUM({WD('X')})=0,MAX({WD('Q')})<=3)),\"PASS\",\"FAIL\")",
         "No stress microcycles; resistance 3 a week at most; estimated 1RM; technique first."),
    ]
    py = [ok for _, ok, _ in pp.verify(p)]
    py_index = [0, 1, 2, 3, 4, 5, 7, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, None, 21, 22]   # verify() order -> these rows
    for i, (rule, formula, how) in enumerate(rows, 2):
        _t(ws, i, 1, i - 1)
        _t(ws, i, 2, rule, align=WRAP)
        _f(ws, i, 3, formula)
        _t(ws, i, 4, how, align=WRAP)
        k = py_index[i - 2]
        _t(ws, i, 5, "n/a" if k is None else ("PASS" if py[k] else "FAIL"))
        _t(ws, i, 6, FIXES.get(i - 1, ""), align=WRAP)
    n = len(rows) + 1
    ws.conditional_formatting.add(f"C2:C{n}", CellIsRule(operator="equal", formula=['"PASS"'], fill=PatternFill("solid", fgColor="C6EFCE")))
    ws.conditional_formatting.add(f"C2:C{n}", CellIsRule(operator="equal", formula=['"FAIL"'], fill=PatternFill("solid", fgColor="FFC7CE")))
    _t(ws, n + 2, 2, "Overall", bold=True)
    _f(ws, n + 2, 3, f'=IF(COUNTIF(C2:C{n},"PASS")={len(rows)},"ALL PASS",COUNTIF(C2:C{n},"FAIL")&" FAIL")')
    _t(ws, n + 4, 2, "What the coach must monitor: test results against targets; RPE and wellness; overtraining signs (performance drop, mood, "
                     "sleep, resting heart rate); efficacy (did the players perform best at the MAIN competition: ~75% excellent, 60% good, 50% acceptable). "
                     "Adjust: a test short of target -> extend the mesocycle or change the exercise complex; too much fatigue -> insert an unloading "
                     "week; an injury -> refer to the medical staff and rework the plan.", align=WRAP)


def build_workbook(p: dict) -> bytes:
    wb = Workbook()
    p["_test_order"] = _inputs(wb, p)["test_order"]
    ap = _annual(wb, p)
    wd_last = _week_data(wb, p, ap)
    _load_chart(wb, p)
    _methods(wb)
    meso = _mesocycles(wb, p, wd_last)
    micro = _microcycles(wb, p)
    cond_last = _conditioning(wb, p)
    res_last = _resistance(wb, p)
    sess = _sessions(wb, p)
    _checks(wb, p, wd_last, meso, micro, cond_last, res_last, sess)
    wb.calculation.fullCalcOnLoad = True
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
