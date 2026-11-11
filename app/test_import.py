"""Read an SOP test-results workbook (the template from test_template_excel) and check it row by row. Pure module (no database).

Never estimates anything: a blank trial stays blank, a test with no trials has no final value. A bad cell rejects its row with the
sheet, row, column and reason; good rows are returned so the admin can confirm them. The best of three is calculated here, not read
from the file.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from .test_battery import ANTHRO, LEVEL_LABEL, LEVELS, TRIALS, best_of, parse_value, tests_for

MAX_BYTES = 2_000_000
MAX_ROWS = 500
SHEET_OF = {lv: LEVEL_LABEL[lv] for lv in LEVELS}
META_SHEET = "Instructions"
TEXT_LIMITS = {"version": 40, "surface": 80, "timing": 80, "notes": 300, "setup": 200}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f]")


def trial_header(test, i: int) -> str:
    return f"{test.label} trial {i} ({test.unit})"


def setup_header(test) -> str:
    return f"{test.label} set-up"


def columns(level: str) -> list[str]:
    """Header row of a level's sheet, in order."""
    cols = ["Player ID", "Player name", "Cleared (Yes/No)", "Test date (YYYY-MM-DD)", "Height (cm)", "Body weight (kg)",
            "Test version", "Course / surface", "Timing method"]
    for t in tests_for(level):
        cols += [trial_header(t, i) for i in range(1, TRIALS + 1)]
        if t.setup:
            cols.append(setup_header(t))
    return cols + ["Notes"]


