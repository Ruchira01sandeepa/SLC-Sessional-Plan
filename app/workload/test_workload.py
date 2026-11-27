"""Workload from the SLC physical testing record (Super Provincial / U17 sheet). Pure module: no database.

The sheet's battery: 2 km run (single effort), standing broad jump x3, push-ups (max), inverted row (max), 20 m sprint x3,
5-10-5 change of direction x3, plank (max hold). Three things are worked out from it:

1. TEST-DAY LOAD - the training load of the testing session itself, in the same units as the workload log (session RPE x
   minutes), so the test day counts in the player's weekly load, load ratio and fast-bowler checks. Time comes from the
   player's OWN results where the sheet records it (2 km time, plank time) and from the number of trials actually done;
   the rest uses the protocol's standard set-up. RPE per part is a standard estimate for a maximal test (shown, so a coach
   can change it in the workload log).
2. TRAINING LOADS FROM THE TESTS - personal doses taken from the player's results: running pace from the 2 km time, sets
   from the push-up / inverted-row / plank maximum (about half to two thirds of the maximum), sprint, change-of-direction
   and jump volumes for a junior player. Lower volumes during the growth spurt.
3. FAST-BOWLER WORKLOAD - the bowling limits that apply, a SUGGESTED stricter limit when the tests show low endurance or
   core (the qualities that protect a bowler late in a spell), and the player's actual bowling from the workload log.
Every number is a PROPOSAL for the coach.
"""
from __future__ import annotations

from math import floor

# ───────────── 1. test-day load ─────────────
# part: (label, rpe, minutes per trial or None when the time comes from the result)
WARM_UP = ("Warm-up and protocol briefing", 3, 15.0)
COOL_DOWN = ("Cool-down", 2, 5.0)
PARTS = {
    "broad_jump": ("Standing broad jump", 6, 1.0),        # jump, walk back, 45-60 s rest
    "sprint_20m": ("20 m sprint", 8, 1.5),                 # sprint, walk back, 60-90 s rest
    "shuttle_5_10_5": ("5-10-5 change of direction", 8, 1.5),
    "pushups": ("Push-ups (max)", 8, 2.0),                 # one set to failure + set-up and rest
    "inverted_row": ("Inverted row (max)", 8, 2.0),
    "plank": ("Plank (max hold)", 8, None),                # time = the player's own hold
    "run_2km": ("2 km run", 9, None),                      # time = the player's own run
}
ORDER = ["broad_jump", "sprint_20m", "shuttle_5_10_5", "pushups", "inverted_row", "plank", "run_2km"]
RECOVERY_BEFORE_RUN = 5.0          # minutes of rest before the 2 km run, the last and hardest item


def _trials(r: dict) -> int:
    return sum(1 for t in (r.get("trials") or []) if t is not None) or (1 if r.get("final") is not None else 0)


def day_load(results: dict[str, dict]) -> dict:
    """results: {test_key: {"trials": [t1, t2, t3], "final": value}} with the run and plank in seconds.
    Returns {parts: [{key, label, minutes, rpe, load, basis}], minutes, rpe, load, high_intensity_minutes}."""
    parts = [{"key": "warm_up", "label": WARM_UP[0], "minutes": WARM_UP[2], "rpe": WARM_UP[1], "basis": "protocol set-up"}]
    for key in ORDER:
        r = results.get(key)
        if not r or r.get("final") is None:
            continue
        label, rpe, per = PARTS[key]
        if key == "run_2km":
            parts.append({"key": "rest", "label": "Rest before the run", "minutes": RECOVERY_BEFORE_RUN, "rpe": 1, "basis": "protocol set-up"})
            minutes, basis = r["final"] / 60, "the player's own 2 km time"
        elif key == "plank":
            minutes, basis = r["final"] / 60 + 1.0, "the player's own hold + 1 min set-up"
        else:
            n = _trials(r)
            minutes, basis = per * n, f"{n} trial{'s' if n != 1 else ''} done"
        parts.append({"key": key, "label": label, "minutes": round(minutes, 1), "rpe": rpe, "basis": basis})
    parts.append({"key": "cool_down", "label": COOL_DOWN[0], "minutes": COOL_DOWN[2], "rpe": COOL_DOWN[1], "basis": "protocol set-up"})
    for p in parts:
        p["load"] = round(p["minutes"] * p["rpe"])
    minutes = sum(p["minutes"] for p in parts)
    load = sum(p["load"] for p in parts)
    return {"parts": parts, "minutes": round(minutes), "load": load, "rpe": max(1, min(10, round(load / minutes))) if minutes else None,
            "high_intensity_minutes": round(sum(p["minutes"] for p in parts if p["rpe"] >= 8), 1)}


