"""The squad's Physical page as one workbook: Heat map, Today, S&C groups, Targets, Progress, Growth. Text is stored as text."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

BLUE, RED, GREEN, GREY = "1F4E79", "F8D7D5", "D5EFDF", "F2F2F2"


def _s(ws, r, c, v, *, bold=False, fill=None, white=False, wrap=False):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"
    cell.font = Font(name="Calibri", size=11, bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    return cell


def _table(ws, r, head, rows, widths=None):
    for i, h in enumerate(head, 1):
        _s(ws, r, i, h, bold=True, fill=BLUE, white=True, wrap=True)
    for row in rows:
        r += 1
        for i, v in enumerate(row, 1):
            fill = None
            if isinstance(v, tuple):                                 # (value, fill)
                v, fill = v
            _s(ws, r, i, v, fill=fill, wrap=isinstance(v, str) and len(v) > 30)
    for i, w in enumerate(widths or [], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    return r + 2


def _rank(v):
    if v is None:
        return ("-", None)
    return (round(v), RED if v < 50 else GREEN if v >= 70 else None)


def build_physical_report(squad: str, d: dict, results: dict | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Heat map"
    x = d["dashboard"]
    _s(ws, 1, 1, f"PHYSICAL REPORT - {squad} - {d['season']['name']} - {d['window_label']}", bold=True)
    _s(ws, 2, 1, f"Tested {x['tested']} of {x['squad_size']}. Rank in level, 100 = best: red below 50 (priority), green 70+ (strength). Not a pass or fail mark.")
    r = _table(ws, 4, ["Player", "Role", "Band", *[a["label"] for a in x["areas"]], "Priorities"],
               [[row["name"], row["role"].replace("_", " "), f"{row['band']} {row['band_label']}" if row["band"] else "-",
                 *[_rank(row["areas"].get(a["area"])) for a in x["areas"]], ", ".join(row["priorities"]) or "-"] for row in x["rows"]],
               [26, 16, 16] + [12] * len(x["areas"]) + [40])
    if x["untested"]:
        _s(ws, r, 1, "Not tested: " + ", ".join(x["untested"]))
        r += 2
    r = _table(ws, r, ["Area", "Tested", "Priority", "Strength", "Weakest area for"],
               [[s["label"], s["tested"], s["priority"], s["strength"], s["weakest_first"]] for s in x["summary"]])
    if x["pace"]:
        _table(ws, r, ["Fast bowler", "Endurance", "Core", "Leg power", "Speed", "Watch"],
               [[p["name"], _rank(p["endurance"]), _rank(p["core"]), _rank(p["power"]), _rank(p["speed"]), ", ".join(p["watch"]) or "OK"] for p in x["pace"]])

    ws = wb.create_sheet("Today")
    t = d["today"]
    _s(ws, 1, 1, f"S&C TODAY - {t['date']}", bold=True)
    _table(ws, 3, ["Player", "Today", "Why", "Notes"], [[p["name"], p["label"], " ".join(p["reasons"]), " ".join(p["notes"])] for p in t["players"]],
           [26, 30, 60, 50])

    ws = wb.create_sheet("S&C groups")
    r = 1
    for g in d["groups"]:
        _s(ws, r, 1, f"{g['label']} ({len(g['players'])}): " + ", ".join(p["name"] for p in g["players"]), bold=True, fill=GREY)
        r += 1
        s = g.get("session")
        if s:
            _s(ws, r, 1, f"{s['phase_label']} session, about {s['minutes']} min" + (f" - also covers {s['second_focus']}" if s.get("second_focus") else ""))
            r = _table(ws, r + 1, ["Part", "Exercise", "Area", "Sets", "Reps / time", "Rest"],
                       [[pt["part"] if i == 0 else "", it["name"], it.get("area_label", ""), it.get("set", ""), it.get("rep") or it.get("time") or "", it.get("rest", "")]
                        for pt in s["parts"] for i, it in enumerate(pt["items"])], [26, 40, 20, 8, 20, 22])
        else:
            r += 1

    ws = wb.create_sheet("Targets")
    rows = [[p["name"], t_["area"], t_["test"], t_["current"], t_["target"], t_["unit"], t_["latest"] or "-",
             ("Reached", GREEN) if t_["reached"] else ("Not yet", RED) if t_["reached"] is False else "-"]
            for p in d["targets"] for t_ in p["targets"]]
    _s(ws, 1, 1, "TARGETS FOR THE NEXT TEST (priority areas, weakest test)", bold=True)
    _table(ws, 3, ["Player", "Area", "Test", "Now", "Target", "Unit", "Latest", "Result"], rows, [26, 20, 22, 10, 10, 8, 10, 10])

    ws = wb.create_sheet("Progress")
    p = d["progress"]
    _s(ws, 1, 1, d["retest"]["text"], bold=True)
    fills = {"improved": GREEN, "declined": RED}
    _table(ws, 3, ["Player", *[f"{t_['label']} ({t_['unit']})" for t_ in p["tests"]], "Improved", "Band"],
           [[row["name"], *[(row["cells"][t_["key"]]["text"], fills.get(row["cells"][t_["key"]]["state"])) for t_ in p["tests"]],
             f"{row['improved']} of {row['compared']}" if row["compared"] else "-", row["band"] or "-"] for row in p["rows"]],
           [26] + [16] * len(p["tests"]) + [10, 20])

    ws = wb.create_sheet("Growth")
    _table(ws, 1, ["Player", "Height (cm)", "Mass (kg)", "BMI", "Growth (cm/yr)", "Stage"],
           [[g["name"], g["height_cm"] or "-", g["weight_kg"] or "-", g["bmi"] or "-", g["velocity_cm_yr"] if g["velocity_cm_yr"] is not None else "-", g["stage_label"]]
            for g in d["growth"]], [26, 12, 12, 8, 14, 26])
    if results is not None:                                      # every result of the window, sit and reach and skinfolds included
        from app.exports.excel.test_results_excel import write_squad_tests_sheet
        write_squad_tests_sheet(wb.create_sheet("Test results"), results)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
