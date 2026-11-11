"""Turn the supplied exercise list into structured data.
    python -m scripts.build_exercise_library
Reads  data/source/exercise_library.txt   Writes  app/data/exercise_library.json
Re-run after editing the text file."""
import json
import re
import sys
from pathlib import Path

from app.exercise_kinds import classify

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "data" / "source" / "exercise_library.txt", ROOT / "app" / "data" / "exercise_library.json"

SECTIONS = {"spin bowler exercises": "spin", "fast bowler exercises": "fast", "fielder exercises": "fielding"}
SUBSECTIONS = {"physical training": "physical", "spin-bowling skill activities": "skill",
               "fast-bowling skill activities": "skill", "fielding skill activities": "skill"}
SESSION = re.compile(r"^(?P<part>.+?)\s+[—-]\s+(?P<min>\d+)\s+minutes?:\s*(?P<what>.+)$")


def build() -> dict:
    lib = {"groups": {g: {"physical": [], "skill": []} for g in SECTIONS.values()}, "session_template": [], "guidance": []}
    group = category = None
    in_session = False
    for raw in SRC.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        low = line.lower()
        if low == "sources":
            break                                    # the export ends with a 'Sources' footer
        if low in SECTIONS:
            group, category, in_session = SECTIONS[low], None, False
        elif low in SUBSECTIONS:
            category = SUBSECTIONS[low]
        elif low.startswith("session-time example"):
            in_session = True
        elif in_session and (m := SESSION.match(line)):
            lib["session_template"].append({"part": m["part"], "minutes": int(m["min"]), "what": m["what"].rstrip(".")})
        elif in_session and line.lower().startswith("keep bowling volumes"):
            lib["guidance"].append(line)
        elif "\t" in line and group and category:
            cols = [c.strip() for c in line.split("\t")]
            if len(cols) != 3 or cols[0].lower() in ("exercise", "activity"):
                continue
            name, purpose, areas = cols
            lib["groups"][group][category].append({"name": name, "purpose": purpose, "areas": areas, "kind": classify(category, name)})
    return lib


if __name__ == "__main__":
    lib = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(lib, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    other = [(g, c, e["name"]) for g, cs in lib["groups"].items() for c, es in cs.items() for e in es if e["kind"] == "other"]
    for g, cs in lib["groups"].items():
        print(g, {c: len(es) for c, es in cs.items()})
    print("session template parts:", len(lib["session_template"]), "| unclassified:", other or "none")
    sys.exit(1 if other else 0)
