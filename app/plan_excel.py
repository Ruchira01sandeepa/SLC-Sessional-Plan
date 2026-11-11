"""Excel export of the seasonal plan (openpyxl). Text is always stored as text, never as a formula."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

STATUS_LABEL = {"not_started": "Not started", "in_progress": "In progress", "achieved": "Achieved", "revised": "Revised", "dropped": "Dropped"}
GREEN, LIGHT, GREY = "1F5C46", "E8F0EB", "F4F5F2"
_thin = Side(style="thin", color="C9CFC9")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
WRAP = Alignment(wrap_text=True, vertical="top")
AREA_FILL = {"technical": "DCEBFA", "tactical": "E9E2F5", "physical": "FDE9D3", "mental": "E3F2E1", "nutrition": "FFF4CC", "recovery": "F8DCDC"}


def _put(ws, r, c, v, *, bold=False, fill=None, color=None, size=None, wrap=True, border=True, fmt=None, align=None):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"                      # never let text that starts with "=" become a formula
    if isinstance(v, date):
        cell.number_format = fmt or "d mmm yyyy"
    cell.font = Font(bold=bold, color=color, size=size or 11)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = align or (WRAP if wrap else Alignment(vertical="top"))
    if border:
        cell.border = BORDER
    return cell


def _header(ws, r, labels, widths=None):
    for i, lab in enumerate(labels, 1):
        _put(ws, r, i, lab, bold=True, fill=GREEN, color="FFFFFF", align=Alignment(wrap_text=True, vertical="center"))
        if widths:
            ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.row_dimensions[r].height = 30


def _title(ws, text, sub=None):
    _put(ws, 1, 1, text, bold=True, size=15, border=False, wrap=False)
    if sub:
        _put(ws, 2, 1, sub, color="5B675F", border=False, wrap=False)


def _print(ws, landscape=True):
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = False


def build_workbook(plan: dict) -> bytes:
    wb = Workbook()

    # ---------- Overview ----------
    ws = wb.active
    ws.title = "Overview"
    s = plan["season"]
    _title(ws, f"Seasonal plan - {plan['squad']}", f"Season {s['name']}  |  {s['start_date']:%d %b %Y} to {s['end_date']:%d %b %Y}  |  generated {plan['generated_on']:%d %b %Y}")
    r = 4
    _header(ws, r, ["Phase", "Starts", "Ends", "Weeks", "Intensity", "Purpose", "Workload principle", "Matches", "Fitness tests", "Training sessions", "Rest days"],
            [22, 14, 14, 8, 22, 55, 55, 10, 24, 12, 10])
    for p in plan["phases"]:
        r += 1
        tests = ", ".join(f"{t['date']:%d %b}" for t in p["fitness_tests"]) or "-"
        for c, v in enumerate([p["label"], p["start_date"], p["end_date"], p["weeks"], p["intensity"], p["focus"], p["workload"], p["matches"], tests,
                               p["training_sessions"], p["rest_days"]], 1):
            _put(ws, r, c, v, bold=(c == 1), fill=LIGHT if c == 1 else None)
    r += 2
    _put(ws, r, 1, "Fitness testing", bold=True, size=12, border=False, wrap=False)
    r += 1
    _header(ws, r, ["Test", "From", "To", "", "Source"])
    for t in plan["testing"]:
        r += 1
        src = t["source"] + (": " + ", ".join(f"{x['date']:%d %b} {x['title']}" for x in t["scheduled"]) if t.get("scheduled") else "")
        for c, v in enumerate([t["test"], t["from"], t["to"], "", src], 1):
            _put(ws, r, c, v)
    r += 2
    _put(ws, r, 1, "Staff", bold=True, size=12, border=False, wrap=False)
    for label, key in (("Coach(es)", "coach"), ("S&C coach(es)", "sc_coach"), ("Physiotherapist(s)", "physio")):
        r += 1
        _put(ws, r, 1, label, bold=True, fill=LIGHT)
        _put(ws, r, 2, ", ".join(plan["staff"][key]) or "To be assigned")
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
    r += 1
    _put(ws, r, 1, "Player roles", bold=True, fill=LIGHT)
    _put(ws, r, 2, ", ".join(plan["roles_label"]) or "-")
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
    r += 2
    _put(ws, r, 1, "Notes", bold=True, size=12, border=False, wrap=False)
    for n in plan["notes"]:
        r += 1
        _put(ws, r, 1, n, border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        ws.row_dimensions[r].height = 32
    _print(ws)

    # ---------- Seasonal Plan ----------
    ws = wb.create_sheet("Seasonal Plan")
    _title(ws, f"Seasonal plan - {plan['squad']} - {s['name']}", "One row per phase, development area and player group. Update Progress status and Coach review as the season goes.")
    cols = ["Phase", "Applies to", "Development area", "Goal", "Start", "End", "Planned activities", "Responsible coach", "Measurement method",
            "Target outcome", "Progress status", "Coach review"]
    _header(ws, 4, cols, [16, 18, 13, 48, 12, 12, 60, 22, 40, 40, 14, 34])
    r = 4
    for row in plan["rows"]:
        r += 1
        vals = [row["phase_label"], row["applies_to_label"], row["development_area"].capitalize(), row["goal"], row["start_date"], row["end_date"],
                row["planned_activities"], row["responsible"], row["measurement_method"], row["target_outcome"],
                STATUS_LABEL.get(row["status"], "Not started"), row["coach_review"] or ""]
        for c, v in enumerate(vals, 1):
            _put(ws, r, c, v, fill=AREA_FILL[row["development_area"]] if c == 3 else None, bold=(c == 3))
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{max(r, 5)}"
    dv = DataValidation(type="list", formula1='"Not started,In progress,Achieved,Revised,Dropped"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"K5:K{max(r, 5)}")
    _print(ws)

    # ---------- Role Programmes ----------
    ws = wb.create_sheet("Role Programmes")
    _title(ws, "Role programmes - exercises and activities by phase", "From the supplied exercise list. Which phase each item is used in is a proposal for the coaches to confirm.")
    _header(ws, 4, ["Player group", "Phase", "Type", "Exercise / activity", "What it is used for", "Areas improved", "Kind of work", "Source list"], [20, 16, 10, 38, 48, 38, 28, 12])
    r = 4
    for e in plan["programmes"]:
        r += 1
        for c, v in enumerate([e["role_label"], e["phase_label"], e["category"].capitalize(), e["name"], e["purpose"], e["areas"], e["kind"], e["source_list"]], 1):
            _put(ws, r, c, v)
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:H{max(r, 5)}"
    _print(ws)

    # ---------- Workload Rules ----------
    ws = wb.create_sheet("Workload Rules")
    _title(ws, "Workload and progressive-overload rules", plan["workload_note"])
    _header(ws, 4, ["Applies to", "Rule"], [24, 110])
    r = 4
    for w in plan["workload_rules"]:
        r += 1
        _put(ws, r, 1, w["applies_to"], bold=True, fill=LIGHT)
        _put(ws, r, 2, w["rule"])
    _print(ws)

    # ---------- Session Template ----------
    ws = wb.create_sheet("Session Template")
    total = sum(x["minutes"] for x in plan["session_template"])
    _title(ws, f"Example {total}-minute {plan.get('age_group', 'U15')} session", " ".join(plan["session_guidance"]))
    _header(ws, 4, ["Part", "Minutes", "What to do"], [26, 10, 100])
    r = 4
    for x in plan["session_template"]:
        r += 1
        _put(ws, r, 1, x["part"], bold=True, fill=LIGHT)
        _put(ws, r, 2, x["minutes"])
        _put(ws, r, 3, x["what"])
    _print(ws)

    # ---------- Calendar ----------
    ws = wb.create_sheet("Calendar")
    _title(ws, "Calendar events in this season")
    _header(ws, 4, ["Date", "Type", "Event"], [14, 16, 60])
    r = 4
    for e in plan["events"]:
        r += 1
        _put(ws, r, 1, e["date"])
        _put(ws, r, 2, e["event_type"].replace("_", " ").capitalize())
        _put(ws, r, 3, e["title"])
    if r == 4:
        _put(ws, 5, 1, "No events in the calendar for this season yet.", border=False)
    _print(ws, landscape=False)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
