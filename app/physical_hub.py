"""The squad's Physical (Strength & Conditioning) page. Pure module: no database.

  1. Dashboard  - player x area ranks (the heat map), bands, priority and strength counts per area, who is not tested,
                  fast-bowler fitness (endurance, core, power, speed).
  2. S&C groups - the squad split into training groups by each player's weakest area, with one group session per group for
                  the current phase. Exercises and dose ranges come from the same picker and dosing as the personal plans,
                  so a group session never contains work the phase does not allow.
  3. Re-test    - the next test window with a suggested date, and per player and test the change since the first window.
  4. Growth     - height, mass and BMI at every test, growth rate (cm a year) and growth stage, from player_profile.growth().
Every exercise and number is a PROPOSAL for the coach.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from .category_plans import COOL_DOWN, MINUTES, WARM_UP
from .dosing import personal_dose
from .exercise_kinds import KIND_LABEL, PHASE_KINDS
from .individual_plan import _physical, _pick
from .player_profile import growth
from .session_plans import PHASE_LABEL
from .test_battery import AREA_LABEL, WINDOW_LABEL, WINDOWS

MIDDLE, STRONG = 50.0, 70.0
PACE = {"fast_bowler"}
MAX_GROUPS, MIN_GROUP = 4, 3
GROUP_MAIN = 6                       # main exercises in a group session
INJURY_KINDS = ("lower_limb_resilience", "landing", "shoulder_prehab")      # prevention work every group gets, where the phase allows it
BOWL_GROUPS = {"fast", "spin"}


def _stem(name: str) -> str:
    return " ".join(name.lower().replace(",", " ").split()[:2])          # "Easy aerobic running, 15-20 min" ~ "Easy aerobic running"


def _injury(phase: str, role_groups: list[str], taken: set[str], bowlers: bool) -> list[dict]:
    allowed = set(PHASE_KINDS[phase])
    order = ["lower_limb_resilience", "shoulder_prehab", "landing"] if bowlers else ["lower_limb_resilience", "landing"]
    want = [k for k in order if k in allowed][:2]                 # bowlers: legs + shoulder; everyone else: legs + landing
    out = []
    for k in want:
        e = next((x for x in _physical(role_groups + ["fast", "spin", "fielding"]) if x["kind"] == k and x["name"] not in taken
                  and _stem(x["name"]) not in {_stem(t) for t in taken}), None)
        if e:
            taken.add(e["name"])
            out.append({"name": e["name"], "purpose": e["purpose"], "kind": k, "kind_label": KIND_LABEL[k], "area_label": "Injury prevention",
                        **personal_dose(k, e["name"], phase, priority=False, percentile=None, status="ready")})
    return out


# ───────────── 1. dashboard ─────────────
def heatmap(players: list[dict], cats: dict[int, dict]) -> dict:
    """players: [{id, name, role, squad_no, style_pace: bool}]. cats: categorisation by player id (one window).
    Returns {areas: [{area, label}], rows: [...], summary: {...}, untested: [names], pace: [...]}."""
    order: list[str] = []
    for c in cats.values():
        for a in c["areas"]:
            if a["area"] not in order:
                order.append(a["area"])
    rows, untested = [], []
    for p in players:
        c = cats.get(p["id"])
        if c is None:
            untested.append(p["name"])
            continue
        pct = {a["area"]: a["percentile"] for a in c["areas"]}
        rows.append({"player_id": p["id"], "name": p["name"], "role": p["role"], "squad_no": p.get("squad_no"), "band": c["band"],
                     "band_label": c["band_label"], "overall": c["overall"], "areas": pct,
                     "priorities": [a["label"] for a in c["focus_areas"]],
                     "weakest": c["focus_areas"][0]["area"] if c["focus_areas"] else None})
    summary = []
    for area in order:
        vals = [r["areas"].get(area) for r in rows if r["areas"].get(area) is not None]
        summary.append({"area": area, "label": AREA_LABEL[area], "tested": len(vals),
                        "priority": sum(1 for v in vals if v < MIDDLE), "strength": sum(1 for v in vals if v >= STRONG),
                        "weakest_first": sum(1 for r in rows if r["weakest"] == area)})
    bands = {b: sum(1 for r in rows if r["band"] == b) for b in range(1, 6)}
    pace = [{"name": r["name"], "role": r["role"], **{k: r["areas"].get(k) for k in ("endurance", "core", "power", "speed")},
             "watch": [AREA_LABEL[k] for k in ("endurance", "core") if r["areas"].get(k) is not None and r["areas"][k] < MIDDLE]}
            for r in rows if r["role"] in PACE or next((p for p in players if p["id"] == r["player_id"]), {}).get("style_pace")]
    return {"areas": [{"area": a, "label": AREA_LABEL[a]} for a in order], "rows": rows, "summary": summary, "bands": bands,
            "untested": untested, "pace": pace, "tested": len(rows), "squad_size": len(players)}


# ───────────── 2. S&C groups ─────────────
GENERAL = "general"                  # the maintenance group's key in a coach's override


def make_groups(rows: list[dict], max_groups: int = MAX_GROUPS, min_size: int = MIN_GROUP, overrides: dict[int, str] | None = None) -> list[dict]:
    """Group players by their weakest area. Areas with at least min_size players become groups (the biggest first, at most
    max_groups); everyone else joins the group of their next-weakest area that exists, or a maintenance group.
    overrides: {player_id: area or "general"} - a coach's move; it always wins (and can create a group of its own)."""
    overrides = overrides or {}
    count: dict[str, int] = {}
    for r in rows:
        if r["weakest"] and r["player_id"] not in overrides:
            count[r["weakest"]] = count.get(r["weakest"], 0) + 1
    areas = [a for a, n in sorted(count.items(), key=lambda x: -x[1]) if n >= min_size][:max_groups]
    if not areas and count:                                   # a small squad: one group for the most common need
        areas = [max(count, key=count.get)]
    for a in sorted({v for v in overrides.values() if v != GENERAL}):
        if a not in areas:
            areas.append(a)
    groups = {a: [] for a in areas}
    rest = []
    moved = set()
    for r in rows:
        ov = overrides.get(r["player_id"])
        if ov:
            (rest if ov == GENERAL else groups[ov]).append(r)
            moved.add(r["player_id"])
            continue
        ranked = sorted((a for a, v in r["areas"].items() if v is not None), key=lambda a: r["areas"][a])
        home = next((a for a in ranked if a in groups and r["areas"][a] < MIDDLE), None)
        if home:
            groups[home].append(r)
        else:
            rest.append(r)
    out = [{"area": a, "label": AREA_LABEL[a] + " group", "players": ps} for a, ps in groups.items() if ps]
    if rest:
        out.append({"area": None, "label": "All-round maintenance group", "players": rest})
    for g in out:
        g["key"] = g["area"] or GENERAL
        g["players"] = sorted(({"player_id": r["player_id"], "name": r["name"], "role": r["role"], "moved": r["player_id"] in moved,
                                "rank": r["areas"].get(g["area"]) if g["area"] else r["overall"],
                                "also": [AREA_LABEL[a] for a, v in sorted(r["areas"].items(), key=lambda x: x[1] if x[1] is not None else 999)
                                         if v is not None and v < MIDDLE and a != g["area"]][:2]} for r in g["players"]),
                              key=lambda x: (x["rank"] is None, x["rank"] or 0))
    return out


