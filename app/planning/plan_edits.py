"""Coach edits to a player's individual plan. Pure module.

A coach changes a generated (or previously saved) plan with a list of edits; the result is saved as a new version. Edits:
  {"type": "swap",   "phase", "area", "index", "exercise"}   replace an exercise with one of that area's alternatives
  {"type": "add",    "phase", "area", "exercise"}            add one of the alternatives
  {"type": "remove", "phase", "area", "index"}
  {"type": "dose",   "phase", "area", "index", "rep"?, "set"?, "time"?, "rest"?, "rep_target"?, "sets_target"?}
  {"type": "goal",   "index", "target_display"?, "by"?, "label"?}
  {"type": "note",   "text"}
Swaps and additions only use exercises the plan already lists as alternatives for that area and phase, so a coach cannot
bring in work the phase does not allow. Every edited item is marked so the plan shows what the coach changed.
"""
from __future__ import annotations

import copy

TEXT_MAX = 120
KINDS = {"swap", "add", "remove", "dose", "goal", "note"}


class EditError(ValueError):
    pass


def _area(plan: dict, phase: str, area: str) -> dict:
    ph = next((p for p in plan["phases"] if p["phase"] == phase), None)
    if ph is None:
        raise EditError(f"The plan has no phase '{phase}'")
    a = next((x for x in ph["areas"] if x["area"] == area), None)
    if a is None:
        raise EditError(f"The plan has no area '{area}' in {phase}")
    a.setdefault("alternatives", [])
    return a


def _index(a: dict, i) -> int:
    if not isinstance(i, int) or not 0 <= i < len(a["exercises"]):
        raise EditError(f"There is no exercise number {i} in {a['label']}")
    return i


def _text(v, field: str) -> str:
    v = str(v).strip()
    if not v or len(v) > TEXT_MAX:
        raise EditError(f"{field} must be 1 to {TEXT_MAX} characters")
    return v


def _int(v, field: str, lo=1, hi=100) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise EditError(f"{field} must be a whole number from {lo} to {hi}")
    return v


def apply_edits(plan: dict, edits: list[dict]) -> dict:
    """A new plan with the edits applied in order. Raises EditError (with a message for the coach) on an invalid edit."""
    out = copy.deepcopy(plan)
    if len(edits) > 200:
        raise EditError("Too many edits at once")
    for n, e in enumerate(edits, 1):
        t = e.get("type")
        if t not in KINDS:
            raise EditError(f"Edit {n}: unknown type '{t}'")
        try:
            if t in ("swap", "add", "remove", "dose"):
                a = _area(out, e.get("phase"), e.get("area"))
            if t == "swap":
                i = _index(a, e.get("index"))
                j = next((k for k, x in enumerate(a["alternatives"]) if x["name"] == e.get("exercise")), None)
                if j is None:
                    raise EditError(f"'{e.get('exercise')}' is not an alternative for {a['label']} in this phase")
                new = {**a["alternatives"].pop(j), "edited": "swapped in by the coach"}
                old = {k: v for k, v in a["exercises"][i].items() if k != "edited"}
                a["exercises"][i] = new
                a["alternatives"].insert(0, old)
            elif t == "add":
                j = next((k for k, x in enumerate(a["alternatives"]) if x["name"] == e.get("exercise")), None)
                if j is None:
                    raise EditError(f"'{e.get('exercise')}' is not an alternative for {a['label']} in this phase")
                if len(a["exercises"]) >= 12:
                    raise EditError(f"{a['label']} already has 12 exercises")
                a["exercises"].append({**a["alternatives"].pop(j), "edited": "added by the coach"})
            elif t == "remove":
                i = _index(a, e.get("index"))
                old = a["exercises"].pop(i)
                a["alternatives"].insert(0, {k: v for k, v in old.items() if k != "edited"})
                a.setdefault("removed", []).append(old["name"])
            elif t == "dose":
                i = _index(a, e.get("index"))
                ex = a["exercises"][i]
                changed = False
                for f in ("rep", "set", "time", "rest"):
                    if f in e and e[f] is not None:
                        ex[f] = _text(e[f], f)
                        changed = True
                for f, lo in (("rep_target", "rep_start"), ("sets_target", "sets_start")):
                    if e.get(f) is not None:
                        v = _int(e[f], f)
                        if ex.get(lo) is not None and v < ex[lo]:
                            raise EditError(f"{f} cannot be below the starting value ({ex[lo]})")
                        ex[f] = v
                        changed = True
                if not changed:
                    raise EditError(f"Edit {n}: nothing to change")
                ex["edited"] = "dose changed by the coach"
                ex["basis"] = "Set by the coach."
            elif t == "goal":
                i = e.get("index")
                if not isinstance(i, int) or not 0 <= i < len(out.get("goals", [])):
                    raise EditError(f"There is no goal number {i}")
                g = out["goals"][i]
                for f in ("target_display", "by", "label"):
                    if e.get(f) is not None:
                        g[f] = _text(e[f], f)
                if e.get("target_display") is not None and g.get("current_display") and g.get("test"):
                    g["label"] = g["label"].split(":")[0] + f": {g['current_display']} to {g['target_display']} {g.get('unit', '')}".rstrip()
                g["edited"] = True
            elif t == "note":
                txt = str(e.get("text") or "").strip()
                if len(txt) > 2000:
                    raise EditError("The coach note is too long (2,000 characters at most)")
                out["coach_note"] = txt or None
        except EditError as err:
            raise EditError(f"Edit {n} ({t}): {err}") from None
    return out
