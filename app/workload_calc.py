"""Workload calculation as in the McGawley workshop notes (Workload_Calculation_McGawley_Workshop.md). Pure module.

Prescribe -> record -> evaluate:
  * INTERNAL load (how the body responded): session RPE load (sRPE = RPE CR-10 x minutes, Foster), Edwards TRIMP (minutes in
    each heart-rate zone x 1-5), Banister TRIMP (minutes x HRr x 0.64 e^(1.92 HRr) for men, 0.86 e^(1.67 HRr) for women).
  * EXTERNAL load (what the athlete did): minutes at >= 90% HRmax, sprint metres, volume load (sets x reps x %1RM x 1RM, in kg),
    foot contacts.
  * WEEK (Monday to Sunday, rest days = 0): weekly load = sum of the days; monotony = mean daily load / SD of daily load (the
    sample SD, as in the worked example: 422 / 285 = 1.48); strain = weekly load x monotony; week-to-week change (keep it under
    about 10% unless an overload is planned); acute:chronic ratio = last 7 days / 28-day average weekly load (about 0.8-1.3 is
    often used, above about 1.5 is a spike - a WARNING FLAG only, its value is debated); weekly load % = week / heaviest week.
  * EVALUATE: % change = (post - pre) / pre x 100; effect size = (post mean - pre mean) / pre SD; performance decrement
    Sdec = total sprint time / (best time x sprints) x 100 - 100.
Every number is guidance for the coaches, never a diagnosis. Responses are individual: test and monitor rather than assume.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, stdev

EDWARDS_WEIGHTS = (1, 2, 3, 4, 5)                # 50-60, 60-70, 70-80, 80-90, 90-100% HRmax
ZONE_LABELS = ("50-60%", "60-70%", "70-80%", "80-90%", "90-100%")
WEEK_CHANGE_FLAG = 10.0                          # % - keep under about 10% unless an overload is planned
ACWR_LOW, ACWR_HIGH, ACWR_SPIKE = 0.8, 1.3, 1.5
MONOTONY_HIGH = 2.0
ACWR_MIN_DAYS = 21
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ───────────── session ─────────────
def srpe(rpe: float | None, minutes: float | None) -> float | None:
    """Session RPE load (AU) = RPE (CR-10, 0-10) x session minutes (warm-up included; ask about 30 min after the session)."""
    if rpe is None or not minutes:
        return None
    return float(rpe) * float(minutes)


def edwards_trimp(zone_minutes: list[float] | None) -> float | None:
    """Minutes in each HR zone x the zone weight (50-60% = 1 ... 90-100% = 5). 9 min x 5 + 6 x 4 + 10 x 2 = 89 AU."""
    if not zone_minutes or not any(zone_minutes):
        return None
    zm = list(zone_minutes)[:5] + [0] * (5 - len(zone_minutes))
    return float(sum((m or 0) * w for m, w in zip(zm, EDWARDS_WEIGHTS)))


def hr_reserve(hr_avg: float, hr_rest: float, hr_max: float) -> float:
    return (hr_avg - hr_rest) / (hr_max - hr_rest)


def banister_trimp(minutes: float | None, hr_avg: float | None, hr_rest: float | None, hr_max: float | None, sex: str = "male") -> float | None:
    """Minutes x HRr x 0.64 e^(1.92 HRr) (men) or 0.86 e^(1.67 HRr) (women); HRr = (HRex - HRrest) / (HRmax - HRrest).
    30 min, HR 170, rest 60, max 195 -> HRr 0.81 -> about 75 AU."""
    if not (minutes and hr_avg and hr_rest and hr_max) or hr_max <= hr_rest:
        return None
    x = max(0.0, min(1.0, hr_reserve(hr_avg, hr_rest, hr_max)))
    a, b = (0.86, 1.67) if sex == "female" else (0.64, 1.92)
    return float(minutes) * x * a * math.exp(b * x)


def estimated_hr_max(age: float | None) -> float | None:
    """When HRmax was not measured: 208 - 0.7 x age (Tanaka). An estimate; a measured value is better."""
    return round(208 - 0.7 * age) if age else None


def volume_load(sets: int, reps: int, pct_1rm: float, one_rm_kg: float) -> float:
    """sets x reps x (%1RM x 1RM). 2 x 10 at 75% of 99 kg = 1,485 kg."""
    return sets * reps * pct_1rm * one_rm_kg


def performance_decrement(times: list[float] | None) -> float | None:
    """Sdec (%) = total sprint time / (best time x number of sprints) x 100 - 100. 7.1, 7.3, 7.4, 7.6, 7.8, 7.9 s -> 5.9%."""
    t = [float(x) for x in (times or []) if x]
    if len(t) < 2:
        return None
    return sum(t) / (min(t) * len(t)) * 100 - 100


def pct_change(pre: float | None, post: float | None) -> float | None:
    """(post - pre) / pre x 100. Squat 99 -> 117 kg = +18.2%."""
    if pre in (None, 0) or post is None:
        return None
    return (post - pre) / pre * 100


def effect_size(pre: list[float], post: list[float]) -> float | None:
    """(post mean - pre mean) / pre SD. Squat: (117 - 99) / 15 = 1.2 (large)."""
    if len(pre) < 2 or not post:
        return None
    sd = stdev(pre)
    return (mean(post) - mean(pre)) / sd if sd else None


def effect_label(es: float | None) -> str:
    if es is None:
        return "-"
    a = abs(es)
    return "trivial" if a < 0.2 else "small" if a < 0.6 else "moderate" if a < 1.2 else "large" if a < 2.0 else "very large"


def acwr_band(r: float | None) -> str:
    if r is None:
        return "needs 3 weeks of data"
    return "spike - flag" if r > ACWR_SPIKE else "raised" if r > ACWR_HIGH else "low" if r < ACWR_LOW else "normal (0.8-1.3)"


# ───────────── the week ─────────────
def week_report(sessions: list[dict], monday: date, *, history: list[dict] | None = None, wellness: list[dict] | None = None,
                hr_rest: float | None = None, hr_max: float | None = None, sex: str = "male") -> dict:
    """sessions: this player's logged sessions [{date, type, attended, minutes, rpe, intensity, hr_avg, zone_minutes, hit_minutes,
    sprint_m, volume_load_kg, foot_contacts, sprint_times}]; history: all their sessions (for the previous week, the 28 days,
    the heaviest week). Returns the week's table (Monday to Sunday, as in the workshop's example week) and its indicators."""
    history = history if history is not None else sessions
    sunday = monday + timedelta(days=6)
    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        rows = []
        for s in sessions:
            if s["date"] != d:
                continue
            if not s.get("attended", True):
                rows.append({**s, "load": 0.0, "basis": "not attended"})
                continue
            load = srpe(s.get("rpe"), s.get("minutes"))
            basis = "RPE x minutes"
            if load is None and s.get("intensity") and s.get("minutes"):
                load, basis = float(s["intensity"] * s["minutes"]), "planned intensity x minutes"
            et = edwards_trimp(s.get("zone_minutes"))
            bt = banister_trimp(s.get("minutes"), s.get("hr_avg"), hr_rest, hr_max, sex)
            hit = s.get("hit_minutes")
            if hit is None and s.get("zone_minutes") and len(s["zone_minutes"]) >= 5:
                hit = s["zone_minutes"][4]                   # minutes at 90-100% HRmax
            rows.append({**s, "load": load, "basis": basis if load is not None else "no RPE", "edwards": et, "banister": bt,
                         "hit": hit, "sdec": performance_decrement(s.get("sprint_times"))})
        days.append({"date": d, "day": DAY_NAMES[i], "sessions": rows,
                     "minutes": sum(r.get("minutes") or 0 for r in rows if r.get("attended", True)),
                     "load": sum(r["load"] or 0 for r in rows)})
    daily = [d["load"] for d in days]
    total = sum(daily)
    mean_d = total / 7
    sd = stdev(daily) if any(daily) else 0.0
    monotony = mean_d / sd if sd > 0 else None

    def week_total(m: date) -> float:
        out = 0.0
        for s in history:
            if m <= s["date"] <= m + timedelta(days=6) and s.get("attended", True):
                v = srpe(s.get("rpe"), s.get("minutes"))
                if v is None and s.get("intensity") and s.get("minutes"):
                    v = float(s["intensity"] * s["minutes"])
                out += v or 0
        return out

    prev = week_total(monday - timedelta(days=7))
    change = (total - prev) / prev * 100 if prev > 0 else None
    last28 = sum(week_total(monday - timedelta(days=7 * k)) for k in range(4))
    first = min((s["date"] for s in history), default=None)
    enough = first is not None and (sunday - first).days + 1 >= ACWR_MIN_DAYS and last28 > 0
    acwr = total / (last28 / 4) if enough else None
    mondays = sorted({s["date"] - timedelta(days=s["date"].weekday()) for s in history} | {monday})
    weeks = {m: week_total(m) for m in mondays if m <= monday}
    heaviest = max(weeks.values(), default=0) or 0
    attended = [r for d in days for r in d["sessions"] if r.get("attended", True)]

    def tot(key):
        vals = [r.get(key) for r in attended if r.get(key) is not None]
        return round(sum(vals), 1) if vals else None

    sdecs = [r["sdec"] for r in attended if r.get("sdec") is not None]
    well = [w for w in (wellness or []) if monday <= w["date"] <= sunday]
    avg = lambda k: round(mean([w[k] for w in well if w.get(k) is not None]), 1) if any(w.get(k) is not None for w in well) else None
    flags = []
    if change is not None and change > WEEK_CHANGE_FLAG:
        flags.append(f"Weekly load up {change:.0f}% on last week (keep under about {WEEK_CHANGE_FLAG:.0f}% unless an overload is planned).")
    if monotony is not None and monotony > MONOTONY_HIGH:
        flags.append(f"Monotony {monotony:.2f} (above about {MONOTONY_HIGH}: too little variation between days).")
    if acwr is not None and acwr > ACWR_SPIKE:
        flags.append(f"Acute:chronic ratio {acwr:.2f} - a spike above {ACWR_SPIKE} (a warning flag, not a prediction).")
    if avg("soreness") and avg("soreness") >= 7 or avg("fatigue") and avg("fatigue") >= 7:
        flags.append("High soreness or fatigue this week: check sleep, food and school stress before adding load.")
    return {
        "monday": monday, "sunday": sunday, "days": days, "total": round(total), "mean_daily": round(mean_d), "sd_daily": round(sd),
        "monotony": round(monotony, 2) if monotony is not None else None, "strain": round(total * monotony) if monotony is not None else None,
        "previous_week": round(prev), "change_pct": round(change, 1) if change is not None else None,
        "acwr": round(acwr, 2) if acwr is not None else None, "acwr_band": acwr_band(round(acwr, 2) if acwr is not None else None),
        "chronic_weekly": round(last28 / 4), "heaviest_week": round(heaviest), "load_pct": round(total / heaviest * 100) if heaviest else None,
        "edwards_trimp": tot("edwards"), "banister_trimp": tot("banister"), "hit_minutes": tot("hit"), "sprint_m": tot("sprint_m"),
        "volume_load_kg": tot("volume_load_kg"), "foot_contacts": tot("foot_contacts"),
        "sdec": round(mean(sdecs), 1) if sdecs else None, "sessions": len(attended),
        "wellness": {"sleep_hours": avg("sleep_hours"), "soreness": avg("soreness"), "fatigue": avg("fatigue"), "days": len(well)},
        "flags": flags,
    }


# ───────────── evaluate (pre -> post, the same tests) ─────────────
def test_change(pre: dict[int, float], post: dict[int, float], lower_is_better: bool) -> dict:
    """pre / post: {player id: result} for one test. Players with both results only. % change of the means, effect size
    (pre SD), and how many players improved."""
    ids = sorted(set(pre) & set(post))
    a, b = [pre[i] for i in ids], [post[i] for i in ids]
    if not ids:
        return {"n": 0}
    es = effect_size(a, b)
    improved = sum(1 for x, y in zip(a, b) if (y < x if lower_is_better else y > x))
    return {"n": len(ids), "pre_mean": mean(a), "pre_sd": stdev(a) if len(a) > 1 else None, "post_mean": mean(b),
            "post_sd": stdev(b) if len(b) > 1 else None, "change_pct": pct_change(mean(a), mean(b)),
            "effect_size": es, "effect": effect_label(es), "improved": improved,
            "better": (mean(b) < mean(a)) if lower_is_better else (mean(b) > mean(a))}
