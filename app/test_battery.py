"""The SLC National U15 Physical Testing SOP as data. Pure module (no database, no Excel).

Two levels, different tests:
  Provincial        height + body weight, Bronco (20/40/60 m shuttles x 5 = 1,200 m, total time)
  Super Provincial  height + body weight, 2 km run, standing broad jump, push-ups, inverted row, 20 m sprint, 5-10-5, plank

Rules from the SOP: 3 trials, the best valid trial is final; results to two decimals; never estimate a missing result;
Bronco and 2 km are different tests and are never compared with each other. Times in minutes are written mm.ss
(8.25 = 8 min 25 s), so the part after the dot is seconds and must be 00 to 59.

Plausible ranges only catch typing errors. They are not standards. Coaches should confirm them.
"""
from __future__ import annotations

from dataclasses import dataclass

PROVINCIAL, SUPER = "provincial", "super_provincial"
LEVELS = (PROVINCIAL, SUPER)
LEVEL_LABEL = {PROVINCIAL: "Provincial", SUPER: "Super Provincial"}
WINDOWS = ("baseline", "mid_season", "end_season")          # same values as models.FitnessPhase
WINDOW_LABEL = {"baseline": "Baseline", "mid_season": "Mid-season", "end_season": "End of season"}

AREAS = ("endurance", "power", "upper_strength", "speed", "agility", "core")
AREA_LABEL = {"endurance": "Endurance", "power": "Leg power", "upper_strength": "Upper-body strength",
              "speed": "Speed", "agility": "Agility", "core": "Core"}


@dataclass(frozen=True)
class Test:
    key: str
    label: str
    unit: str                  # shown to the user
    kind: str                  # "mmss" (stored as seconds), "decimal", "count"
    higher_is_better: bool
    area: str
    levels: tuple[str, ...]
    lo: float                  # plausible range, in STORED units (seconds for mmss)
    hi: float
    setup: bool = False        # the SOP wants the set-up recorded (push-up and inverted-row)


TESTS: tuple[Test, ...] = (
    Test("bronco", "Bronco", "mm.ss", "mmss", False, "endurance", (PROVINCIAL,), 180, 900),
    Test("run_2km", "2 km run", "mm.ss", "mmss", False, "endurance", (SUPER,), 330, 1200),
    Test("broad_jump", "Standing broad jump", "cm", "decimal", True, "power", (SUPER,), 80, 320),
    Test("pushups", "Push-ups", "valid reps", "count", True, "upper_strength", (SUPER,), 0, 100, setup=True),
    Test("inverted_row", "Inverted row", "valid reps", "count", True, "upper_strength", (SUPER,), 0, 100, setup=True),
    Test("sprint_20m", "20 m sprint", "s", "decimal", False, "speed", (SUPER,), 2.5, 6.0),
    Test("shuttle_5_10_5", "5-10-5 shuttle", "s", "decimal", False, "agility", (SUPER,), 3.5, 10.0),
    Test("plank", "Standard plank", "s", "decimal", True, "core", (SUPER,), 5, 600),
)
BY_KEY = {t.key: t for t in TESTS}
TRIALS = 3

# height and weight are recorded for every player but never ranked (they say nothing about being fitter or weaker)
ANTHRO = {"height_cm": ("Height", "cm", 120.0, 200.0), "weight_kg": ("Body weight", "kg", 25.0, 120.0)}


def tests_for(level: str) -> list[Test]:
    return [t for t in TESTS if level in t.levels]


def area_tests(level: str, area: str) -> list[Test]:
    return [t for t in tests_for(level) if t.area == area]


def areas_for(level: str) -> list[str]:
    return [a for a in AREAS if area_tests(level, a)]


# ───────────── numbers ─────────────
def parse_mmss(value) -> float:
    """'8.25' or 8.25 -> 505.0 seconds. Always read with two decimals, because Excel drops trailing zeros (8.30 -> 8.3).
    Accepts 8:25 too. Raises ValueError with a message the admin can act on."""
    if isinstance(value, bool):
        raise ValueError("not a time")
    if isinstance(value, (int, float)):
        text = f"{float(value):.2f}"
    else:
        text = str(value).strip().replace(":", ".")
    try:
        mins_s, _, secs_s = text.partition(".")
        if not mins_s.isdigit() or (secs_s and not secs_s.isdigit()):
            raise ValueError
        mins = int(mins_s)
        if len(secs_s) > 2:
            raise ValueError
        secs = int(secs_s.ljust(2, "0")) if secs_s else 0
    except ValueError:
        raise ValueError(f"'{value}' is not a time in mm.ss (for example 8.25 for 8 min 25 s)") from None
    if secs > 59:
        raise ValueError(f"'{value}': the part after the dot is seconds and must be 00 to 59 (8.25 = 8 min 25 s)")
    return float(mins * 60 + secs)


def format_mmss(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(round(seconds))
    return f"{s // 60}.{s % 60:02d}"


def parse_value(test: Test, value, rng: tuple[float, float] | None = None) -> float:
    """One trial as typed by the admin -> stored number. Blank values are handled by the caller, never estimated.
    rng: the plausible range to check against (the squad's age group, see age_norms.plausible); the test's own range otherwise."""
    if test.kind == "mmss":
        v = parse_mmss(value)
    else:
        if isinstance(value, bool):
            raise ValueError("not a number")
        try:
            v = float(str(value).strip()) if not isinstance(value, (int, float)) else float(value)
        except ValueError:
            raise ValueError(f"'{value}' is not a number") from None
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError(f"'{value}' is not a number")
        if test.kind == "count":
            if v != int(v):
                raise ValueError(f"'{value}': repetitions must be a whole number")
            v = int(v)
        else:
            v = round(v, 2)
    lo_v, hi_v = rng or (test.lo, test.hi)
    if not lo_v <= v <= hi_v:
        lo, hi = (format_mmss(lo_v), format_mmss(hi_v)) if test.kind == "mmss" else (lo_v, hi_v)
        shown = format_mmss(v) if test.kind == "mmss" else v
        raise ValueError(f"{test.label} {shown} {test.unit} is outside the plausible range {lo} to {hi} {test.unit} - check the entry")
    return float(v)


def best_of(test: Test, trials: list[float | None]) -> float | None:
    """Best of the valid trials. None when there are none (never estimated)."""
    vals = [v for v in trials if v is not None]
    if not vals:
        return None
    return max(vals) if test.higher_is_better else min(vals)


def display(test: Test, value: float | None) -> str | None:
    if value is None:
        return None
    if test.kind == "mmss":
        return format_mmss(value)
    if test.kind == "count":
        return str(int(value))
    return f"{value:.2f}"
