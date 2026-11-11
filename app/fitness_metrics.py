"""Fitness metrics and the pure functions that compare a player with their own baseline, the squad and targets.

No adult / international pass-fail limits are used anywhere (spec). A player is compared only with:
  their own baseline, their individual target, the coach-defined squad benchmark, and their squad's percentile.
"""
from dataclasses import dataclass

from .models import FitnessPhase


@dataclass(frozen=True)
class Metric:
    field: str
    label: str
    unit: str
    higher_is_better: bool
    lo: float          # plausibility range for an U15 player: catches typos (3.4 entered as 34), not "standards"
    hi: float


METRICS: tuple[Metric, ...] = (
    Metric("bodyweight_kg", "Bodyweight", "kg", True, 20, 120),     # direction is neutral; shown, not judged
    Metric("height_cm", "Height", "cm", True, 100, 210),
    Metric("cmj_cm", "Countermovement jump", "cm", True, 5, 80),
    Metric("squat_jump_cm", "Squat jump", "cm", True, 5, 80),
    Metric("sprint_5m_s", "5 m sprint", "s", False, 0.8, 3.0),
    Metric("sprint_10m_s", "10 m sprint", "s", False, 1.4, 4.0),
    Metric("sprint_20m_s", "20 m sprint", "s", False, 2.5, 6.0),
    Metric("yoyo_distance_m", "Yo-Yo IR1 distance", "m", True, 0, 3000),
    Metric("prone_plank_s", "Prone plank", "s", True, 0, 900),
    Metric("side_plank_front_s", "Side plank (front)", "s", True, 0, 900),
    Metric("side_plank_back_s", "Side plank (back)", "s", True, 0, 900),
    Metric("calf_raises_front_leg", "Calf raises (front leg)", "reps", True, 0, 250),
    Metric("calf_raises_back_leg", "Calf raises (back leg)", "reps", True, 0, 250),
)
BY_FIELD = {m.field: m for m in METRICS}
# Anthropometrics are tracked but never ranked or judged "better/worse" (growth is not an achievement).
NEUTRAL = {"bodyweight_kg", "height_cm"}
PHASE_ORDER = [FitnessPhase.baseline, FitnessPhase.mid_season, FitnessPhase.end_season]
MIN_SQUAD_FOR_PERCENTILE = 5


def current_value(by_phase: dict, field: str):
    """Most recent phase that has a value -> (phase, value)."""
    for ph in reversed(PHASE_ORDER):
        t = by_phase.get(ph)
        v = getattr(t, field, None) if t else None
        if v is not None:
            return ph, v
    return None, None


def improved(m: Metric, baseline, current) -> bool | None:
    if baseline is None or current is None or m.field in NEUTRAL or current == baseline:
        return None
    return (current > baseline) == m.higher_is_better


def percentile(m: Metric, value, squad_values: list[float]) -> float | None:
    """Mid-rank percentile among squad results: 100 = best in squad, direction-aware.
    None when the squad is too small for it to mean anything."""
    if m.field in NEUTRAL or value is None or len(squad_values) < MIN_SQUAD_FOR_PERCENTILE:
        return None
    worse = sum(1 for v in squad_values if (v < value if m.higher_is_better else v > value))
    equal = sum(1 for v in squad_values if v == value)
    return round(100 * (worse + 0.5 * equal) / len(squad_values), 1)


def target_status(m: Metric, current, target) -> str | None:
    if current is None or target is None:
        return None
    return "met" if (current >= target if m.higher_is_better else current <= target) else "not_yet"
