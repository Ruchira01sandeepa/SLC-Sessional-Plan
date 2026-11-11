"""One player's workbook: a summary of their test results and focus plan, the weekly load, then the same sheets as the squad
seasonal workbook (annual plan, load distribution, component distribution, session plans for the player's role).
Text is stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L

from .annual_grid_excel import write_annual_sheet
from .seasonal_workbook import (BLUE, LIGHT, season_phases_of, session_sheet_name, write_component_sheet, write_load_sheet,
                                write_session_sheet)
from .session_plans import ROLE_LABEL, build_session


def _s(ws, r, c, v, *, bold=False, fill=None, white=False, wrap=False, fmt=None):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"
    cell.font = Font(name="Calibri", size=11, bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    if wrap:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    if fmt:
        cell.number_format = fmt
    return cell


def write_summary_sheet(ws, summary: dict, plan: dict) -> None:
    for col, w in zip("ABCDEFGH", (30, 22, 14, 14, 14, 14, 16, 18)):
        ws.column_dimensions[col].width = w
    _s(ws, 1, 1, f"Individual plan: {summary['player']}", bold=True)
    info = [("Role", ROLE_LABEL.get(summary["role"], summary["role"])), ("Level", summary["level_label"]),
            ("Test window", summary["window_label"]),
            ("Band", f"{summary['band']} - {summary['band_label']}" if summary.get("band") else "No band yet"),
            ("Overall score (0-100)", summary.get("overall")),
            ("Readiness", f"{plan['readiness']['label']}: {plan['readiness']['reason']}")]
    for i, (k, v) in enumerate(info, 3):
        _s(ws, i, 1, k, bold=True)
        _s(ws, i, 2, v)
    r = 3 + len(info) + 1
    for c, h in enumerate(["Area", "Test", "Trial 1", "Trial 2", "Trial 3", "Best (final)", "Test percentile", "Area percentile"], 1):
        _s(ws, r, c, h, bold=True, fill=BLUE, white=True)
    r += 1
    for a in summary["areas"]:
        for k, t in enumerate(a["tests"]):
            _s(ws, r, 1, a["label"] if k == 0 else None)
            _s(ws, r, 2, t["label"] + f" ({t['unit']})")
            for i, d in enumerate(t["trials_display"], 3):
                _s(ws, r, i, d)
            _s(ws, r, 6, t["display"], bold=True)
            _s(ws, r, 7, t["percentile"])
            _s(ws, r, 8, a["percentile"] if k == 0 else None)
            r += 1
    r += 1
    _s(ws, r, 1, "Focus areas (below the middle, weakest first)", bold=True)
    for f in plan["focus_areas"] or []:
        r += 1
        _s(ws, r, 1, f["label"])
        _s(ws, r, 2, f["percentile"])
    if not plan["focus_areas"]:
        r += 1
        _s(ws, r, 1, "None")
    r += 2
    _s(ws, r, 1, "Notes", bold=True)
    for line in plan["notes"] + [summary.get("note")] if summary.get("note") else plan["notes"]:
        r += 1
        _s(ws, r, 1, line)
    r += 2
    _s(ws, r, 1, "Results are confidential. Share only with authorised staff.")


def write_profile_sheet(ws, summary: dict, plan: dict) -> None:
    """The player's own plan on one page: who they are, strengths, priorities, goals, skills, a typical week and review dates."""
    pr, gr, ta = plan["profile"], plan["profile"]["growth"], plan["profile"]["training_age"]
    for col, w in zip("ABCDEFGH", (26, 46, 26, 46, 18, 18, 18, 18)):
        ws.column_dimensions[col].width = w
    _s(ws, 1, 1, f"Personal plan: {summary['player']}", bold=True)
    _s(ws, 2, 1, "Built from this player's own test ranks, coach ratings, growth, history and readiness. A proposal for the coach.")
    r = 4
    facts = [("Role", ROLE_LABEL.get(plan["role"], plan["role"])), ("Readiness", f"{plan['readiness']['label']}: {plan['readiness']['reason']}"),
             ("Growth", gr["label"] + (f" ({gr['velocity_cm_yr']} cm a year)" if gr["velocity_cm_yr"] is not None else "")),
             ("Experience", ta["label"]), ("Weighting", pr["importance_source"]), ("Player's own goal", pr.get("objective") or "-")]
    for k, v in facts:
        _s(ws, r, 1, k, bold=True)
        _s(ws, r, 2, v, wrap=True)
        r += 1
    r += 1
    _s(ws, r, 1, "Strengths to build on", bold=True, fill=BLUE, white=True)
    _s(ws, r, 2, None, fill=BLUE)
    _s(ws, r, 3, "Priorities", bold=True, fill=BLUE, white=True)
    _s(ws, r, 4, None, fill=BLUE)
    r += 1
    for i in range(max(len(plan["strengths"]), len(plan["priorities"]), 1)):
        if i < len(plan["strengths"]):
            _s(ws, r + i, 1, plan["strengths"][i]["label"], bold=True)
            _s(ws, r + i, 2, plan["strengths"][i]["detail"], wrap=True)
        if i < len(plan["priorities"]):
            _s(ws, r + i, 3, plan["priorities"][i]["label"], bold=True)
            _s(ws, r + i, 4, plan["priorities"][i]["detail"], wrap=True)
    r += max(len(plan["strengths"]), len(plan["priorities"]), 1) + 1
    for c, hd in enumerate(["Goal type", "Goal", "By", "Why"], 1):
        _s(ws, r, c, hd, bold=True, fill=BLUE, white=True)
    r += 1
    for g in plan["goals"]:
        _s(ws, r, 1, g["kind"])
        _s(ws, r, 2, g["label"], wrap=True)
        _s(ws, r, 3, g.get("by"))
        _s(ws, r, 4, g.get("why"), wrap=True)
        r += 1
    for ph in plan["phases"]:
        if ph.get("skills"):
            r += 1
            _s(ws, r, 1, f"Cricket skills: {ph['label']}", bold=True, fill=LIGHT)
            r += 1
            for sk in ph["skills"]:
                _s(ws, r, 1, f"{sk['group']} - {sk['skill']} ({sk['rating']}/5)")
                _s(ws, r, 2, ", ".join(d["name"] for d in sk["drills"]) or sk.get("note"), wrap=True)
                r += 1
    r += 1
    _s(ws, r, 1, "A typical week", bold=True, fill=BLUE, white=True)
    r += 1
    for ph in plan["phases"]:
        _s(ws, r, 1, ph["label"], bold=True)
        _s(ws, r, 2, " | ".join(f"{d['day']}: {', '.join(d['items'])}" for d in ph.get("typical_week", [])), wrap=True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        ws.row_dimensions[r].height = 46
        r += 1
    r += 1
    _s(ws, r, 1, "Review points", bold=True, fill=BLUE, white=True)
    r += 1
    for rv in plan["reviews"][:12]:
        _s(ws, r, 1, rv["date"].strftime("%d %b %Y") if hasattr(rv["date"], "strftime") else str(rv["date"]))
        _s(ws, r, 2, rv["what"], wrap=True)
        r += 1
    r += 1
    for line in plan["notes"]:
        _s(ws, r, 1, line)
        r += 1
    ws.freeze_panes = "A4"


def write_focus_sheet(ws, plan: dict) -> None:
    for col, w in zip("ABCDEFGHIJ", (18, 26, 40, 34, 20, 18, 14, 26, 46, 44)):
        ws.column_dimensions[col].width = w
    for c, h in enumerate(["Phase", "Focus area", "Exercise", "What it is for", "Time", "Reps", "Sets", "Rest", "Why this dose", "Why this exercise"], 1):
        _s(ws, 1, c, h, bold=True, fill=BLUE, white=True)
    r = 2
    for ph in plan["phases"]:
        _s(ws, r, 1, f"{ph['label']} ({ph['sessions_per_week']} focus session(s) a week)", bold=True, fill=LIGHT)
        for c in range(2, 11):
            _s(ws, r, c, None, fill=LIGHT)
        r += 1
        for a in ph["areas"]:
            if a["note"]:
                _s(ws, r, 2, a["label"] + (" (priority)" if a["priority"] else ""), bold=True)
                _s(ws, r, 3, a["note"], wrap=True)
                r += 1
            for k, e in enumerate(a["exercises"]):
                _s(ws, r, 2, (a["label"] + (" (priority)" if a["priority"] else "")) if k == 0 else None, bold=True)
                _s(ws, r, 3, e["name"], wrap=True)
                _s(ws, r, 4, e["purpose"], wrap=True)
                for c, key in zip((5, 6, 7, 8, 9, 10), ("time", "rep", "set", "rest", "basis", "why")):
                    _s(ws, r, c, e.get(key) or None, wrap=True)
                r += 1
    _s(ws, r + 1, 2, "Progression: start at the first number. Add one rep (or one set once the reps reach the target) every two weeks if technique stays good and there is no pain. Hold or step back if the player is sore or tired.")
    ws.freeze_panes = "A2"


def write_weekly_sheet(ws, plan: dict) -> None:
    for col, w in zip("ABCDEFGHIJKLM", (8, 14, 18, 12, 14, 14, 18, 14, 14, 16, 14, 11, 60)):
        ws.column_dimensions[col].width = w
    heads = ["Week", "Starts", "Phase", "Squad load %", "Planned load (units)", "Matches (units)", "Bowling (days x overs, spells)", "Bowling (units)",
             "Focus work (units)", "General training (units)", "Change on last week", "Load ratio", "Notes"]
    for c, h in enumerate(heads, 1):
        _s(ws, 1, c, h, bold=True, fill=BLUE, white=True)
        ws.cell(row=1, column=c).alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate(plan["weeks"], 2):
        _s(ws, i, 1, w["week"])
        _s(ws, i, 2, w["start"].strftime("%d %b %Y"))
        _s(ws, i, 3, w["phase_label"])
        _s(ws, i, 4, w["squad_percentage"], fmt="0%")
        _s(ws, i, 5, w["planned_load"], fmt="#,##0")
        _s(ws, i, 6, w["match_load"] or None, fmt="#,##0")
        _s(ws, i, 7, f"{w['bowl_days']} x {w['overs_per_day']} ({w['spells']})" if w["bowl_days"] else None)
        _s(ws, i, 8, w["bowl_load"] or None, fmt="#,##0")
        _s(ws, i, 9, w["focus_load"], fmt="#,##0")
        _s(ws, i, 10, w["general_load"], fmt="#,##0")
        _s(ws, i, 11, None if w["rise_pct"] is None else w["rise_pct"] / 100, fmt="+0.0%;-0.0%;0.0%")
        _s(ws, i, 12, w["load_ratio"], fmt="0.00")
        _s(ws, i, 13, "; ".join(w["flags"]) or None)
    n = len(plan["weeks"]) + 3
    sm = plan["load_summary"]
    lines = [f"Start: {sm['source']}.", f"Starting weekly load: {sm['start_load']:,} units ({sm['unit']}).",
             f"Highest weekly rise {sm['max_rise_pct']}% (cap 10%); highest load ratio {sm['max_load_ratio']} (cap 1.3); easy weeks {sm['easy_weeks']}.",
             sm["assumptions"],
             "The week's load is shared as: matches (fixed by the calendar), then bowling (squad sheet overs, within the fast-bowler limits, only reduced to fit), "
             "then individual focus work, then general squad training.",
             f"Readiness {plan['readiness']['label']}: {plan['readiness']['reason']}",
             "Every number is a proposal for the coach."]
    if sm["match_over_limit_weeks"]:
        lines.append(f"{sm['match_over_limit_weeks']} week(s) have match load alone above the weekly limit. The coach should review the match minutes in those weeks.")
    for k, line in enumerate(lines):
        _s(ws, n + k, 1, line)
    ws.freeze_panes = "A2"


def write_progress_sheet(ws, prog: dict) -> None:
    wins = prog["windows"]
    ws.column_dimensions["A"].width = 28
    for i in range(len(wins) + 2):
        ws.column_dimensions[chr(66 + i)].width = 18
    heads = ["Test"] + [w["label"] for w in wins] + ["Change (first to latest)"]
    for c, hd in enumerate(heads, 1):
        _s(ws, 1, c, hd, bold=True, fill=BLUE, white=True)
    for r, t in enumerate(prog["tests"], 2):
        _s(ws, r, 1, f"{t['label']} ({t['unit']})")
        for c, w in enumerate(wins, 2):
            _s(ws, r, c, t["values"].get(w["window"]))
        ch = t["change"]
        _s(ws, r, len(wins) + 2, f"{ch['text']} ({ch['state']})" if ch else None)
    r = len(prog["tests"]) + 3
    _s(ws, r, 1, "Band", bold=True)
    for c, w in enumerate(wins, 2):
        _s(ws, r, c, f"Band {w['band']} {w['band_label']}" if w["band"] else "No band")
    if prog["band_movement"]:
        _s(ws, r, len(wins) + 2, prog["band_movement"]["text"])
    for line in prog["notes"]:
        r += 1
        _s(ws, r + 1, 1, line)
    ws.freeze_panes = "B2"


def build_player_workbook(summary: dict, plan: dict, g: dict, bowling: set[str] | None = None, prog: dict | None = None) -> bytes:
    wb = Workbook()
    write_profile_sheet(wb.active, summary, plan)
    wb.active.title = "Player plan"
    write_summary_sheet(wb.create_sheet("Test summary"), summary, plan)
    write_focus_sheet(wb.create_sheet("Focus plan"), plan)
    write_weekly_sheet(wb.create_sheet("Weekly load"), plan)
    if prog and len(prog["windows"]) >= 2:
        write_progress_sheet(wb.create_sheet("Progress"), prog)
    write_annual_sheet(wb.create_sheet("Annual plan"), g)
    write_load_sheet(wb.create_sheet("Load distribution"), g)
    write_component_sheet(wb.create_sheet("Component distribution"), [plan["role"]], bowling)
    used = {"Player plan", "Test summary", "Focus plan", "Weekly load", "Progress", "Annual plan", "Load distribution", "Component distribution"}
    for phase in season_phases_of(g):
        write_session_sheet(wb.create_sheet(session_sheet_name(plan["role"], phase, used)), build_session(plan["role"], phase, bowling))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
