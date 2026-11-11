"""Workload and safety rules: a pure module (no database, no web) so every rule is easy to test and audit.

Sources and status of the numbers
  * Fast-bowler limits depend on the squad's age group (app/age_groups.py). U15 (5 overs a spell, 16 overs a match day,
    3 bowling days a week, a non-bowling day after a bowling day) comes from the project brief; U17 values are placeholders.
    All are PROVISIONAL until SLC / provincial approval.
  * Cricket Australia's junior guidelines for ages 13-15 are stricter on match days (12 overs, 5 per spell, 3 bowling
    days a week). The 12-over figure is used here as an early CAUTION, below the brief's hard limit of 16.
  * Spin bowlers, all-rounders, batters and keepers get NO automatic bowling limits. A coach may set limits for a
    player (Player.workload_limits) and then those apply.
  * Load = session RPE x minutes (Foster). ACWR = last 7 days / (last 28 days / 4). The 1.3 and 1.5 thresholds, the
    30 % week-on-week rise and the monotony threshold are common sport-science rules of thumb, NOT proven safe or
    unsafe cut-offs for children. They flag a conversation; they do not diagnose or predict injury.
  * Nothing here replaces the judgement of the coach or the physiotherapist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, pstdev

SEVERITY_ORDER = {"info": 1, "warn": 2, "stop": 3}

from .age_groups import PROFILES, profile as age_profile

DEFAULT_FAST_LIMITS = dict(PROFILES["U15"].fast_limits)       # U15; a squad's age group picks its own (app/age_groups.py)
LIMIT_KEYS = ("max_spell_overs", "max_match_day_overs", "max_bowling_days_week")

ACWR_WARN = 1.5
ACWR_INFO = 1.3
ACWR_MIN_HISTORY_DAYS = 21          # need three weeks of data before the ratio means anything
WEEK_RISE_WARN = 0.30               # +30 % on last week
WEEK_RISE_MIN_PRIOR = 200           # ignore the rise when last week was tiny (arbitrary units)
MONOTONY_INFO = 2.0
WELLNESS_HIGH = 8                   # soreness / fatigue 8+ of 10 (higher = worse)
SLEEP_LOW_HOURS = 7.0               # average of the last three logs; 8-10 h is the usual advice at this age
HISTORY_DAYS = 28


@dataclass
class Log:
    date: date
    session_type: str = "training"
    attended: bool = True
    duration_min: int | None = None
    rpe: int | None = None
    intensity: int | None = None
    balls_bowled: int | None = None
    overs_bowled: float | None = None
    spells: list | None = None


@dataclass
class Wellness:
    date: date
    soreness: int | None = None
    fatigue: int | None = None
    sleep_hours: float | None = None
    pain_flag: bool = False


@dataclass
class Alert:
    rule_code: str
    severity: str
    message: str
    ref_date: date | None = None        # None = a standing condition (one open alert at a time)


# ───────────── helpers ─────────────
def overs_to_balls(overs: float) -> int:
    """Cricket notation: 3.2 overs = 3 overs and 2 balls = 20 balls. Raises ValueError for 3.7."""
    whole = int(overs)
    rem = round((overs - whole) * 10)
    if rem > 5 or rem < 0 or overs < 0:
        raise ValueError("Overs use cricket notation: 3.2 means 3 overs and 2 balls (the part after the point is 0 to 5)")
    return whole * 6 + rem


def balls_to_overs(balls: int) -> float:
    return int(balls) // 6 + (int(balls) % 6) / 10


def effective_limits(role: str, custom: dict | None, age_group: str | None = None) -> dict | None:
    """Limits that apply to a player, or None when nothing is checked automatically. Fast bowlers start from their squad's
    age-group defaults; a coach's custom limits override them."""
    custom = {k: v for k, v in (custom or {}).items() if k in LIMIT_KEYS and v}
    if role == "fast_bowler":
        out = dict(age_profile(age_group).fast_limits)
        out.update(custom)
        if out["max_match_day_overs"] <= out["caution_match_day_overs"]:
            out["caution_match_day_overs"] = None
        return out
    if custom:
        return {"max_spell_overs": custom.get("max_spell_overs"), "max_match_day_overs": custom.get("max_match_day_overs"),
                "caution_match_day_overs": None, "max_bowling_days_week": custom.get("max_bowling_days_week")}
    return None