# ───────────── 2. training loads from the tests ─────────────
def _mmss(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def training_targets(results: dict[str, dict], *, in_spurt: bool = False, new_player: bool = False) -> list[dict]:
    """Personal doses from the test results. Each: {quality, test, result, prescription, why}."""
    out = []
    low = in_spurt or new_player
    run = (results.get("run_2km") or {}).get("final")
    if run:
        per_km = run / 2
        out.append({"quality": "Endurance", "test": "2 km run", "result": _mmss(run),
                    "prescription": f"Easy runs 15-20 min at about {_mmss(per_km * 1.25)} per km; intervals {'3-4' if low else '4-6'} x 400 m in "
                                    f"{_mmss(per_km * 0.4 * 1.05)} with the same time to recover.",
                    "why": f"Paces come from the 2 km time ({_mmss(per_km)} per km): easy about 25% slower, intervals about 5% slower than test pace."})
    bj = (results.get("broad_jump") or {}).get("final")
    if bj:
        contacts = "15-25" if low else "25-40"
        out.append({"quality": "Leg power", "test": "Standing broad jump", "result": f"{bj:.0f} cm",
                    "prescription": f"{contacts} jump-and-land contacts a session (e.g. {'3 x 5' if low else '4 x 6'} broad jumps or hops), full recovery; "
                                    f"aim past {bj + 10:.0f} cm by the next test.",
                    "why": "Junior jump volume counts landings; lower during the growth spurt or for new players."})
    sp = (results.get("sprint_20m") or {}).get("final")
    if sp:
        out.append({"quality": "Speed", "test": "20 m sprint", "result": f"{sp:.2f} s",
                    "prescription": f"{'4-6' if low else '6-8'} sprints of 10-20 m at full effort, walk-back recovery of at least 60 s; "
                                    f"target under {sp - 0.05:.2f} s.",
                    "why": "Speed is trained fresh and with full recovery; volume is kept low so every rep is fast."})
    cod = (results.get("shuttle_5_10_5") or {}).get("final")
    if cod:
        out.append({"quality": "Agility", "test": "5-10-5", "result": f"{cod:.2f} s",
                    "prescription": f"{'3-4' if low else '4-6'} change-of-direction reps (5-10-5 or 90-degree cuts) each way, 60-90 s rest; "
                                    f"target under {cod - 0.1:.2f} s.",
                    "why": "Low reps with full rest keep the cuts sharp and the knees safe."})
    for key, quality, label in (("pushups", "Upper-body strength", "push-ups"), ("inverted_row", "Upper-body strength", "inverted rows")):
        mx = (results.get(key) or {}).get("final")
        if mx:
            lo, hi = max(1, floor(mx * 0.5)), max(1, floor(mx * 0.65))
            out.append({"quality": quality, "test": "Push-ups" if key == "pushups" else "Inverted row", "result": f"{mx:.0f} reps",
                        "prescription": f"3 sets of {lo}-{hi} {label}, 60-90 s rest; add 1-2 reps a set every 2 weeks.",
                        "why": f"About half to two thirds of the test maximum ({mx:.0f}), so every set is done with good form."})
    pl = (results.get("plank") or {}).get("final")
    if pl:
        hold = max(10, round(pl * 0.5 / 5) * 5)
        out.append({"quality": "Core", "test": "Plank", "result": f"{pl:.0f} s",
                    "prescription": f"3 holds of {hold} s (front plank) plus side planks, 30-45 s rest.",
                    "why": f"Half of the test hold ({pl:.0f} s) keeps the position strict; long single holds add little."})
    return out


# ───────────── 3. fast-bowler workload ─────────────
LOW = 50.0                          # below the middle of the player's level


def bowling_advice(role: str, bowling_types: set[str] | None, limits: dict | None, defaults: dict, areas: dict[str, float | None],
                   bowling: dict | None) -> dict | None:
    """Fast bowlers and pace-bowling all-rounders only. areas: {area: percentile}; bowling: the workload summary's bowling part.
    Returns {limits, suggested, reasons, current} or None for players who do not bowl pace."""
    pace = role == "fast_bowler" or (role == "all_rounder" and "fast" in (bowling_types or set()))
    if not pace:
        return None
    base = dict(limits or defaults)
    reasons, sug = [], dict(base)
    end, core = areas.get("endurance"), areas.get("core")
    if end is not None and end < LOW:
        caution = defaults.get("caution_match_day_overs") or base.get("max_match_day_overs")
        if caution and base.get("max_match_day_overs") and caution < base["max_match_day_overs"]:
            sug["max_match_day_overs"] = caution
        reasons.append(f"Endurance is below the middle (rank {end:g}): keep match days at the caution level until it improves.")
    if core is not None and core < LOW:
        if base.get("max_spell_overs"):
            sug["max_spell_overs"] = max(3, base["max_spell_overs"] - 1)
        reasons.append(f"Core is below the middle (rank {core:g}): one over fewer per spell while trunk strength is built.")
    if not reasons:
        reasons.append("Endurance and core are at or above the middle: the normal limits apply.")
    b = bowling or {}
    return {"limits": {k: base.get(k) for k in ("max_spell_overs", "max_match_day_overs", "max_bowling_days_week")},
            "suggested": {k: sug.get(k) for k in ("max_spell_overs", "max_match_day_overs", "max_bowling_days_week")},
            "stricter": sug != base, "reasons": reasons,
            "current": {"overs_7d": b.get("overs_7d"), "bowling_days_7d": len(b.get("days_bowled_7d") or [])}}
