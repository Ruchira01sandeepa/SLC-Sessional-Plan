"""Week-by-week planned workload for ONE player. Pure module (no database, no Excel).

Load is counted the same way as the workload engine: session RPE x minutes (arbitrary units, AU), a week = 7 days, and the load
ratio = this week / the average of the last 4 weeks. The plan starts from what the player has really been doing and builds
gradually from there.

Method, week by week (every step can only lower the load, never raise it):
  1. Shape: the squad's weekly percentage gives the shape of the season; the level comes from the player's own recent load.
     A week at the squad's lowest percentage is planned at 75% of the player's starting load, the squad's peak week at 140% of it
     (transition weeks are 60% of that), and weeks in between follow the percentage.
  2. Readiness: Caution = 80%, Hold = nothing planned until cleared.
  3. Rise cap: a week is at most 10% above the week before (not applied when the week before was tiny). After an easy week the cap
     counts from the last build week, so the player can return to that level instead of climbing back from the dip.
  4. Match and test weeks: no increase on the week before.
  5. Easy week: after three build weeks, the 4th week is 75% of the average of the last three. Also used when the player's last four
     real weeks rose every week. Transition weeks are already light.
  6. Load ratio cap: planned week / average of the last 4 weeks never goes above 1.3 (the workload engine's first flag).
  7. Matches and bowling are part of the week's load, not extra. Each squad match counts MATCH_UNITS (the plan assumes the player plays every
     match). The week's total is shared as: matches first (fixed by the calendar), then bowling (the squad load sheet's overs, which already
     respect the fast-bowler limits and count matches as bowling days; overs are only ever reduced, never added, to fit), then the
     individual focus sessions (at most 40% of the week), and what is left is general squad training. If a match week alone is above the
     limit, the plan says so instead of hiding it.

Starting load: the average weekly load of the last 4 weeks, if the player has at least 3 weeks of logged sessions. Otherwise a LOW
starting estimate (START_LOAD) is used and the plan says so. Every number is a PROPOSAL for the coach. Rises of about 10% are common
practice, not a proven safe limit for children.
"""
from __future__ import annotations

from .load_distribution import split_spells
from .workload_rules import ACWR_INFO, ACWR_MIN_HISTORY_DAYS, DEFAULT_FAST_LIMITS, WEEK_RISE_MIN_PRIOR