def session_load(log: Log) -> tuple[float | None, str]:
    """Foster session load: RPE x minutes. Falls back to the coach-planned intensity. Not attended = 0."""
    if not log.attended:
        return 0.0, "not attended"
    if not log.duration_min:
        return None, "no duration"
    if log.rpe:
        return float(log.rpe * log.duration_min), "RPE x minutes"
    if log.intensity:
        return float(log.intensity * log.duration_min), "planned intensity x minutes"
    return None, "no RPE or intensity"


def log_balls(log: Log) -> int:
    if not log.attended:
        return 0
    if log.balls_bowled is not None:
        return log.balls_bowled
    return overs_to_balls(log.overs_bowled) if log.overs_bowled else 0


def daily_loads(logs: list[Log], start: date, end: date) -> tuple[dict, int]:
    """date -> load for every day from start to end (rest days are 0). Also counts sessions with no measurable load."""
    out = {start + timedelta(days=i): 0.0 for i in range((end - start).days + 1)}
    unmeasured = 0
    for lg in logs:
        if lg.date in out:
            v, _ = session_load(lg)
            if v is None:
                unmeasured += 1
            else:
                out[lg.date] += v
    return out, unmeasured


def _window(daily: dict, end: date, days: int) -> list[float]:
    return [daily.get(end - timedelta(days=i), 0.0) for i in range(days)]


# ───────────── summary ─────────────
def summarise(logs: list[Log], as_of: date, limits: dict | None) -> dict:
    start = as_of - timedelta(days=HISTORY_DAYS * 2 - 1)           # 56 days: enough for "this month vs last month"
    daily, unmeasured = daily_loads(logs, start, as_of)
    acute = sum(_window(daily, as_of, 7))
    prev_week = sum(_window(daily, as_of - timedelta(days=7), 7))
    last28 = sum(_window(daily, as_of, 28))
    prev28 = sum(_window(daily, as_of - timedelta(days=28), 28))
    chronic = last28 / 4

    first = min((lg.date for lg in logs if lg.date <= as_of), default=None)
    history_days = (as_of - first).days + 1 if first else 0
    enough = history_days >= ACWR_MIN_HISTORY_DAYS and chronic > 0
    acwr = round(acute / chronic, 2) if enough else None

    wk = _window(daily, as_of, 7)
    sd = pstdev(wk)
    monotony = round(mean(wk) / sd, 2) if sd > 0 else None
    weeks = [round(sum(_window(daily, as_of - timedelta(days=7 * i), 7))) for i in range(7, -1, -1)]   # oldest first

    # bowling
    by_day: dict[date, int] = {}
    max_spell: dict[date, float] = {}
    for lg in logs:
        if not lg.attended or lg.date > as_of:
            continue
        b = log_balls(lg)
        if b:
            by_day[lg.date] = by_day.get(lg.date, 0) + b
        for sp in lg.spells or []:
            o = sp.get("overs") if isinstance(sp, dict) else None
            if o:
                max_spell[lg.date] = max(max_spell.get(lg.date, 0), float(o))
    last7 = [as_of - timedelta(days=i) for i in range(7)]
    bowled7 = sorted(d for d in by_day if d in last7)
    streak = 0
    d = as_of if as_of in by_day else as_of - timedelta(days=1)
    while d in by_day:
        streak += 1
        d -= timedelta(days=1)

    return {
        "as_of": as_of.isoformat(),
        "history_days": history_days,
        "unmeasured_sessions_8wk": unmeasured,
        "acute_load_7d": round(acute),
        "chronic_weekly_load_28d": round(chronic),
        "acwr": acwr,
        "acwr_status": ("insufficient_data" if not enough else "high" if acwr > ACWR_WARN else "raised" if acwr > ACWR_INFO else "ok"),
        "monotony_7d": monotony,
        "strain_7d": round(acute * monotony) if monotony else None,
        "weekly_loads_oldest_first": weeks,
        "vs_last_week_pct": round((acute / prev_week - 1) * 100) if prev_week > 0 else None,
        "vs_4wk_average_pct": round((acute / chronic - 1) * 100) if chronic > 0 else None,
        "month_vs_last_month_pct": round((last28 / prev28 - 1) * 100) if prev28 > 0 else None,
        "bowling": {
            "days_bowled_7d": [x.isoformat() for x in bowled7],
            "overs_7d": balls_to_overs(sum(by_day[x] for x in bowled7)),
            "overs_by_day": {x.isoformat(): balls_to_overs(by_day[x]) for x in sorted(by_day) if x in last7},
            "consecutive_bowling_days": streak,
            "limits": limits,
        },
        "_by_day": by_day, "_max_spell": max_spell, "_daily": daily,
    }


