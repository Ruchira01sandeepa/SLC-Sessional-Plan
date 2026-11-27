"""'Test results' sheets for the plan and report workbooks: every SOP test (trials and best, age reference), sit and reach, the 8
skinfolds and the body measures. One player (testing.player_test_report) or the whole squad (testing.squad_test_results)."""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

NAVY, PALE, WHITE = "0D2B6E", "EEF3F9", "FFFFFF"
AGE_FILL = {"strong": "CFE9CC", "on_track": "DCEBFA", "developing": "FFF0CC", "below": "F8DCDC"}
THIN = Side(style="thin", color="C9D5E3")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _c(ws, r, c, v, *, bold=False, fill=None, white=False, center=False, fmt=None):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = Font(name="Calibri", size=10, bold=bold, color=WHITE if white else None)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(horizontal="center" if center else None, vertical="center", wrap_text=True)
    cell.border = BOX
    if fmt:
        cell.number_format = fmt
    return cell


def _head(ws, r, labels):
    for i, h in enumerate(labels, 1):
        _c(ws, r, i, h, bold=True, fill=NAVY, white=True, center=True)


def _sr(cm):
    if cm is None:
        return None, "-"
    return cm, "Past the toes" if cm > 0 else "Short of the toes" if cm < 0 else "At the toes"


def write_player_tests_sheet(ws, rep: dict, name: str) -> None:
    """One player's results this season, window by window (testing.player_test_report)."""
    ag = rep.get("ref_label") or rep.get("age_group", "U15")
    for col, w in zip("ABCDEFGHI", (26, 11, 10, 10, 10, 11, 13, 18, 30)):
        ws.column_dimensions[col].width = w
    ws.cell(row=1, column=1, value=f"TEST RESULTS - {name.upper()}").font = Font(bold=True, size=12)
    r = 3
    if not rep.get("windows"):
        ws.cell(row=r, column=1, value="No test results this season yet.")
        return
    for w in rep["windows"]:
        title = f"{w['window_label']} test · {w['level_label']}" + (f" · {w['test_date']:%d %b %Y}" if w.get("test_date") else "")
        ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=11, color=NAVY)
        r += 1
        bm = w.get("benchmark")
        kv = [("Height (cm)", w["height_cm"]), ("Weight (kg)", w["weight_kg"]), ("BMI", w["bmi"]), ("Sum of 8 skinfolds (mm)", w["skinfold_sum"]),
              ("Sit and reach (cm from the toes)", w["sit_reach"]), ("Band", f"Band {w['band']} - {w['band_label']}" if w.get("band") else "-"),
              (f"{ag} points", f"{bm['total']} / {bm['max']} - {bm['band_label']}" if bm else "-")]
        for k, v in kv:
            _c(ws, r, 1, k, bold=True, fill=PALE)
            _c(ws, r, 2, v if v is not None else "-", fmt="0.0" if isinstance(v, float) else None)
            r += 1
        r += 1
        _head(ws, r, ["Test", "Unit", "Trial 1", "Trial 2", "Trial 3", "Best", f"{ag} expected", f"Against {ag}", "Notes"])
        r += 1
        for t in w["tests"]:
            _c(ws, r, 1, t["label"], bold=True)
            _c(ws, r, 2, t["unit"], center=True)
            for i, v in enumerate((t["trials"] + [None] * 3)[:3], 3):
                _c(ws, r, i, v or "-", center=True)
            _c(ws, r, 6, t["best"], bold=True, center=True)
            _c(ws, r, 7, t["expected"] or "-", center=True)
            _c(ws, r, 8, t["age_label"] or "-", center=True, fill=AGE_FILL.get(t["age"]))
            _c(ws, r, 9, "")
            r += 1
        cm, txt = _sr(w["sit_reach"])                           # sit and reach: recorded, no age reference
        _c(ws, r, 1, "Sit and reach", bold=True)
        _c(ws, r, 2, "cm", center=True)
        for i, v in enumerate((w.get("sit_reach_trials") or [None] * 3)[:3], 3):
            _c(ws, r, i, v if v is not None else "-", center=True, fmt="+0.0;-0.0;0.0" if v is not None else None)
        _c(ws, r, 6, cm if cm is not None else "-", bold=True, center=True, fmt="+0.0;-0.0;0.0" if cm is not None else None)
        _c(ws, r, 7, "Toes (0)", center=True)
        _c(ws, r, 8, txt, center=True, fill=("CFE9CC" if cm >= 10 else "DCEBFA" if cm >= 0 else "FFF0CC") if cm is not None else None)
        _c(ws, r, 9, w.get("sit_reach_note") or "")
        r += 2
        _head(ws, r, [x["label"] for x in w["skinfolds"]] + ["Sum of 8"])
        r += 1
        for i, x in enumerate(w["skinfolds"], 1):
            _c(ws, r, i, x["final"] if x["final"] is not None else "-", center=True, fmt="0.0")
        _c(ws, r, len(w["skinfolds"]) + 1, w["skinfold_sum"] if w["skinfold_sum"] is not None else "-", bold=True, center=True, fmt="0.0")
        r += 1
        if w.get("copied"):
            ws.cell(row=r, column=1, value="Skinfolds not measured: " + "; ".join(w["copied"])).font = Font(italic=True, color="A85D00")
            r += 1
        r += 2
    ws.cell(row=r, column=1, value=f"Against {ag}: the {ag} youth reference. Sit and reach: cm past (+) or short of (-) the toes; "
                                   "it is recorded, not ranked. Best of 3 trials; times in mm.ss.").font = Font(italic=True, size=9)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1