def group_session(group: dict, phase: str, role_groups: list[str]) -> dict:
    """One focus session for the group: about two thirds of the main work on the group's area, the rest on the group's next
    most common need; doses are the conservative (priority, median rank) ranges of the personal plans."""
    area = group["area"]
    ranks = [p["rank"] for p in group["players"] if p["rank"] is not None]
    pct = median(ranks) if ranks else None
    second: dict[str, int] = {}
    for p in group["players"]:
        for a in p["also"]:
            second[a] = second.get(a, 0) + 1
    label_to_area = {v: k for k, v in AREA_LABEL.items()}
    other = label_to_area.get(max(second, key=second.get)) if second else None
    main, taken = [], set()
    plan = ([(area, 4), (other, 2)] if area and other else [(area, GROUP_MAIN)] if area else
            [("core", 2), ("upper_strength", 2), ("power", 2)])
    for a, n in plan:
        if not a:
            continue
        ex = [e for e in _pick(a, phase, role_groups, n + 3, priority=pct is not None, percentile=pct, ctx={"taken": taken, "seed": group["label"]})
              if e["kind"] not in INJURY_KINDS]
        kept = []
        for e in ex:                                              # no near-duplicates (two versions of the same exercise)
            if len(kept) < n and _stem(e["name"]) not in {_stem(t) for t in taken}:
                kept.append(e)
                taken.add(e["name"])
        main += [{**e, "area": a, "area_label": AREA_LABEL[a]} for e in kept]
    injury = _injury(phase, role_groups, taken, bool(BOWL_GROUPS & set(role_groups)))
    warm = WARM_UP["transition" if phase == "transition" else "default"]
    minutes = MINUTES["warm"] + MINUTES["cool"] + MINUTES["per_exercise"] * len(main) + (MINUTES["injury"] if injury else 0)
    return {"phase": phase, "phase_label": PHASE_LABEL[phase], "minutes": minutes, "focus": group["label"],
            "second_focus": AREA_LABEL.get(other) if other else None,
            "parts": [{"part": "Warm-up", "minutes": MINUTES["warm"], "items": [{"name": w} for w in warm]},
                      {"part": "Main work", "minutes": MINUTES["per_exercise"] * len(main), "items": main},
                      {"part": "Landing and injury prevention", "minutes": MINUTES["injury"] if injury else 0, "items": injury},
                      {"part": "Cool-down", "minutes": MINUTES["cool"], "items": [{"name": c} for c in COOL_DOWN]}],
            "note": "Doses are the conservative group range. Each player's own plan (Plans by category > Physical) has their personal dose."}