# ───────────── alerts ─────────────
def evaluate(logs: list[Log], wellness: list[Wellness], availability: str, role: str, custom_limits: dict | None,
             as_of: date, age_group: str | None = None) -> tuple[list[Alert], dict]:
    limits = effective_limits(role, custom_limits, age_group)
    s = summarise(logs, as_of, limits)
    by_day, max_spell, daily = s.pop("_by_day"), s.pop("_max_spell"), s.pop("_daily")
    out: list[Alert] = []
    last7 = [as_of - timedelta(days=i) for i in range(6, -1, -1)]
    fd = lambda d: d.strftime("%d %b")

    # 1. an unavailable player has a session on record
    if availability == "unavailable":
        for lg in logs:
            if lg.attended and as_of - timedelta(days=6) <= lg.date <= as_of and (lg.duration_min or log_balls(lg)):
                out.append(Alert("UNAVAILABLE_SESSION", "stop", f"Player is marked unavailable but a session is logged on {fd(lg.date)}. Check with the physiotherapist.", lg.date))
                break

    # 2. bowling limits
    if limits:
        ms, md, mw = limits.get("max_spell_overs"), limits.get("max_match_day_overs"), limits.get("max_bowling_days_week")
        for d in last7:
            if ms and max_spell.get(d, 0) > ms:
                out.append(Alert("BOWL_SPELL_OVERS", "stop", f"A spell of {max_spell[d]:g} overs on {fd(d)} is above the {ms}-over spell limit.", d))
            if d in by_day:
                overs = by_day[d] / 6
                if md and overs > md:
                    out.append(Alert("BOWL_DAY_OVERS", "stop", f"{balls_to_overs(by_day[d]):g} overs on {fd(d)} is above the {md}-over daily limit.", d))
                elif limits.get("caution_match_day_overs") and overs > limits["caution_match_day_overs"]:
                    out.append(Alert("BOWL_DAY_OVERS_CAUTION", "warn", f"{balls_to_overs(by_day[d]):g} overs on {fd(d)} is above {limits['caution_match_day_overs']} overs, the level Cricket Australia advises for ages 13 to 15.", d))
        days = [d for d in last7 if d in by_day]
        if mw:
            if len(days) > mw:
                out.append(Alert("BOWL_DAYS_WEEK", "stop", f"Bowled on {len(days)} of the last 7 days; the limit is {mw}. No more bowling this week.", None))
            elif len(days) == mw:
                out.append(Alert("BOWL_DAYS_WEEK", "info", f"{mw} of {mw} bowling days used in the last 7 days. No more bowling days until one drops out of the window.", None))
        # a non-bowling day after every bowling day (brief); only fast bowlers by default
        if role == "fast_bowler" or limits.get("max_bowling_days_week"):
            run = 0
            for d in last7:
                run = run + 1 if d in by_day else 0
                if run == 2:
                    out.append(Alert("BOWL_BACK_TO_BACK", "warn", f"Bowled on {fd(d - timedelta(days=1))} and {fd(d)}. Plan a non-bowling day after every bowling day.", d))
                elif run >= 3:
                    out.append(Alert("BOWL_THREE_IN_A_ROW", "stop", f"Bowled on three days in a row ending {fd(d)}.", d))

    # 3. load
    if s["acwr"] is not None:
        if s["acwr"] > ACWR_WARN:
            out.append(Alert("LOAD_ACWR", "warn", f"This week's load is {s['acwr']}x the 4-week average (above {ACWR_WARN}). Hold or reduce load.", None))
        elif s["acwr"] > ACWR_INFO:
            out.append(Alert("LOAD_ACWR", "info", f"This week's load is {s['acwr']}x the 4-week average (above {ACWR_INFO}). Increase carefully.", None))
    prev = sum(_window(daily, as_of - timedelta(days=7), 7))
    if prev >= WEEK_RISE_MIN_PRIOR and s["history_days"] >= 14 and s["acute_load_7d"] > prev * (1 + WEEK_RISE_WARN):
        out.append(Alert("LOAD_WEEK_SPIKE", "warn", f"Load is {s['vs_last_week_pct']}% above last week. Increase load gradually.", None))
    if s["monotony_7d"] and s["monotony_7d"] > MONOTONY_INFO and s["history_days"] >= 7:
        out.append(Alert("LOAD_MONOTONY", "info", f"Daily load has been very similar all week (monotony {s['monotony_7d']}). Vary hard and easy days.", None))
    if s["history_days"] >= 7 and all(daily.get(d, 0) > 0 for d in last7):
        out.append(Alert("NO_REST_DAY", "warn", "No rest day in the last 7 days.", None))

    # 4. wellness (numbers only; no medical detail ever appears in an alert)
    for w in wellness:
        if w.pain_flag and as_of - timedelta(days=2) <= w.date <= as_of:
            out.append(Alert("WELLNESS_PAIN", "stop", f"Pain flag reported on {fd(w.date)}. Reduce load and refer to the physiotherapist.", w.date))
    recent = [w for w in wellness if as_of - timedelta(days=1) <= w.date <= as_of]
    if recent:
        latest = max(recent, key=lambda w: w.date)
        high = [n for n, v in (("soreness", latest.soreness), ("fatigue", latest.fatigue)) if v is not None and v >= WELLNESS_HIGH]
        if high:
            out.append(Alert("WELLNESS_HIGH", "warn", f"High {' and '.join(high)} reported on {fd(latest.date)}. Consider an easier session.", None))
    sleeps = [w.sleep_hours for w in sorted(wellness, key=lambda w: w.date, reverse=True) if w.sleep_hours is not None and w.date <= as_of][:3]
    if len(sleeps) == 3 and mean(sleeps) < SLEEP_LOW_HOURS:
        out.append(Alert("WELLNESS_SLEEP", "info", f"Average sleep over the last three logs is {mean(sleeps):.1f} h; 8 to 10 h is usual advice at this age.", None))

    s["alerts_worst"] = max((a.severity for a in out), key=lambda x: SEVERITY_ORDER[x], default=None)
    return out, s


