"""Earlier workload: training a player did BEFORE their sessions were logged in the app, entered as one summary per week.
Pure module: no database.

Why: the load ratio needs about three weeks of history and the fast-bowler checks look back seven days, so without the
weeks before the app was used every player starts as "needs 3 weeks of logs". A coach enters, per week: sessions, average
minutes, average RPE and (bowlers) overs and bowling days. The week is spread over its days as ordinary session logs, so
the existing workload engine needs no change. The logs are marked, so re-entering a week replaces them, and a coach's own
logs are never touched.
"""
from __future__ import annotations

from datetime import date, timedelta

from .workload_rules import balls_to_overs, overs_to_balls

MARK = "earlier_week"               # stored in WorkloadLog.match_participation for the logs this module creates
MAX_WEEKS_BACK = 12


def session_days(week_start: date, sessions: int, avoid: set[date] | frozenset = frozenset()) -> list[date]:
    """Spread the sessions over the 7 days (one session a day, never two on a day). Days that already have a log are used
    last, only when the week would not fit otherwise."""
    if sessions <= 0:
        return []
    if sessions > 7:
        raise ValueError("At most 7 sessions a week (one a day) can be entered as earlier workload")
    days = [week_start + timedelta(days=i) for i in range(7)]
    free = [d for d in days if d not in avoid]
    pool = free if len(free) >= sessions else free + [d for d in days if d in avoid]
    step = len(pool) / sessions
    picked = sorted({pool[int(i * step)] for i in range(sessions)})
    i = 0
    while len(picked) < sessions:                          # rounding put two sessions on a day: fill the gaps
        if pool[i] not in picked:
            picked.append(pool[i])
        i += 1
    return sorted(picked)


def spread_week(week_start: date, *, sessions: int, minutes: int, rpe: int, overs: float | None = None, bowling_days: int | None = None,
                avoid: set[date] | frozenset = frozenset()) -> list[dict]:
    """One week summary -> session logs [{log_date, duration_min, rpe, balls_bowled, overs_bowled}]. Overs go evenly over the
    bowling days (bowling happens at a session); the extra balls go to the first days."""
    if not 0 <= sessions <= 7:
        raise ValueError("Sessions must be 0 to 7")
    if sessions and not 10 <= minutes <= 300:
        raise ValueError("Average minutes must be 10 to 300")
    if sessions and not 1 <= rpe <= 10:
        raise ValueError("Average RPE must be 1 to 10")
    balls = overs_to_balls(overs) if overs else 0
    bdays = bowling_days or (1 if balls else 0)
    if balls and bdays > sessions:
        raise ValueError("Bowling days cannot be more than the sessions in the week")
    if bdays and not balls:
        raise ValueError("Bowling days are given but no overs")
    days = session_days(week_start, sessions, avoid)
    out = []
    bowl_idx = [int(i * len(days) / bdays) for i in range(bdays)] if bdays else []
    per, extra = (divmod(balls, bdays) if bdays else (0, 0))
    k = 0
    for i, d in enumerate(days):
        row = {"log_date": d, "duration_min": minutes, "rpe": rpe, "balls_bowled": None, "overs_bowled": None}
        if i in bowl_idx:
            b = per + (1 if k < extra else 0)
            k += 1
            row["balls_bowled"], row["overs_bowled"] = b, balls_to_overs(b)
        out.append(row)
    return out


def summarise(rows: list[dict]) -> dict | None:
    """The weekly summary back from the logs this module wrote (to show what was entered)."""
    if not rows:
        return None
    balls = sum(r.get("balls_bowled") or 0 for r in rows)
    return {"sessions": len(rows), "minutes": round(sum(r["duration_min"] for r in rows) / len(rows)),
            "rpe": round(sum(r["rpe"] for r in rows) / len(rows)), "overs": balls_to_overs(balls) if balls else None,
            "bowling_days": sum(1 for r in rows if r.get("balls_bowled")) or None,
            "load": sum(r["duration_min"] * r["rpe"] for r in rows)}
