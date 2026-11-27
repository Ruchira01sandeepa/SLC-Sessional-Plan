"""Read a squad sheet (e.g. "U15 Galle Super Provincial Tournament 16 players Squad 2026") into new players. Pure module (no database).

Expected layout (the SLC National Talent Pathway squad list), found by its header row, not by fixed positions:

    Ranking | Player Name | (Captain / Vice Captain) | DOB | Age @ <date> | School | District | Province | Bat | Bowl

Group heading rows ("Batting group", "Wicket Keeper group", "Spin group", "Pace group", "Spin All Rounder", "Pace All Rounder",
"Stand By") set the role of the players under them. Stand-by players keep their own role, worked out from the Bowl code.
Nothing is guessed silently: a row that cannot be read is listed with its row number and reason, and doubtful values are warnings.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

from app.reference.age_groups import CODES as AGE_CODES, age_on, check_dob
from app.core.clock import today_lk

MAX_BYTES = 2_000_000
MAX_ROWS = 300
HEADER_SCAN_ROWS = 30
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f]")

ROLE_LABEL = {"batter": "Batter", "bat_wicketkeeper": "Wicket-keeper batter", "spin_bowler": "Spin bowler",
              "fast_bowler": "Fast bowler", "all_rounder": "All-rounder"}

# Bowl column codes -> (arm, style text, kind). The style text is what the rest of the app reads ("spin" / "fast" / "medium").
BOWL_CODES = {
    "RAF": ("Right", "right-arm fast", "fast"), "LAF": ("Left", "left-arm fast", "fast"),
    "RAFM": ("Right", "right-arm fast-medium", "fast"), "LAFM": ("Left", "left-arm fast-medium", "fast"),
    "RAMF": ("Right", "right-arm medium-fast", "fast"), "LAMF": ("Left", "left-arm medium-fast", "fast"),
    "RAM": ("Right", "right-arm medium pace", "fast"), "LAM": ("Left", "left-arm medium pace", "fast"),
    "RAOS": ("Right", "right-arm off spin", "spin"), "RAO": ("Right", "right-arm off spin", "spin"),
    "RALS": ("Right", "right-arm leg spin", "spin"), "RAL": ("Right", "right-arm leg spin", "spin"),
    "LAO": ("Left", "left-arm orthodox spin", "spin"), "LAOS": ("Left", "left-arm orthodox spin", "spin"),
    "SLA": ("Left", "left-arm orthodox spin", "spin"),
    "LAWS": ("Left", "left-arm wrist spin", "spin"), "LAC": ("Left", "left-arm wrist spin (chinaman)", "spin"),
    "WK": (None, None, "keeper"),
}
BAT_CODES = {"RH": "Right", "RHB": "Right", "R": "Right", "LH": "Left", "LHB": "Left", "L": "Left"}

_HEADERS = {        # field -> accepted header texts (lower case, spaces squeezed)
    "ranking": ("ranking", "rank", "no", "no.", "#", "squad no", "player no"),
    "name": ("player name", "name", "player"),
    "school": ("school", "school / club", "school/club", "club"),
    "district": ("district",),
    "province": ("province",),
    "bat": ("bat", "batting", "batting hand"),
    "bowl": ("bowl", "bowling", "bowling style"),
}


def _clean(v) -> str | None:
    if v is None:
        return None
    s = _CTRL.sub("", str(v)).strip()
    return re.sub(r"\s+", " ", s) or None


def _norm(v) -> str:
    return (_clean(v) or "").lower()


def _as_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def group_role(text: str) -> tuple[str, bool] | None:
    """A group heading -> (role, standby). None when the text is not a group heading."""
    t = re.sub(r"[^a-z]", "", text.lower())
    if not t or len(t) > 40:
        return None
    if "standby" in t or t in ("reserves", "reserve"):
        return ("", True)                                  # role comes from each player's Bowl code
    if "allrounder" in t:
        return ("all_rounder", False)
    if "wicket" in t or "keeper" in t:
        return ("bat_wicketkeeper", False)
    if "spin" in t:
        return ("spin_bowler", False)
    if "pace" in t or "fast" in t or "seam" in t:
        return ("fast_bowler", False)
    if "batting" in t or "batter" in t or "batsm" in t:
        return ("batter", False)
    return None


def _captaincy(texts: list[str]) -> str | None:
    for s in texts:
        t = s.lower()
        if "captain" in t or t in ("c", "vc", "(c)", "(vc)"):
            return "vice_captain" if ("vic" in t or t in ("vc", "(vc)")) else "captain"
    return None


def _find_header(ws):
    """(row number, {field: column}, age column, age reference date) of the header row, or None."""
    rows = list(ws.iter_rows(min_row=1, max_row=HEADER_SCAN_ROWS, values_only=True))
    for i, vals in enumerate(rows):
        texts = [_norm(v) for v in vals]
        cols = {}
        for field, names in _HEADERS.items():
            for c, t in enumerate(texts):
                if t in names and field not in cols:
                    cols[field] = c
        dob = next((c for c, t in enumerate(texts) if t.startswith("dob") or t.startswith("date of birth")), None)
        if "name" not in cols or dob is None:
            continue
        cols["dob"] = dob
        above = [_norm(v) for v in rows[i - 1]] if i > 0 else []
        age_col, ref = None, None
        for c, t in enumerate(texts):
            if t.startswith("age") or (c < len(above) and above[c].startswith("age")):
                age_col = c
                ref = _as_date(vals[c])
                if ref is None:
                    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t + " " + (above[c] if c < len(above) else ""))
                    if m:
                        try:
                            ref = date(int(m[3]), int(m[1]), int(m[2]))
                        except ValueError:
                            ref = None
                break
        above_texts = [s for r in rows[:i] for v in r if not isinstance(v, (int, float)) and (s := _clean(v))]
        title = next((t for t in above_texts if "squad" in t.lower()), above_texts[-1] if above_texts else None)
        return i + 1, cols, age_col, ref, title
    return None


def _parse_dob(v, age, ref) -> tuple[date | None, str | None]:
    """(date, problem). Strings like 11/18/2011 are read month/day unless the Age column says day/month."""
    d = _as_date(v)
    if d is not None:
        return d, None
    if isinstance(v, (int, float)) and 20000 < v < 60000:                  # an Excel date serial left as a number
        return date(1899, 12, 30) + timedelta(days=int(v)), None
    s = _clean(v)
    if not s:
        return None, "Date of birth is missing"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), None
        except ValueError:
            return None, f"'{s}' is not a real date"
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if not m:
        return None, f"Cannot read the date of birth '{s}' (use a date cell, or month/day/year)"
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    options = []
    for mo, dd in ((a, b), (b, a)):                                       # month/day first, as in the SLC sheet
        try:
            options.append(date(y, mo, dd))
        except ValueError:
            pass
    options = list(dict.fromkeys(options))
    if not options:
        return None, f"'{s}' is not a real date"
    if len(options) > 1 and isinstance(age, (int, float)) and ref:
        fits = [o for o in options if abs((ref - o).days / 365.25 - float(age)) < 0.05]
        if len(fits) == 1:
            return fits[0], None
    return options[0], None


def parse_workbook(data: bytes, age_group: str | None = None, today: date | None = None) -> dict:
    """Returns {sheet, title, suggested: {name, province, age_group}, rows, errors, warnings}.
    rows: {row, squad_no, full_name, date_of_birth, age, role, role_label, group, standby, captaincy, school_or_club, district,
    province, batting_hand, bowling_arm, style, bowl_code}. errors / warnings: {row, column, message}."""
    if len(data) > MAX_BYTES:
        raise ValueError("The file is too large (2 MB at most)")
    try:
        wb = load_workbook(BytesIO(data), data_only=True)
    except Exception:
        raise ValueError("This is not a readable .xlsx file. Save the squad list as an Excel workbook (.xlsx) and try again.")
    today = today or today_lk()

    found = None
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        h = _find_header(ws)
        if h:
            found = (ws, *h)
            break
    if not found:
        raise ValueError("No squad table found. The sheet needs a header row with 'Player Name' and 'DOB' columns.")
    ws, header_row, cols, age_col, ref, title = found

    m = re.search(r"\bU\s?(\d{2})\b", title or "", re.I)
    suggested_age = f"U{m[1]}" if m and f"U{m[1]}" in AGE_CODES else None
    age_group = (age_group or suggested_age or "U15").upper()

    def cell(vals, field):
        c = cols.get(field)
        return vals[c] if c is not None and c < len(vals) else None

    rows, errors, warnings, skipped = [], [], [], []
    group, standby_mode = None, False
    names_seen, numbers_seen = {}, {}
    data_rows = 0
    for r_no, vals in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        texts = [s for s in (_clean(v) for v in vals) if s]
        if not texts:
            continue
        rank, name, dob_v = cell(vals, "ranking"), _clean(cell(vals, "name")), cell(vals, "dob")
        rank_no = int(rank) if isinstance(rank, (int, float)) and float(rank).is_integer() else (
            int(rank) if isinstance(rank, str) and rank.strip().isdigit() else None)
        if rank_no is None and _blank(dob_v):
            g = next((group_role(t) for t in texts if group_role(t)), None)
            if g:
                group, standby_mode = g
                continue
            skipped.append((r_no, texts[0]))                           # e.g. the selectors' names under the table
            continue
        data_rows += 1
        if data_rows > MAX_ROWS:
            raise ValueError(f"Too many player rows (at most {MAX_ROWS})")

        def err(column, message):
            errors.append({"row": r_no, "column": column, "message": message})

        def warn(column, message):
            warnings.append({"row": r_no, "column": column, "message": message})

        known = set(cols.values()) | ({age_col} if age_col is not None else set())
        extra = [t for c, v in enumerate(vals) if c not in known and (t := _clean(v))]     # e.g. "CAPTAIN" / "VIC CAPTAIN"
        before = len(errors)
        if not name:
            err("Player Name", "Player name is missing")
        elif len(name) > 200:
            err("Player Name", "Player name is longer than 200 characters")
        age_v = vals[age_col] if age_col is not None and age_col < len(vals) else None
        dob, problem = _parse_dob(dob_v, age_v, ref)
        if problem:
            err("DOB", problem)
        elif dob:
            try:
                check_dob(age_group, dob, today)
            except ValueError as e:
                err("DOB", f"{dob.isoformat()}: {e}")

        bowl_raw = _clean(cell(vals, "bowl"))
        code = re.sub(r"[^A-Z]", "", (bowl_raw or "").upper()) or None
        arm, style, kind = BOWL_CODES.get(code, (None, None, None)) if code else (None, None, None)
        if code and code not in BOWL_CODES:
            warn("Bowl", f"Unknown bowling code '{bowl_raw}'; kept as written")
            style = bowl_raw[:50]
        bat_raw = _clean(cell(vals, "bat"))
        bat = BAT_CODES.get(re.sub(r"[^A-Z]", "", (bat_raw or "").upper())) if bat_raw else None
        if bat_raw and not bat:
            warn("Bat", f"Unknown batting code '{bat_raw}' (use RH or LH)")

        if group is None:
            err("Group", "This player is not under a group heading (Batting / Wicket Keeper / Spin / Pace / All Rounder / Stand By)")
            role = None
        elif standby_mode:
            role = {"keeper": "bat_wicketkeeper", "fast": "fast_bowler", "spin": "spin_bowler"}.get(kind, "batter")
        else:
            role = group
            expected = {"spin_bowler": "spin", "fast_bowler": "fast", "bat_wicketkeeper": "keeper"}.get(role)
            if expected and kind and kind != expected:
                warn("Bowl", f"Bowling code '{bowl_raw}' does not match the {ROLE_LABEL[role].lower()} group")
            if role == "all_rounder" and kind not in ("spin", "fast"):
                warn("Bowl", "All-rounder without a bowling code: their bowling type is unknown")
        if kind == "keeper":
            arm = None

        if name:
            key = name.lower()
            if key in names_seen:
                err("Player Name", f"Same name as row {names_seen[key]}")
            names_seen.setdefault(key, r_no)
        if rank_no is not None:
            if rank_no in numbers_seen:
                warn("Ranking", f"Same number as row {numbers_seen[rank_no]}")
            numbers_seen.setdefault(rank_no, r_no)

        if len(errors) > before:
            continue
        rows.append({
            "row": r_no, "squad_no": rank_no, "full_name": name, "date_of_birth": dob.isoformat(), "age": age_on(dob, today),
            "role": role, "role_label": ROLE_LABEL[role], "group": "Stand by" if standby_mode else ROLE_LABEL[role],
            "standby": standby_mode, "captaincy": _captaincy(extra),
            "school_or_club": (_clean(cell(vals, "school")) or None) and _clean(cell(vals, "school"))[:200],
            "district": (_clean(cell(vals, "district")) or None) and _clean(cell(vals, "district"))[:100],
            "province": _clean(cell(vals, "province")), "batting_hand": bat, "bowling_arm": arm, "style": style,
            "bowl_code": code,
        })

    last_player = max((r["row"] for r in rows), default=0)
    last_player = max([last_player] + [e["row"] for e in errors])
    for r_no, text in skipped:
        if r_no < last_player:
            warnings.append({"row": r_no, "column": "", "message": f"Row ignored ('{text[:40]}'): no ranking number and no date of birth"})
    caps = [r for r in rows if r["captaincy"] == "captain"]
    if len(caps) > 1:
        warnings.append({"row": caps[1]["row"], "column": "", "message": "More than one captain marked"})
    if not rows and not errors:
        raise ValueError("No players found under the header row")

    provinces = Counter(r["province"] for r in rows if r["province"])
    return {"sheet": ws.title, "title": title, "age_group": age_group,
            "suggested": {"name": (title or "")[:200] or None, "province": provinces.most_common(1)[0][0] if provinces else None,
                          "age_group": suggested_age},
            "rows": rows, "errors": errors, "warnings": warnings}


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())
