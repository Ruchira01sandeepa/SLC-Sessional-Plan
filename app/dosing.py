"""Personal sets and reps for an exercise in a player's plan. Pure module (no database, no Excel).

The supplied exercise list has no sets or reps, so session_plans.DOSE holds conservative U15 ranges ("8-12 reps", "2-3 sets"). Here
that range is made personal:
  * Every exercise STARTS at the low end of the range (learn the movement, quality first).
  * The TARGET for the phase depends on the player: priority areas (ranked below the middle) build toward the top of the range, the
    weaker the area the higher the target; other areas are maintained near the lower-middle; untested areas stay low.
  * Phase limits: in-season work is capped at the middle of the range (maintenance), transition stays at the low end.
  * Readiness: Caution stays at the low end. Hold has no exercises at all.
Progression rule shown to the coach: add one rep, or one set once reps reach the target, every two weeks if technique stays good and
there is no pain; hold or step back if the player is sore or tired. Nothing here goes above the range in session_plans.DOSE.
"""
from __future__ import annotations

import re

from .session_plans import _dose

_RANGE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?(.*)$")
PROGRESSION = ("Start at the first number. Add one rep (or one set once the reps reach the target) every two weeks if technique stays good and there is "
               "no pain. Hold or step back if the player is sore or tired.")


def _parse(s: str):
    m = _RANGE.match(s or "")
    if not m:
        return None
    lo = int(m.group(1))
    return lo, int(m.group(2) or lo), m.group(3).rstrip()


def _at(lo: int, hi: int, t: float) -> int:
    return lo + int(round((hi - lo) * t))


def _show(start: int, target: int, suffix: str) -> str:
    return f"{start}{suffix}" if start == target else f"{start}, building to {target}{suffix}"


def personal_dose(kind: str, name: str, phase: str, *, priority: bool, percentile: float | None, status: str,
                  t_scale: float = 1.0, low_reason: str | None = None) -> dict:
    """The exercise's dose for this player: time/rep/set/rest strings, numeric start and target, and why."""
    time, rep, sets, rest = _dose(kind, name, phase)
    pr, ps = _parse(rep), _parse(sets)
    base = {"time": time, "rep": rep, "set": sets, "rest": rest, "rep_start": None, "rep_target": None, "sets_start": None, "sets_target": None,
            "basis": "Standard range for this exercise.", "progression": None}
    if pr is None or ps is None or kind == "aerobic":
        return base
    severity = 0.0 if percentile is None else max(0.0, min(1.0, (50.0 - percentile) / 50.0))
    if priority:
        t = 0.5 + 0.5 * severity
        basis = f"Priority area (rank {percentile:g} of 100): builds toward the top of the range."
    elif percentile is None:
        t, basis = 0.25, "Not tested yet: kept low until a result is available."
    else:
        t, basis = 0.25, "Maintenance: this area is at or above the middle, so it is kept near the lower end of the range."
    if t_scale != 1.0 and t > 0:                        # e.g. a new player (low training age) builds half as far
        t = round(t * t_scale, 3)
        basis += " Smaller target while the player is new to this kind of training."
    if low_reason:                                       # e.g. high-impact work during the growth spurt
        t, basis = 0.0, low_reason
    if phase == "transition":
        t, basis = 0.0, "Transition phase: low end of the range."
    elif phase == "in_season" and t > 0.5:
        t, basis = 0.5, basis.split(":")[0] + ": in-season work is capped at the middle of the range."
    if status == "caution":
        t, basis = 0.0, "Readiness is Caution: low end of the range."
    (rlo, rhi, rsuf), (slo, shi, _) = pr, ps
    rep_t, sets_t = _at(rlo, rhi, t), _at(slo, shi, t)
    return {**base, "rep": _show(rlo, rep_t, rsuf), "set": _show(slo, sets_t, ""), "rep_start": rlo, "rep_target": rep_t, "sets_start": slo,
            "sets_target": sets_t, "basis": basis, "progression": PROGRESSION}