def current_phase(phases: list[dict], today: date) -> str | None:
    """The phase today falls in; before the season the first phase, after it the last."""
    if not phases:
        return None
    ph = sorted(phases, key=lambda p: p["start_date"])
    for p in ph:
        if p["start_date"] <= today <= p["end_date"]:
            return p["phase_type"]
    return ph[0]["phase_type"] if today < ph[0]["start_date"] else ph[-1]["phase_type"]


# ───────────── 3. re-test ─────────────
def retest_plan(season: dict, phases: list[dict], done: list[str], scheduled: list[date], today: date) -> dict:
    """The next window to test and a suggested date. done: windows with results; scheduled: fitness-test event dates."""
    nxt = next((w for w in WINDOWS if w not in done), None)
    s0, e0 = season["start_date"], season["end_date"]
    if nxt is None:
        return {"next_window": None, "text": "All three test windows are done for this season."}
    short = (e0 - s0).days + 1 < 28
    if nxt == "baseline":
        when, why = s0, "at the start of the season"
    elif nxt == "mid_season" and not short:
        comp = next((p for p in phases if p["phase_type"] == "in_season"), None)
        when = (comp["start_date"] + (comp["end_date"] - comp["start_date"]) / 2) if comp else s0 + (e0 - s0) / 2
        why = "in the middle of the in-season phase"
    else:
        nxt = "end_season"
        when, why = e0 + timedelta(days=7), "about a week after the last day, once players have recovered" if short else "at the end of the season"
        if not short:
            when = e0 - timedelta(days=6)
    when = max(when, today)
    upcoming = sorted(d for d in scheduled if d >= today)
    return {"next_window": nxt, "label": WINDOW_LABEL[nxt], "suggested_date": when, "why": why, "scheduled": upcoming[:3],
            "text": (f"Next: {WINDOW_LABEL[nxt]} test, suggested {when:%d %b %Y} ({why})."
                     + (" A fitness test is already in the calendar on " + ", ".join(f"{d:%d %b}" for d in upcoming[:3]) + "." if upcoming else
                        " Add it to the calendar so it appears in the plans and the load."))}


