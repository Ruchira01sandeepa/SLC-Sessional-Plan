"""Role skill grids (Development / Adaptability / Progress Status sheets) and the drills that fit each skill. Pure module.

The coach marks each role skill with the workbook legend (? / Naturally good / Have to improve / Improving / Good / Complete).
In the individual plan: "Have to improve" skills become goals with drills; "Improving" skills are kept in the drills;
"Naturally good", "Good" and "Complete" are strengths. Drills are matched to the skill by the words they share (the skill rows
keep the workbook's own spellings, so common variants are normalised first) within the drills the season phase allows.
"""
from __future__ import annotations

import re

from .exercise_kinds import KIND_LABEL, PHASE_KINDS
from .exercises import groups_for, library

STATUS_LABEL = {"no_clue": "?", "naturally_good": "Naturally good", "have_to_improve": "Have to improve", "improving": "Improving",
                "good": "Good", "complete": "Complete"}
STATUS_CLASS = {"have_to_improve": "priority", "improving": "developing", "naturally_good": "strength", "good": "strength",
                "complete": "strength", "no_clue": "unknown"}
KIND_LABEL_SHEET = {"development": "Development", "adaptability_primary": "Adaptability (primary)", "adaptability_secondary": "Adaptability (secondary)",
                    "progress_skill": "Progress: skills", "progress_task": "Progress: tasks"}
SKILL_KINDS = {"foundation", "variation", "tactical", "match_prep", "analysis", "catching", "ground_fielding", "throwing", "fielding_game"}

# workbook spellings and short forms -> the word used in the drill list
NORMALISE = {"stroks": "stroke", "strokes": "stroke", "starght": "straight", "straght": "straight", "lenth": "length", "triger": "trigger",
             "alingment": "alignment", "technic": "technique", "based": "base", "bowls": "bowl", "bowling": "bowl", "batting": "bat",
             "keeping": "keep", "keeper": "keep", "runup": "run-up", "yorkers": "yorker", "catches": "catch", "catching": "catch",
             "throws": "throw", "throwing": "throw", "drives": "drive", "takes": "take", "spinners": "spin", "pacers": "pace"}
STOP = {"and", "the", "for", "with", "into", "from", "under", "new", "old", "balls", "ball", "skill", "skills", "role", "specific", "execution",
        "ungrouped", "set", "up", "drill", "good"}
BAT_WORDS = ("bat", "stroke", "drive", "shot", "feet", "range", "hitting", "length", "trigger", "strike", "line")
KEEP_WORDS = ("keep", "stump", "glove", "dismiss", "take")
BOWL_WORDS = ("bowl", "run-up", "release", "action", "delivery", "variation", "spin", "seam", "force", "control", "yorker", "bracing", "stock")
FIELD_WORDS = ("field", "catch", "throw")


def _tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z][a-z\-]+", (text or "").lower()):
        w = NORMALISE.get(w, w)
        for part in [w] + w.split("-"):
            part = NORMALISE.get(part, part)
            if len(part) > 2 and part not in STOP:
                out.add(part.rstrip("s") if len(part) > 4 else part)
    return out


def drill_groups(group: str, skill: str, role: str, bowling_types: set[str] | None) -> list[str]:
    """Which drill lists a role skill draws from: decided by its words, inside the lists of the player's role."""
    text = f"{group} {skill}".lower()
    text_n = " ".join(NORMALISE.get(w, w) for w in re.findall(r"[a-z\-]+", text))
    own = groups_for(role, bowling_types)
    bowl = [g for g in own if g in ("fast", "spin")]
    if any(w in text_n for w in KEEP_WORDS) and "keeping" in own:
        return ["keeping"]
    if any(w in text_n for w in FIELD_WORDS) and not any(w in text_n for w in BOWL_WORDS):
        return ["fielding"]
    if any(w in text_n for w in BAT_WORDS) and "batting" in own and not (bowl and any(w in text_n for w in BOWL_WORDS)):
        return ["batting"]
    if bowl:
        return bowl
    return [g for g in own if g != "fielding"] or own


def match_drills(group: str, skill: str, role: str, bowling_types: set[str] | None, phase: str, n: int = 2) -> list[dict]:
    """Up to n drills for one role skill that the phase allows, best word match first (foundation work when nothing matches)."""
    allowed = set(PHASE_KINDS[phase]) & SKILL_KINDS
    want_skill = _tokens(skill)
    want_group = _tokens(group) - want_skill
    cands = []
    for g in drill_groups(group, skill, role, bowling_types):
        for d in library()["groups"][g]["skill"]:
            if d["kind"] in allowed:
                have = _tokens(f"{d['name']} {d['purpose']} {d['areas']}")
                score = 2 * len(want_skill & have) + len(want_group & have)          # the skill's own words count double
                cands.append((score, d["kind"] == "foundation", d, g))
    cands.sort(key=lambda c: (-c[0], not c[1]))
    out, seen = [], set()
    for score, _, d, g in cands:
        if d["name"] in seen:
            continue
        if score == 0 and out:
            break
        seen.add(d["name"])
        out.append({"name": d["name"], "purpose": d["purpose"], "kind_label": KIND_LABEL[d["kind"]], "added": bool(d.get("added")),
                    "match": "close" if score else "general"})
        if len(out) >= n:
            break
    return out