RISE_CAP = 0.10
ACWR_CAP = ACWR_INFO                     # 1.3
EASY_AFTER = 3                           # build weeks before an easy week
EASY_FACTOR = 0.75
LOW_FACTOR, PEAK_FACTOR = 0.75, 1.40      # planned load at the squad's lowest and highest weekly percentage, as a share of the starting load
TRANSITION_FACTOR = 0.60
START_LOAD = 900.0                       # AU per week when the player has no real history: about 4 sessions x 45 min x RPE 5
FOCUS_MIN = {"ready": 40, "caution": 30}
FOCUS_RPE = {"pre_season": 5, "pre_competition": 6, "in_season": 5, "transition": 3}
FOCUS_SHARE_MAX = 0.40
MATCH_UNITS = 600                        # one match: about 120 minutes at RPE 5 (the player's own logged RPE replaces this in real history)
BOWL_MIN_PER_OVER, BOWL_RPE = 5, 6       # an over of bowling with the walk back: about 5 minutes at RPE 6
BOWL_UNITS_PER_OVER = BOWL_MIN_PER_OVER * BOWL_RPE
BOWL_SHARE_MAX = 0.50                    # bowling at most half of the week's non-match load
MAX_BOWL_DAYS = DEFAULT_FAST_LIMITS["max_bowling_days_week"]
SPELL_MAX = DEFAULT_FAST_LIMITS["max_spell_overs"]
LOAD_FACTOR = {"ready": 1.0, "caution": 0.8, "hold": 0.0}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def plan_weeks(*, weeks: list[dict], status: str, workload: dict | None, sessions_by_phase: dict[str, int], bowler: bool = False,
               limits: dict | None = None, start_load: float | None = None, peak_factor: float | None = None) -> dict:
    """weeks: [{week, phase, percentage, matches, test, bowl_days, overs_per_day}] in order. workload: workload_rules.summarise() output
    (or None). sessions_by_phase: nominal individual focus sessions a week. bowler: the player bowls (fast, spin or all-rounder), so the
    squad sheet's bowling overs are part of the load. Returns {weeks: [...], summary: {...}}."""
    spell_max = (limits or DEFAULT_FAST_LIMITS)["max_spell_overs"]
    factor = LOAD_FACTOR[status]
    w = workload or {}
    history = w.get("history_days") or 0
    chronic = w.get("chronic_weekly_load_28d") or 0
    from_logs = history >= ACWR_MIN_HISTORY_DAYS and chronic > 0
    m1 = (weeks[0].get("matches") or 0) * MATCH_UNITS if weeks and factor else 0
    # no history: assume the player has been doing a week like the first planned week (low training load plus that week's matches)
    start_est = float(start_load or START_LOAD)
    peak = peak_factor or PEAK_FACTOR
    base = float(chronic) if from_logs else start_est + m1
    actual = [float(x) for x in (w.get("weekly_loads_oldest_first") or [])] if from_logs else []
    seq = ([base] * 4 + actual)[-4:] if not actual else ([base] * max(0, 4 - len(actual)) + actual)[-4:]
    prev = actual[-1] if actual else base
    run = EASY_AFTER if len(actual) >= 4 and actual[-1] > actual[-2] > actual[-3] > actual[-4] > 0 else 0
    pmax = max((x["percentage"] for x in weeks), default=1.0) or 1.0
    build_ref = prev                                       # the last build (non-easy) week, for returning after an easy week
    was_easy = False

    out, rises, ratios = [], [], []
    for wk in weeks:
        phase, flags = wk["phase"], []
        cap_from = max(prev, build_ref) if was_easy else prev
        raw = base * (LOW_FACTOR + (peak - LOW_FACTOR) * wk["percentage"] / pmax) * factor * (TRANSITION_FACTOR if phase == "transition" else 1.0)
        planned = raw
        easy = False
        if factor == 0:
            planned, flags = 0.0, ["On hold: no new load until a coach or physiotherapist clears the player"]
        else:
            if cap_from >= WEEK_RISE_MIN_PRIOR and planned > cap_from * (1 + RISE_CAP):
                planned = cap_from * (1 + RISE_CAP)
                flags.append("Rise limited to 10%")
            if planned > prev and (wk.get("matches") or wk.get("test")):
                planned = prev
                flags.append("Match week: no increase" if wk.get("matches") else "Test week: no increase")
            if run >= EASY_AFTER and phase != "transition":
                cap = EASY_FACTOR * _mean(seq[-3:])
                if planned > cap:
                    planned = cap
                easy = True
                flags.append("Easy week")
            chron = _mean(seq[-4:])
            if chron > 0 and planned > ACWR_CAP * chron:
                planned = ACWR_CAP * chron
                flags.append("Load ratio limited to 1.3")
        m = (wk.get("matches") or 0) * MATCH_UNITS if factor else 0
        over = bool(factor and m > planned)
        if over:
            planned = float(m)
            flags.append("Match load alone is above the weekly limit: no other training is planned. The coach should review the match minutes")
        chron = _mean(seq[-4:])
        ratio = round(planned / chron, 2) if chron > 0 and factor else None
        rise = round((planned / prev - 1) * 100, 1) if prev > 0 and factor else None
        cap_rise = round((planned / cap_from - 1) * 100, 1) if cap_from > 0 and factor else None      # the figure the 10% cap applies to
        if was_easy and rise is not None and rise > 10 and "Rise limited to 10%" not in flags:
            flags.append("Back to the build level after an easy week")
        if cap_rise is not None and cap_rise > 0:
            rises.append(cap_rise)
        if ratio is not None:
            ratios.append(ratio)

        budget = max(0.0, planned - m)
        days, opd = (wk.get("bowl_days") or 0, wk.get("overs_per_day") or 0) if bowler and factor else (0, 0)
        want = opd
        while opd > 0 and days * opd * BOWL_UNITS_PER_OVER > BOWL_SHARE_MAX * budget:
            opd -= 1
        if opd < want:
            flags.append("Bowling overs reduced to fit the load")
        if opd == 0:
            days = 0
        bowl_load = days * opd * BOWL_UNITS_PER_OVER

        sessions = sessions_by_phase.get(phase, 0) if factor else 0
        if sessions and easy:
            sessions = min(sessions, 1)
        per = FOCUS_RPE[phase] * FOCUS_MIN["caution" if status == "caution" else "ready"]
        fit = int(min(FOCUS_SHARE_MAX * planned, max(0.0, budget - bowl_load)) // per) if per else 0
        if sessions > fit:
            if factor:
                flags.append("Focus sessions reduced to fit the load")
            sessions = fit
        focus_load = sessions * per
        out.append({"week": wk["week"], "planned_load": round(planned), "matches": wk.get("matches") or 0, "match_load": m,
                    "bowl_days": days, "overs_per_day": opd, "bowl_overs_week": days * opd, "spells": "+".join(map(str, split_spells(opd, spell_max))) if opd else None,
                    "bowl_load": bowl_load, "focus_sessions": sessions, "focus_load": focus_load,
                    "general_load": max(0, round(planned - m - bowl_load - focus_load)),
                    "rise_pct": rise, "rise_cap_pct": cap_rise, "load_ratio": ratio, "easy_week": easy, "match_over_limit": over, "flags": flags})

        if easy or (factor and planned < prev * 0.9) or phase == "transition":
            run = 0
        elif factor:
            run += 1
        if not easy and factor:
            build_ref = planned
        was_easy = easy
        seq.append(planned)
        prev = planned

    return {"weeks": out, "summary": {
        "start_load": round(base), "from_logs": from_logs,
        "source": ("The player's average weekly load over the last 4 weeks of logged sessions" if from_logs else
                   f"A low starting estimate ({int(start_est)} units of training a week" + (f" plus {m1} units for the first week's match" + ("es" if weeks[0].get("matches", 0) > 1 else "") if m1 else "")
                   + "), because fewer than 3 weeks of sessions are logged. Keep logging RPE and duration; the plan will use the real load once there are 3 weeks."),
        "assumptions": f"Each squad match counts {MATCH_UNITS} units (about 120 minutes at RPE 5) and the plan assumes the player plays every match. "
                       f"Bowling counts {BOWL_UNITS_PER_OVER} units an over (about {BOWL_MIN_PER_OVER} minutes at RPE {BOWL_RPE}).",
        "match_over_limit_weeks": sum(1 for x in out if x["match_over_limit"]),
        "max_rise_pct": max(rises, default=0.0), "max_load_ratio": max(ratios, default=None),
        "easy_weeks": sum(1 for x in out if x["easy_week"]),
        "limited_weeks": sum(1 for x in out if any(f.startswith(("Rise limited", "Load ratio")) for f in x["flags"])),
        "unit": "units = session RPE x minutes"}}


def verify(result: dict, fast: bool = False, limits: dict | None = None) -> list[str]:
    """Independent re-check of the finished plan against the limits. Returns a list of violations (empty = all weeks within limits).
    Weeks where a match alone is above the limit are reported in their flags and in the summary, not hidden, and are not counted here."""
    lim = limits or DEFAULT_FAST_LIMITS
    max_days, spell_max = lim["max_bowling_days_week"], lim["max_spell_overs"]
    bad = []
    for x in result["weeks"]:
        wk = x["week"]
        if not x["match_over_limit"]:
            if x["rise_cap_pct"] is not None and x["rise_cap_pct"] > RISE_CAP * 100 + 0.6 and x["planned_load"] >= WEEK_RISE_MIN_PRIOR:
                bad.append(f"week {wk}: rise {x['rise_cap_pct']}% is above {int(RISE_CAP * 100)}%")
            if x["load_ratio"] is not None and x["load_ratio"] > ACWR_CAP + 0.01:
                bad.append(f"week {wk}: load ratio {x['load_ratio']} is above {ACWR_CAP}")
            if x["match_load"] + x["bowl_load"] + x["focus_load"] > x["planned_load"] + 1:
                bad.append(f"week {wk}: matches, bowling and focus work add up to more than the week's load")
        if x["planned_load"] and x["focus_load"] > FOCUS_SHARE_MAX * x["planned_load"] + 1e-6:
            bad.append(f"week {wk}: focus work is above {int(FOCUS_SHARE_MAX * 100)}% of the week")
        if fast:
            if x["bowl_days"] + x["matches"] > max_days:
                bad.append(f"week {wk}: {x['bowl_days']} bowling days plus {x['matches']} match(es) is above {max_days} bowling days in 7")
            if any(int(o) > spell_max for o in (x["spells"] or "").split("+") if o):
                bad.append(f"week {wk}: a spell is longer than {spell_max} overs")
    return bad
