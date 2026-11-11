"""Progress against the plan, and the dose for the next session. Pure module.

The plan's progression rule, applied automatically from what was logged:
  "Start at the first number. Add one rep (or one set once the reps reach the target) every two weeks if technique stays good
   and there is no pain. Hold or step back if the player is sore or tired."
How it is applied, per exercise, in 14-day blocks from the first logged session of that exercise:
  * PROGRESS when the block has at least 2 logged sessions, technique was good every time, the prescribed reps were done
    and there was no pain: +1 rep, or +1 set once the reps are at the target (never above the targets).
  * STEP BACK when any session in the block had pain: -1 rep (or -1 set when the reps are already at the start); refer to
    the physiotherapist.
  * HOLD otherwise (too few sessions, technique not yet good, reps not completed), with the reason.
  * Readiness Caution or Hold stops progression (the dose is held) until the player is Ready again.
The block that is still running is not judged yet; the result shows the next review date.
"""
from __future__ import annotations

from datetime import date, timedelta

BLOCK_DAYS = 14
MIN_SESSIONS = 2


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def current_phase(plan: dict, today: date) -> str | None:
    weeks = plan.get("weeks") or []
    for w in weeks:
        start = _d(w["start"])
        if start <= today < start + timedelta(days=7):
            return w["phase"]
    if weeks:
        return weeks[0]["phase"] if today < _d(weeks[0]["start"]) else weeks[-1]["phase"]
    return plan["phases"][0]["phase"] if plan.get("phases") else None


def key(phase: str, area: str, name: str) -> str:
    return f"{phase}|{area}|{name}"


def _fmt(reps: int | None, sets: int | None) -> str | None:
    if reps is None or sets is None:
        return None
    return f"{reps} reps x {sets} sets"


def exercise_progress(ex: dict, logs: list[dict], today: date, readiness: str) -> dict:
    """ex: a plan exercise (rep_start, rep_target, sets_start, sets_target). logs: [{log_date, sets_done, reps_done, technique_ok, pain}]."""
    logs = sorted(logs, key=lambda l: _d(l["log_date"]))
    r0, rt, s0, st = ex.get("rep_start"), ex.get("rep_target"), ex.get("sets_start"), ex.get("sets_target")
    numeric = None not in (r0, rt, s0, st)
    reps, sets = (r0, s0) if numeric else (None, None)
    history, status, reason = [], "not_started", "Not logged yet: start at the first number."
    if logs:
        first = _d(logs[0]["log_date"])
        block_start = first
        while block_start + timedelta(days=BLOCK_DAYS) <= today + timedelta(days=1):
            block_end = block_start + timedelta(days=BLOCK_DAYS)
            blk = [l for l in logs if block_start <= _d(l["log_date"]) < block_end]
            if any(l.get("pain") for l in blk):
                if numeric:
                    if reps > r0:
                        reps -= 1
                    elif sets > s0:
                        sets -= 1
                status, reason = "stepped_back", "Pain was reported: one step back. Refer to the physiotherapist before progressing."
            elif len(blk) < MIN_SESSIONS:
                status, reason = "held", f"Only {len(blk)} session(s) in two weeks; at least {MIN_SESSIONS} are needed to progress."
            elif not all(l.get("technique_ok", True) for l in blk):
                status, reason = "held", "Technique was not yet good in every session: hold the dose."
            elif numeric and any((l.get("reps_done") or 0) < reps or (l.get("sets_done") or 0) < sets for l in blk
                                 if l.get("reps_done") is not None or l.get("sets_done") is not None):
                status, reason = "held", "Not every session reached the prescribed reps and sets: hold the dose."
            elif not numeric:
                status, reason = "on_track", f"{len(blk)} session(s) with good technique and no pain."
            elif reps < rt:
                reps += 1
                status, reason = "progressed", f"{len(blk)} good sessions with no pain: one rep added."
            elif sets < st:
                sets += 1
                status, reason = "progressed", f"{len(blk)} good sessions with no pain: reps at target, one set added."
            else:
                status, reason = "at_target", "At the target for this phase: keep the dose and keep the technique sharp."
            history.append({"from": block_start.isoformat(), "to": (block_end - timedelta(days=1)).isoformat(), "sessions": len(blk), "result": status,
                            "dose": _fmt(reps, sets)})
            block_start = block_end
        running = [l for l in logs if _d(l["log_date"]) >= block_start]
        next_review = block_start + timedelta(days=BLOCK_DAYS)
        if any(l.get("pain") for l in running):              # pain never waits for the end of the block: step back now
            if numeric:
                if reps > r0:
                    reps -= 1
                elif sets > s0:
                    sets -= 1
            status, reason = "stepped_back", "Pain was reported in this block: one step back now. Refer to the physiotherapist before progressing."
        elif not history:
            status, reason = "in_progress", f"{len(running)} session(s) logged in the first two weeks so far."
    else:
        next_review = None
    if readiness in ("caution", "hold") and status in ("progressed", "in_progress", "not_started", "on_track"):
        reason = ("Readiness is " + readiness.capitalize() + ": the dose is held until the player is Ready again. " + reason).strip()
        status = "held_readiness" if status == "progressed" else status
    return {"name": ex["name"], "current_reps": reps, "current_sets": sets, "current": _fmt(reps, sets) or ex.get("rep") and f"{ex.get('rep')} reps",
            "start": _fmt(r0, s0), "target": _fmt(rt, st), "status": status, "reason": reason, "sessions": len(logs),
            "last_logged": _d(logs[-1]["log_date"]).isoformat() if logs else None,
            "next_review": next_review.isoformat() if next_review else None, "history": history}


def plan_progress(plan: dict, logs: list[dict], today: date, readiness: str = "ready") -> dict:
    """Progress for every exercise of the plan plus adherence (focus sessions done vs planned) over the last 4 weeks.
    logs: [{log_date, phase, area, exercise, sets_done, reps_done, technique_ok, pain}]."""
    by_key: dict[str, list[dict]] = {}
    for l in logs:
        by_key.setdefault(key(l["phase"], l["area"], l["exercise"]), []).append(l)
    exercises = {}
    for ph in plan.get("phases", []):
        for a in ph["areas"]:
            for ex in a["exercises"]:
                k = key(ph["phase"], a["area"], ex["name"])
                exercises[k] = {**exercise_progress(ex, by_key.get(k, []), today, readiness), "phase": ph["phase"], "area": a["area"]}
    planned = {p["phase"]: p["sessions_per_week"] for p in plan.get("phases", [])}
    weeks = []
    for i in range(3, -1, -1):
        start = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        end = start + timedelta(days=7)
        days = {_d(l["log_date"]) for l in logs if start <= _d(l["log_date"]) < end}
        ph = current_phase(plan, start) or ""
        weeks.append({"week_start": start.isoformat(), "done": len(days), "planned": planned.get(ph, 0), "phase": ph})
    done, want = sum(w["done"] for w in weeks), sum(w["planned"] for w in weeks)
    counts: dict[str, int] = {}
    for e in exercises.values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"current_phase": current_phase(plan, today), "exercises": exercises, "adherence": {"weeks": weeks, "done": done, "planned": want,
            "pct": round(100 * done / want) if want else None}, "status_counts": counts, "logged_sessions": len({_d(l["log_date"]) for l in logs})}
