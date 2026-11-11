"""Measurable role-specific fields (the 'Role-Specific Skill Execution' column of each Development sheet).

The workbooks name these but give them no unit. Here each one gets a unit, a direction and a plausible range so
baseline / mid-season / end-of-season values can be stored and compared. Items the sheet describes in words
(e.g. 'Drift and dip', 'New-ball role', 'Primary role clarity') are 1-5 coach ratings, the same scale as the PDP.
This list is a PROPOSAL for the coaches to confirm; change it here and nothing else needs to move.
"""
from .fitness_metrics import Metric
from .models import PlayerRole as R

RATING = "1-5 rating"


def _rating(field: str, label: str) -> Metric:
    return Metric(field, label, RATING, True, 1, 5)


BATTING_AVG = Metric("batting_average", "Batting average", "runs", True, 0, 200)
STRIKE_RATE = Metric("strike_rate", "Strike rate", "runs/100 balls", True, 0, 300)
DOT_BOWL = Metric("dot_ball_pct_bowling", "Dot-ball percentage (bowling)", "%", True, 0, 100)
NEW_BALL = _rating("new_ball_role", "New-ball role")

KPIS: dict[R, tuple[Metric, ...]] = {
    R.fast_bowler: (
        Metric("avg_speed_kmh", "Average bowling speed", "km/h", True, 40, 140),
        DOT_BOWL, NEW_BALL),
    R.spin_bowler: (
        Metric("stock_ball_accuracy_pct", "Stock-ball accuracy (in target zone)", "%", True, 0, 100),
        _rating("drift_dip", "Drift and dip"), NEW_BALL),
    R.all_rounder: (
        BATTING_AVG, STRIKE_RATE, DOT_BOWL, _rating("primary_role_clarity", "Primary role clarity")),
    R.bat_wicketkeeper: (
        BATTING_AVG, STRIKE_RATE,
        Metric("catch_success_pct", "Catch success percentage", "%", True, 0, 100),
        Metric("gather_to_release_s", "Gather-to-release time", "s", False, 0.3, 5.0)),
    R.batter: (
        BATTING_AVG, STRIKE_RATE,
        Metric("dot_ball_pct_batting", "Dot-ball percentage (batting)", "%", False, 0, 100),
        Metric("pace_control_pct", "Control against pace", "%", True, 0, 100),
        Metric("spin_control_pct", "Control against spin", "%", True, 0, 100),
        Metric("machine_speed_kmh", "Bowling-machine speed handled", "km/h", True, 30, 140)),
}

ALL_KPIS: dict[str, Metric] = {}
for _role, _ms in KPIS.items():
    for _m in _ms:
        assert ALL_KPIS.setdefault(_m.field, _m) == _m, f"{_m.field} defined twice with different settings"


def kpis_for(role: R) -> tuple[Metric, ...]:
    return KPIS[role]


def validate_role_specific(role: R, data: dict | None) -> dict:
    """Check keys and ranges against the player's role. A None value means 'clear this measure'."""
    allowed = {m.field: m for m in kpis_for(role)}
    out: dict = {}
    for key, v in (data or {}).items():
        m = allowed.get(key)
        if m is None:
            raise ValueError(f"'{key}' is not a measure for {role.value.replace('_', ' ')}s")
        if v is None:
            out[key] = None
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{m.label} must be a number")
        if m.unit == RATING and v != int(v):
            raise ValueError(f"{m.label} is a whole-number rating from 1 to 5")
        if not m.lo <= v <= m.hi:
            raise ValueError(f"{m.label} {v} is outside the plausible range {m.lo}-{m.hi} {m.unit} - check the entry")
        out[key] = v
    return out