def write_squad_tests_sheet(ws, d: dict) -> None:
    """Every player's results for one window, one row each (testing.squad_test_results), sit and reach and skinfolds included."""
    tests = [t for t in d["tests"] if any(r["results"].get(t["key"]) for r in d["players"])]
    head = ["No.", "Player", "Level", "Date", "Height (cm)", "Weight (kg)", "BMI", *[f"{t['label']} ({t['unit']})" for t in tests],
            "Sit and reach (cm from toes)", *[f"{s['label']} (mm)" for s in d["sites"]], "Sum of 8 skinfolds (mm)",
            "Not measured (copied from a comparison player)"]
    ws.cell(row=1, column=1, value=f"TEST RESULTS - {d.get('squad', '')} - {d.get('season', {}).get('name', '')} - {d['window_label']}").font = Font(bold=True, size=12)
    _head(ws, 3, head)
    ws.row_dimensions[3].height = 42
    r = 4
    for p in d["players"]:
        vals = [p["squad_no"], p["name"] + (" (stand-by)" if p["standby"] else ""), p["level_label"] or "Not tested", p["test_date"] or "-",
                p["height_cm"], p["weight_kg"], p["bmi"], *[p["results"].get(t["key"]) or "-" for t in tests], p["sit_reach"],
                *[p["skinfolds"].get(s["key"]) for s in d["sites"]], p["skinfold_sum"],
                "; ".join(x for x in ([f"Sit and reach: {p['sit_reach_copied']}"] if p.get("sit_reach_copied") else [])
                          + ([f"Skinfolds: {'; '.join(p['copied'])}"] if p.get("copied") else [])) or None]
        for i, v in enumerate(vals, 1):
            _c(ws, r, i, "-" if v is None else v, bold=i == 2, center=i > 2, fmt="0.0" if isinstance(v, float) else None)
        if p["sit_reach"] is not None:
            ws.cell(row=r, column=8 + len(tests)).number_format = "+0.0;-0.0;0.0"
        r += 1
    ws.cell(row=r + 1, column=1, value="Best of 3 trials; times in mm.ss. Sit and reach: cm past (+) or short of (-) the toes. "
                                       "Sit and reach and skinfolds are recorded, not ranked.").font = Font(italic=True, size=9)
    ws.column_dimensions["B"].width = 26
    for i in range(3, len(head) + 1):
        ws.column_dimensions[ws.cell(row=3, column=i).column_letter].width = 12
    ws.column_dimensions[ws.cell(row=3, column=len(head)).column_letter].width = 48
    ws.freeze_panes = "C4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
