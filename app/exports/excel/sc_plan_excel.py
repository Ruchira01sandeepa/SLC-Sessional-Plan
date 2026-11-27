"""The Strength & Conditioning (Physical) category plan as its own workbook: Summary, Sessions, Week by week.
Text is stored as text, never as a formula."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

BLUE, LIGHT, GREY = "1F4E79", "DDEBF7", "F2F2F2"
STATUS = {"priority": "Priority", "strength": "Strength", "solid": "Solid", "not_rated": "Not rated yet"}


def _s(ws, r, c, v, *, bold=False, fill=None, white=False, wrap=False):
    cell = ws.cell(row=r, column=c)
    cell.value = v
    if isinstance(v, str):
        cell.data_type = "s"                                              # stored as text, never run as a formula
    cell.font = Font(name="Calibri", size=11, bold=bold, color="FFFFFF" if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    return cell


def _head(ws, r, cols):
    for i, h in enumerate(cols, 1):
        _s(ws, r, i, h, bold=True, fill=BLUE, white=True, wrap=True)


def build_sc_workbook(out: dict, phys: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "S&C summary"
    season = (out.get("season") or {}).get("name") or ""
    _s(ws, 1, 1, f"STRENGTH & CONDITIONING PLAN - {out['player']}", bold=True)
    _s(ws, 2, 1, f"Season: {season} · Readiness: {out['readiness'].get('label', out['status'])} · Growth: {phys['growth']} · Experience: {phys['training_age']}")
    _s(ws, 3, 1, "A proposal for the coach, built from the player's individual plan. Stop and refer to the physiotherapist if there is pain.", wrap=False)
    r = 5
    _s(ws, r, 1, "Test profile", bold=True)
    r += 1
    _head(ws, r, ["Area", "Rank in level (0-100)", "Status", "For age", "Trend"])
    for a in phys["test_profile"]:
        r += 1
        _s(ws, r, 1, a["label"])
        _s(ws, r, 2, a["percentile"])
        _s(ws, r, 3, STATUS.get(a["status"], a["status"] or ""))
        _s(ws, r, 4, a.get("age_label") or "")
        _s(ws, r, 5, a.get("trend") or "")
    r += 2
    _s(ws, r, 1, "Goals", bold=True)
    for g in phys["goals"]:
        r += 1
        _s(ws, r, 1, g["label"], wrap=True)
        _s(ws, r, 3, g.get("by") or "")
        _s(ws, r, 4, g.get("why") or "", wrap=True)
    r += 2
    _s(ws, r, 1, "PDP - Physical (coach rating 1-5)", bold=True)
    for p in phys["pdp"]:
        r += 1
        _s(ws, r, 1, p["skill"])
        _s(ws, r, 2, p["rating"] if p["rating"] is not None else "not rated")
    r += 2
    _s(ws, r, 1, "Rules", bold=True)
    for t in phys["rules"]:
        r += 1
        _s(ws, r, 1, t)
    for col, w in zip("ABCDE", (34, 20, 22, 60, 12)):
        ws.column_dimensions[col].width = w

    ws = wb.create_sheet("Sessions")
    r = 1
    cols = ["Part", "Exercise", "Area", "Sets", "Reps / time", "Rest", "Why", "Progression"]
    for ph in phys["phases"]:
        _s(ws, r, 1, f"{ph['label']} - {ph['sessions_per_week']} focus session(s) a week", bold=True, fill=LIGHT)
        r += 1
        _s(ws, r, 1, "Week: " + " | ".join(f"{d['day']}: {', '.join(d['items'])}" for d in ph["typical_week"]), wrap=False)
        r += 1
        for s in ph["sessions"]:
            _s(ws, r, 1, f"{s['name']}" + (f" ({s['day']})" if s.get("day") else "") + f" · about {s['minutes']} min · {s['when']}", bold=True, fill=GREY)
            if s.get("note"):
                _s(ws, r, 3, s["note"])
            r += 1
            _head(ws, r, cols)
            for part in s["parts"]:
                for it in part["items"] or []:
                    r += 1
                    _s(ws, r, 1, part["part"])
                    _s(ws, r, 2, it["name"], wrap=True)
                    _s(ws, r, 3, it.get("area_label") or "")
                    _s(ws, r, 4, it.get("set") or "")
                    _s(ws, r, 5, it.get("rep") or it.get("time") or "")
                    _s(ws, r, 6, it.get("rest") or "")
                    _s(ws, r, 7, it.get("why") or "", wrap=True)
                    _s(ws, r, 8, it.get("progression") or "", wrap=True)
            r += 2
        r += 1
    for col, w in zip("ABCDEFGH", (18, 36, 22, 8, 18, 22, 40, 50)):
        ws.column_dimensions[col].width = w

    ws = wb.create_sheet("Week by week")
    _head(ws, 1, ["Week", "Starts", "Phase", "Focus sessions", "Focus load", "Planned week load", "Matches", "Bowling days", "Easy week", "Sessions this week", "Dose this week", "Flags"])
    for i, w in enumerate(phys["weeks"], 2):
        vals = [w["week"], str(w["start"])[:10], w["phase_label"], w["focus_sessions"], w["focus_load"], w["planned_load"], w["matches"],
                w["bowl_days"], "Yes" if w["easy_week"] else "", ", ".join(w["sessions"]), w["dose_step"], "; ".join(w["flags"])]
        for c, v in enumerate(vals, 1):
            _s(ws, i, c, v, wrap=c in (11, 12))
    for col, w in zip("ABCDEFGHIJKL", (7, 12, 16, 10, 10, 12, 9, 10, 9, 22, 60, 40)):
        ws.column_dimensions[col].width = w
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