def _clean(v) -> str | None:
    if v is None:
        return None
    s = _CTRL.sub("", str(v)).strip()
    return s or None


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def parse_workbook(data: bytes, players: dict[int, str]) -> dict:
    """players: {player_id: full_name} of the squad. Returns {meta, rows, errors, blank_rows}.
    rows: accepted rows {level, sheet, row, player_id, cleared, test_date, height_cm, weight_kg, version, surface, timing, notes,
    results: {test_key: {trials:[..3], final, setup}}}."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"The file is too large (limit {MAX_BYTES // 1_000_000} MB). Upload the template, not a copy with extra content.")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ValueError("That is not a readable .xlsx file. Download the template, fill it in and upload it again.") from None

    meta = {}
    if META_SHEET in wb.sheetnames:
        for r in wb[META_SHEET].iter_rows(min_row=1, max_row=12, max_col=2, values_only=True):
            if r[0] and r[1] is not None:
                meta[str(r[0]).strip().lower()] = str(r[1]).strip()
    rows: list[dict] = []
    errors: list[dict] = []
    blank_rows = 0

    def err(sheet, row, col, msg):
        errors.append({"sheet": sheet, "row": row, "column": col, "message": msg})

    seen_sheets = 0
    for level in LEVELS:
        name = SHEET_OF[level]
        if name not in wb.sheetnames:
            continue
        seen_sheets += 1
        ws = wb[name]
        it = ws.iter_rows(values_only=True)
        head = next(it, None)
        want = columns(level)
        if head is None or [str(h).strip() if h is not None else "" for h in head[:len(want)]] != want:
            raise ValueError(f"The '{name}' sheet columns do not match the template. Download a fresh template and copy the results across.")
        idx = {h: i for i, h in enumerate(want)}
        for n, raw in enumerate(it, start=2):
            if n - 1 > MAX_ROWS:
                raise ValueError(f"More than {MAX_ROWS} rows on '{name}'. Upload the template for one squad.")
            cell = lambda h: raw[idx[h]] if idx[h] < len(raw) else None
            tests = tests_for(level)
            filled = any(not _blank(cell(trial_header(t, i))) for t in tests for i in range(1, TRIALS + 1)) \
                or not _blank(cell("Height (cm)")) or not _blank(cell("Body weight (kg)"))
            if not filled:
                blank_rows += 1
                continue
            before = len(errors)
            pid_raw = cell("Player ID")
            try:
                pid = int(float(str(pid_raw).strip()))
            except (TypeError, ValueError):
                err(name, n, "Player ID", "Player ID is missing or not a number")
                continue
            if pid not in players:
                err(name, n, "Player ID", f"Player ID {pid} is not in this squad")
                continue
            if str(cell("Player name") or "").strip().lower() != players[pid].strip().lower():
                err(name, n, "Player name", f"Name does not match Player ID {pid} ({players[pid]}). Do not edit the ID or name columns")
            cl = str(cell("Cleared (Yes/No)") or "").strip().lower()
            if cl not in ("yes", "no"):
                err(name, n, "Cleared (Yes/No)", "Enter Yes or No: medical clearance is required before testing")
            elif cl == "no":
                err(name, n, "Cleared (Yes/No)", "Not medically cleared: results cannot be recorded for this player")
            td = cell("Test date (YYYY-MM-DD)")
            tdate = None
            if not _blank(td):
                if isinstance(td, datetime):
                    tdate = td.date()
                elif isinstance(td, date):
                    tdate = td
                else:
                    try:
                        tdate = date.fromisoformat(str(td).strip()[:10])
                    except ValueError:
                        err(name, n, "Test date (YYYY-MM-DD)", f"'{td}' is not a date (use YYYY-MM-DD)")
            else:
                err(name, n, "Test date (YYYY-MM-DD)", "Test date is required")

            def anthro(header, key):
                v = cell(header)
                if _blank(v):
                    return None
                lab, unit, lo, hi = ANTHRO[key]
                try:
                    x = round(float(v), 2)
                except (TypeError, ValueError):
                    err(name, n, header, f"'{v}' is not a number")
                    return None
                if not lo <= x <= hi:
                    err(name, n, header, f"{lab} {x} {unit} is outside the plausible range {lo} to {hi} {unit} - check the entry")
                    return None
                return x
            height, weight = anthro("Height (cm)", "height_cm"), anthro("Body weight (kg)", "weight_kg")

            texts = {}
            for key, header in (("version", "Test version"), ("surface", "Course / surface"), ("timing", "Timing method"), ("notes", "Notes")):
                t = _clean(cell(header))
                if t and len(t) > TEXT_LIMITS[key]:
                    err(name, n, header, f"Too long (limit {TEXT_LIMITS[key]} characters)")
                texts[key] = t

            results = {}
            for t in tests:
                trials: list[float | None] = []
                for i in range(1, TRIALS + 1):
                    h = trial_header(t, i)
                    v = cell(h)
                    if _blank(v):
                        trials.append(None)
                        continue
                    try:
                        trials.append(parse_value(t, v))
                    except ValueError as e:
                        err(name, n, h, str(e))
                        trials.append(None)
                setup = _clean(cell(setup_header(t))) if t.setup else None
                if setup and len(setup) > TEXT_LIMITS["setup"]:
                    err(name, n, setup_header(t), f"Too long (limit {TEXT_LIMITS['setup']} characters)")
                final = best_of(t, trials)
                if final is not None or setup:
                    results[t.key] = {"trials": trials, "final": final, "setup": setup}
            if len(errors) == before:
                rows.append({"level": level, "sheet": name, "row": n, "player_id": pid, "test_date": tdate, "height_cm": height,
                             "weight_kg": weight, "version": texts["version"], "surface": texts["surface"], "timing": texts["timing"],
                             "notes": texts["notes"], "results": results})
    if not seen_sheets:
        raise ValueError("The workbook has neither a 'Provincial' nor a 'Super Provincial' sheet. Use the template.")

    # a player filled in more than once (both level sheets, or twice on one) is ambiguous: reject every such row
    count: dict[int, list[dict]] = {}
    for r in rows:
        count.setdefault(r["player_id"], []).append(r)
    for pid, rs in count.items():
        if len(rs) > 1:
            for r in rs:
                err(r["sheet"], r["row"], "Player ID", f"{players[pid]} is filled in more than once (both level sheets or twice). Fill one row only")
            rows = [r for r in rows if r["player_id"] != pid]
    errors.sort(key=lambda e: (e["sheet"], e["row"]))
    return {"meta": meta, "rows": rows, "errors": errors, "blank_rows": blank_rows}
