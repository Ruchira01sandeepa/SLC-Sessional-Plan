"""Exercise library access (data built by scripts/build_exercise_library.py)."""
import json
from functools import lru_cache
from pathlib import Path

from .exercise_kinds import KIND_LABEL, PHASE_KINDS

_PATH = Path(__file__).resolve().parent / "data" / "exercise_library.json"
_EXTRA = Path(__file__).resolve().parent / "data" / "extra_drills.json"     # batting and keeping drills added to the supplied list
ADDED_GROUPS = ("batting", "keeping")


@lru_cache(maxsize=1)
def library() -> dict:
    lib = json.loads(_PATH.read_text(encoding="utf-8"))
    extra = json.loads(_EXTRA.read_text(encoding="utf-8"))["groups"]
    for g, cats in extra.items():
        lib["groups"][g] = {c: [{**e, "added": True} for e in items] for c, items in cats.items()}
    return lib


# Which library groups apply to which player role. The supplied list covers spin bowling, fast bowling and fielding;
# batting and wicketkeeping drills are ADDED (app/data/extra_drills.json). All-rounders also get the bowling list that
# matches their bowling type.
def bowling_types(role: str, style: str | None) -> set[str] | None:
    """An all-rounder's bowling type(s) from the free-text style ("right-arm leg spin", "left-arm medium pace", ...).
    None for every other role (their bowling type follows the role)."""
    if role != "all_rounder":
        return None
    st = (style or "").lower()
    out = set()
    if "spin" in st:
        out.add("spin")
    if any(w in st for w in ("fast", "pace", "seam", "medium")):
        out.add("fast")
    return out or None


def groups_for(role: str, bowling_types: set[str] | None = None) -> list[str]:
    if role == "spin_bowler":
        return ["spin", "fielding"]
    if role == "fast_bowler":
        return ["fast", "fielding"]
    if role == "all_rounder":
        return sorted(bowling_types or {"fast", "spin"}) + ["batting", "fielding"]
    if role == "bat_wicketkeeper":
        return ["batting", "keeping", "fielding"]
    return ["batting", "fielding"]                                  # batter


def exercises_for(groups: list[str], phase: str) -> list[dict]:
    """Every exercise / activity of these groups that suits the phase, with its group, category and kind."""
    kinds = set(PHASE_KINDS[phase])
    seen, out = set(), []
    for g in groups:
        for cat in ("physical", "skill"):
            for e in library()["groups"][g][cat]:
                key = (cat, e["name"])
                if e["kind"] in kinds and key not in seen:       # shared items (e.g. plank) appear once
                    seen.add(key)
                    out.append({**e, "group": g, "category": cat})
    return out


def by_kind(exs: list[dict], category: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in exs:
        if e["category"] == category:
            out.setdefault(KIND_LABEL[e["kind"]], []).append(e["name"])
    return out
