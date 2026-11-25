"""A player's own seasonal plan, in the supplied workbook's structure (Annual plan | Load distribution | Component distribution |
Session plan), built from the squad's grid and the player's OWN test ranks. Pure module: no database, no web.

How a player's plan differs from the squad plan (each area is the mean percentile of that area's tests, latest window):
  * WEAK area (below the 50th percentile): its rows are trained in every week (or training day) of each phase in which the squad
    plan trains them at all, except lighter recovery weeks - the developing emphasis.
  * STRONG area (75th percentile or more): its rows keep ALL the squad plan's work, so a strength keeps improving (never cut).
  * Others follow the squad plan.
  * The player's own Load distribution sheet (load_distribution.build_interval_loads) adds the extra work for the weak areas:
    endurance +1 rep of 120 m and 150 m and +1 x 300 m in preparation; speed +2 speed-endurance reps; leg power, upper-body
    strength, core and agility get their development extra in the rows under the running block.
Rows a test area maps to are in AREA_ROWS. Phases where the squad plan never trains a row are never filled, so a player's plan
never adds work the season's phase does not allow (for example no endurance block in competition)."""
from __future__ import annotations

import copy
from datetime import timedelta

WEAK, STRONG = 50, 75
AREA_ROWS: dict[str, list[tuple[str, str]]] = {
    "endurance": [("Physical", "Endurance"), ("Technical", "Anaerobic endurance")],
    "power": [("Technical", "Explosive power"), ("Physical", "Strength")],
    "upper_strength": [("Physical", "Strength")],
    "speed": [("Physical", "Speed"), ("Technical", "Reaction speed")],
    "agility": [("Physical", "Coordination"), ("Technical", "Reaction speed")],
    "core": [("Physical", "Strength"), ("Physical", "Coordination")],
    "flexibility": [("Physical", "Flexibility")],
}
# Flexibility comes from sit and reach (recorded, not ranked): cm past the toes (+) or short of them (-), against a fixed line.
FLEX_WEAK, FLEX_STRONG = 0.0, 10.0          # cannot reach the toes -> focus; 10 cm or more past them -> strength
NOT_TRAINING_DAY = {"rest", "match", "before"}
# Competition days drawn one per day (a tournament): a weak area also gets a SHORT, low-load dose on the recovery days between
# matches - easy aerobic flush, strides, reaction / footwork drills, a few low jumps, trunk and upper-body work. Never on a match
# day or the day before, and no interval conditioning (the matches carry the load).
RECOVERY_DAYS = {"between", "after", "free"}
RECOVERY_DOSE_ROWS = {("Physical", "Endurance"), ("Physical", "Speed"), ("Physical", "Strength"), ("Physical", "Coordination"),
                      ("Technical", "Reaction speed"), ("Technical", "Explosive power")}
SHORT = {"endurance": "END", "power": "PWR", "upper_strength": "UPP", "speed": "SPD", "agility": "AGI", "core": "CORE", "flexibility": "FLEX"}


def flexibility_area(sit_reach_cm: float | None) -> dict | None:
    """The sit-and-reach result as a plan area: weak when the player cannot reach the toes, strong at 10 cm or more past them."""
    if sit_reach_cm is None:
        return None
    status = "weak" if sit_reach_cm < FLEX_WEAK else "strong" if sit_reach_cm >= FLEX_STRONG else "ok"
    return {"area": "flexibility", "label": "Flexibility", "percentile": None, "status": status, "value": round(sit_reach_cm, 1),
            "detail": f"sit and reach {sit_reach_cm:+.1f} cm"}


def area_text(a: dict) -> str:
    """'Leg power (8th)' or 'Flexibility (sit and reach -7.6 cm)'."""
    return f"{a['label']} ({a['detail']})" if a.get("detail") else f"{a['label']} ({a['percentile']:.0f}th)"


def classify(areas: list[dict]) -> tuple[list[dict], list[dict]]:
    """areas: [{area, label, percentile}] -> (weak, strong), weakest first / strongest first."""
    got = [a for a in areas if a.get("percentile") is not None and a["area"] in AREA_ROWS]
    weak = sorted((a for a in got if a["percentile"] < WEAK), key=lambda a: a["percentile"])
    strong = sorted((a for a in got if a["percentile"] >= STRONG), key=lambda a: -a["percentile"])
    weak += [a for a in areas if a.get("status") == "weak" and a["area"] in AREA_ROWS]       # flexibility (sit and reach)
    strong += [a for a in areas if a.get("status") == "strong" and a["area"] in AREA_ROWS]
    return weak, strong


def _personalise(grid: dict, weak_rows: set, strong_rows: set) -> None:
    n, kinds = grid["weeks"], grid["kinds"]
    light = grid.get("recovery_weeks") or [False] * n
    dk = grid.get("day_kind_keys", [""] * n)
    off = [k in NOT_TRAINING_DAY for k in dk]
    for sec in grid["sections"]:
        for row in sec["rows"]:
            key = (sec["name"], row["label"])
            marks = row["marks"]
            if key in weak_rows:
                phases = {kinds[i] for i in range(n) if marks[i]}
                row["marks"] = [marks[i] or (kinds[i] in phases and not light[i] and not off[i])
                                or (key in RECOVERY_DOSE_ROWS and kinds[i] == "competition" and dk[i] in RECOVERY_DAYS) for i in range(n)]
            # a STRONG area keeps the squad plan's full work, so it keeps improving (it is never cut)


def personal_grid(g: dict, *, name: str, role: str, areas: list[dict]) -> dict:
    """The squad grid g (annual_grid.build_grid) made into one player's plan. Adds title, focus and the performance row."""
    weak, strong = classify(areas)
    weak_rows = {r for a in weak for r in AREA_ROWS[a["area"]]}
    strong_rows = {r for a in strong for r in AREA_ROWS[a["area"]]} - weak_rows      # a row a weak area needs is never cut
    out = copy.deepcopy(g)
    focus = ", ".join(a["label"] for a in weak) or "none below the 50th percentile"
    tested = [a["percentile"] for a in areas if a.get("percentile") is not None]
    overall = round(sum(tested) / len(tested)) if tested else None
    for grid in [out] + ([out["daily"]] if out.get("daily") else []):
        _personalise(grid, weak_rows, strong_rows)
        grid["title"] = f"ANNUAL PLAN FOR {name.upper()} ({role}) - FOCUS: {focus.upper()}"
        if g.get("year"):
            ws = g["week_starts"]
            grid["title"] += f" - {ws[0]:%d %b %Y} TO {ws[-1] + timedelta(days=6):%d %b %Y}".upper()
        # Performance index: the player's own test ranks (percentile, weakest first) from the first column, "re-test" in later test columns
        ranks = [f"{SHORT[a['area']]} {round(a['percentile'])}" for a in sorted(
            (a for a in areas if a.get("percentile") is not None and a["area"] in SHORT), key=lambda a: a["percentile"])]
        perf = [None] * grid["weeks"]
        ranks += [f"FLEX {a['value']:+.0f}cm" for a in areas if a.get("area") == "flexibility" and a.get("value") is not None]
        for i, txt in enumerate(ranks[:grid["weeks"]]):
            perf[i] = txt
        for i, t in enumerate(grid["test_weeks"]):
            if t and i >= len(ranks):
                perf[i] = "re-test"
        grid["performance"] = perf
    out["player"] = {"name": name, "role": role, "weak": weak, "strong": strong, "overall": overall,
                     "extra_endurance_reps": 1 if any(a["area"] == "endurance" for a in weak) else 0}
    return out