def progress_rows(per_player: dict[int, dict], names: dict[int, str]) -> dict:
    """per_player: test_progress.progress() output by player. Returns the squad matrix: player x test change."""
    tests: list[dict] = []
    for pr in per_player.values():
        for t in pr["tests"]:
            if t["key"] not in [x["key"] for x in tests]:
                tests.append({"key": t["key"], "label": t["label"], "unit": t["unit"]})
    rows = []
    for pid, pr in per_player.items():
        by = {t["key"]: t for t in pr["tests"]}
        rows.append({"player_id": pid, "name": names[pid], "windows": [w["window"] for w in pr["windows"]],
                     "band": pr["band_movement"]["text"] if pr["band_movement"] else None,
                     "improved": pr["tests_improved"], "compared": pr["tests_compared"],
                     "cells": {k: ({"text": by[k]["change"]["text"], "state": by[k]["change"]["state"]} if k in by and by[k]["change"] else
                                   {"text": next((v for v in reversed(list(by[k]["values"].values())) if v), "–") if k in by else "–", "state": "single"})
                               for k in [t["key"] for t in tests]}})
    rows.sort(key=lambda r: names[r["player_id"]])
    return {"tests": tests, "rows": rows, "any_compared": any(r["compared"] for r in rows)}


# ───────────── 4. growth and body data ─────────────
def growth_rows(players: list[dict], measures: dict[int, list[dict]]) -> list[dict]:
    """players: [{id, name, role, maturity_status}]. measures: {player_id: [{date, height_cm, weight_kg}]} from every test."""
    out = []
    for p in players:
        ms = sorted((m for m in measures.get(p["id"], []) if m.get("date")), key=lambda m: m["date"])
        heights = [(m["date"], m["height_cm"]) for m in ms if m.get("height_cm")]
        g = growth(heights, p.get("maturity_status"), p["role"])
        last = ms[-1] if ms else None
        bmi = round(last["weight_kg"] / (last["height_cm"] / 100) ** 2, 1) if last and last.get("height_cm") and last.get("weight_kg") else None
        out.append({"player_id": p["id"], "name": p["name"], "role": p["role"], "maturity_status": p.get("maturity_status"),
                    "measures": [{"date": m["date"], "height_cm": m.get("height_cm"), "weight_kg": m.get("weight_kg"),
                                  "bmi": round(m["weight_kg"] / (m["height_cm"] / 100) ** 2, 1) if m.get("height_cm") and m.get("weight_kg") else None}
                                 for m in ms],
                    "height_cm": last.get("height_cm") if last else None, "weight_kg": last.get("weight_kg") if last else None, "bmi": bmi,
                    "velocity_cm_yr": g["velocity_cm_yr"], "stage": g["stage"], "stage_label": g["label"], "stage_source": g["source"],
                    "in_spurt": g["in_spurt"], "bowling_window": g["bowling_window"]})
    return out


# ───────────── 5. today: what each player should do in S&C today ─────────────
ACTIONS = {"full": "Full S&C session", "upper": "Upper body and trunk only", "reduced": "Reduced session",
           "light": "Light only (activation and mobility)", "recovery": "Recovery only", "none": "No S&C today"}
ACTION_ORDER = ["none", "recovery", "light", "reduced", "upper", "full"]


