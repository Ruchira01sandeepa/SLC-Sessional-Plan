"""Component distribution sheet: which exercise belongs in which phase. Pure module.

The supplied rugby sheet marks running components (continuous run, fartlek, tempo, intervals, sprint distances) against
General / Special / Pre-competition / Competition / Transition. The cricket version does the same with the supplied
exercise list (spin bowling, fast bowling, fielding), grouped by type of work. An 'x' means the exercise suits the phase
under exercise_kinds.PHASE_KINDS, a PROPOSAL for the coaches to confirm. Pre-season has one phase in the season, so it is
marked under both General and Special preparation.
"""
from __future__ import annotations

from .annual_grid import COMP, GENERAL, PRECOMP, SEASON_PHASE_OF, SPECIAL, TRANS
from .exercise_kinds import KIND_LABEL, PHASE_KINDS
from .exercises import groups_for, library

COLUMNS = [GENERAL, SPECIAL, PRECOMP, COMP, TRANS]
GROUP_LABEL = {"spin": "Spin bowling", "fast": "Fast bowling", "batting": "Batting (added drills)", "keeping": "Wicketkeeping (added drills)", "fielding": "Fielding and general"}
CATEGORY_LABEL = {"physical": "Physical", "skill": "Skill"}


def build_components(roles: list[str], bowling_types: set[str] | None = None) -> dict:
    groups = sorted({g for r in roles for g in groups_for(r, bowling_types)}, key=["spin", "fast", "batting", "keeping", "fielding"].index)
    lib = library()["groups"]
    blocks = []
    for g in groups:
        for cat in ("physical", "skill"):
            by_kind: dict[str, list[dict]] = {}
            for e in lib[g][cat]:
                by_kind.setdefault(e["kind"], []).append(e)
            rows = []
            for kind, items in by_kind.items():
                for i, e in enumerate(items):
                    rows.append({"type": f"{KIND_LABEL.get(kind, 'Other')}" if i == 0 else None, "name": e["name"], "purpose": e["purpose"], "areas": e["areas"],
                                 "kind": kind, "marks": [kind in PHASE_KINDS[SEASON_PHASE_OF[p]] for p in COLUMNS]})
            if rows:                                                # the added batting / keeping groups have no physical list
                blocks.append({"label": f"{GROUP_LABEL[g]} - {CATEGORY_LABEL[cat]}", "rows": rows})
    return {
        "columns": COLUMNS, "blocks": blocks,
        "notes": ["An 'x' means the exercise suits that phase. The mapping is a proposal for the coaches to confirm.",
                  "Pre-season is one phase in the season, so it is marked under both General and Special preparation.",
                  "The supplied list covers spin bowling, fast bowling and fielding only. Batting and wicketkeeping drills were ADDED (marked as added) "
                  "for coaches to review; batters and keepers use the fielding and general list for physical work."],
    }