# ───────────── progressive overload guidance ─────────────
PHASE_FACTORS = {                       # share of the recent weekly average suggested for next week, by season phase
    "pre_season": (1.00, 1.10), "pre_competition": (1.00, 1.05), "in_season": (0.90, 1.05), "transition": (0.50, 0.80),
}


def overload_guidance(summary: dict, alerts: list[Alert], phase: str | None = None) -> dict:
    """A suggested range for NEXT week's session load. Guidance for the coach, never an instruction."""
    chronic, acute, weeks = summary["chronic_weekly_load_28d"], summary["acute_load_7d"], summary["weekly_loads_oldest_first"]
    note = ("Rule-of-thumb guidance: small, gradual rises (about 10 %) are common practice, but no increase is proven safe. "
            "Progress only if the planned work was done with acceptable technique, recovery and no pain.")
    worst = max((SEVERITY_ORDER[a.severity] for a in alerts), default=0)
    if summary["history_days"] < ACWR_MIN_HISTORY_DAYS or chronic <= 0:
        return {"action": "insufficient_data", "next_week_load": None, "reason": "Fewer than three weeks of logged sessions. Build gradually and keep logging RPE and duration.", "note": note}
    if any(a.severity == "stop" for a in alerts):
        return {"action": "reduce", "next_week_load": [round(chronic * 0.5), round(chronic * 0.7)],
                "reason": "A stop alert is open (limit exceeded, pain flag or unavailable). Reduce load and review with the coach and physiotherapist.", "note": note}
    if worst == 2:
        return {"action": "hold", "next_week_load": [round(chronic * 0.8), round(chronic * 1.0)],
                "reason": "A warning is open (high load ratio, sharp rise, no rest day or poor recovery). Do not increase this week.", "note": note}
    rising = len(weeks) >= 4 and weeks[-1] > weeks[-2] > weeks[-3] > weeks[-4] > 0
    if rising:
        return {"action": "deload", "next_week_load": [round(acute * 0.7), round(acute * 0.8)],
                "reason": "Load has risen four weeks in a row. A lighter week lets the player absorb it.", "note": note}
    lo_f, hi_f = PHASE_FACTORS.get(phase or "", (1.00, 1.10))
    lo, hi = chronic * lo_f, min(chronic * hi_f, chronic * ACWR_INFO)
    return {"action": "build" if hi_f > 1.0 and phase not in ("transition", "in_season") else "maintain" if phase != "transition" else "reduce",
            "next_week_load": [round(lo), round(hi)],
            "reason": f"No warnings open. Range is {int(lo_f * 100)}% to {int(hi_f * 100)}% of the 4-week average" + (f" for the {phase.replace('_', ' ')} phase." if phase in PHASE_FACTORS else "."), "note": note}