def today_action(p: dict) -> dict:
    """p: {availability, alerts_worst, alert_codes, pain_recent, soreness, fatigue, sleep_avg, match_today, match_tomorrow,
    bowled_recent, role, in_spurt}. The strictest rule that applies decides; every rule that applies is listed as a reason."""
    reasons, act = [], "full"

    def stricter(a: str, why: str):
        nonlocal act
        reasons.append(why)
        if ACTION_ORDER.index(a) < ACTION_ORDER.index(act):
            act = a
    if p.get("availability") == "unavailable":
        stricter("none", "Unavailable (set by the physiotherapist).")
    if p.get("pain_recent"):
        stricter("none", "Pain reported in the last 2 days: refer to the physiotherapist.")
    if p.get("alerts_worst") == "stop":
        stricter("recovery", "A stop alert is open (workload).")
    if p.get("match_today"):
        stricter("none", "Match today.")
    elif p.get("match_tomorrow"):
        stricter("light", "Match tomorrow: nothing hard the day before.")
    if p.get("availability") == "modified":
        stricter("reduced", "Modified training (physiotherapist).")
    if p.get("alerts_worst") == "warn":
        stricter("reduced", "A workload warning is open" + (": " + ", ".join(p["alert_codes"]) if p.get("alert_codes") else "") + ".")
    if (p.get("soreness") or 0) >= 8 or (p.get("fatigue") or 0) >= 8:
        stricter("reduced", "High soreness or fatigue in the latest wellness check.")
    if p.get("bowled_recent") and p.get("role") in ("fast_bowler", "all_rounder"):
        stricter("upper", "Bowled today or yesterday: no jumps, sprints or heavy leg work.")
    notes = []
    if p.get("sleep_avg") is not None and p["sleep_avg"] < 7:
        notes.append(f"Short sleep (average {p['sleep_avg']:.1f} h).")
    if p.get("in_spurt") and act in ("full", "reduced", "upper"):
        notes.append("Growth spurt: keep jumps and sprints at the low end.")
    if act == "reduced":
        notes.append("One set fewer on every exercise; no jumps or maximal sprints.")
    if not reasons:
        reasons.append("Nothing limits training today.")
    return {"action": act, "label": ACTIONS[act], "reasons": reasons, "notes": notes}


# ───────────── 6. targets for the next test ─────────────
def test_targets(cat: dict, cohort_values: dict[str, list[float]], next_label: str | None, later: dict[str, float] | None,
                 age_group: str | None, goal_fn) -> list[dict]:
    """For each priority area (below the middle, weakest first, at most 3): the weakest test, the target for the next test and,
    when a later window has the result, whether it was reached. goal_fn = player_profile.physical_goal."""
    from .test_battery import BY_KEY, display
    out = []
    for f in cat.get("focus_areas", [])[:3]:
        area = next(a for a in cat["areas"] if a["area"] == f["area"])
        tested = [t for t in area["tests"] if t.get("percentile") is not None]
        if not tested:
            continue
        weakest = min(tested, key=lambda t: t["percentile"])
        g = goal_fn({**area, "source": "test"}, weakest["key"], cohort_values.get(weakest["key"]), next_label, age_group)
        if not g:
            continue
        row = {"area": area["label"], "test": BY_KEY[weakest["key"]].label, "unit": g["unit"], "current": g["current_display"],
               "target": g["target_display"], "rank": area["percentile"], "reached": None, "latest": None}
        if later and later.get(weakest["key"]) is not None:
            t = BY_KEY[weakest["key"]]
            v = later[weakest["key"]]
            row["latest"] = display(t, v)
            row["reached"] = v >= g["target"] if t.higher_is_better else v <= g["target"]
        out.append(row)
    return out


# ───────────── 7. group sessions logged ─────────────
SC_MARK = "sc:"                      # WorkloadLog.match_participation prefix of a logged group S&C session ("sc:endurance")


def attendance(logs: list[dict], players: list[dict], today: date, days: int = 28) -> dict:
    """logs: [{player_id, log_date, attended, group, load}] of group S&C sessions. A session is (date, group). Returns the
    sessions and, per player, attended / planned in the last `days` days (lowest attendance first)."""
    since = today - timedelta(days=days)
    recent = [x for x in logs if x["log_date"] >= since]
    sessions: dict[tuple, dict] = {}
    for x in recent:
        k = (x["log_date"], x["group"])
        s = sessions.setdefault(k, {"date": x["log_date"], "group": x["group"], "present": 0, "absent": 0, "load": 0})
        s["present" if x["attended"] else "absent"] += 1
        s["load"] += x.get("load") or 0
    per = []
    for p in players:
        mine = [x for x in recent if x["player_id"] == p["id"]]
        if mine:
            per.append({"player_id": p["id"], "name": p["name"], "attended": sum(1 for x in mine if x["attended"]), "of": len(mine)})
    return {"days": days, "sessions": sorted(sessions.values(), key=lambda s: (s["date"], s["group"]), reverse=True),
            "players": sorted(per, key=lambda r: (r["attended"] / r["of"], r["name"]))}
