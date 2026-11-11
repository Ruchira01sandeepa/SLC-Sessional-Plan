"""Which kind of work an exercise or activity is, and which season phases it belongs to.

The supplied exercise list (data/source/exercise_library.txt) says what each item is for but not WHEN in the season to
use it. The kind and the phase mapping below are a PROPOSAL for the coaches to review. Changing PHASE_KINDS changes
every generated plan; nothing else needs to move.
"""

# (keywords found in the lower-cased name, kind). First match wins, so order matters.
PHYSICAL_RULES = [
    (("plank", "pallof", "copenhagen"), "trunk_stability"),
    (("rotational throw", "woodchop", "overhead slam", "chest pass"), "rotation_power"),
    (("shoulder external", "shoulder internal", "band external", "band internal", "pull-apart", "wall slide"), "shoulder_prehab"),
    (("thoracic", "hip mobility", "single-leg balance"), "mobility_balance"),
    (("controlled landing", "dive-and-recover"), "landing"),
    (("calf raise", "nordic"), "lower_limb_resilience"),
    (("finger and wrist", "wrist roller"), "grip_wrist"),
    (("split squat", "lunge", "romanian", "glute bridge"), "leg_strength"),
    (("push-up", "band row", "pull-up", "farmer"), "upper_strength"),
    (("broad jump", "countermovement", "bounding", "power skips", "box jump", "single-leg hop"), "plyometric_power"),
    (("acceleration sprint", "20 m sprint", "reaction sprint"), "speed"),
    (("lateral shuffle", "pro-agility", "three-cone", "t-drill", "zig-zag", "ladder"), "agility"),
    (("shuttle",), "repeat_sprint"),
    (("aerobic",), "aerobic"),
]
SKILL_RULES = [
    (("video",), "analysis"),
    (("pressure", "match-simulation", "small-sided", "controlled net bowling"), "match_prep"),
    (("plan drill", "field-setting", "field-placement", "crease-position", "new-ball bowling", "old-ball",
      "death-over", "wicket-taking", "middle-overs"), "tactical"),
    (("top-spinner", "arm-ball", "googly", "drift", "turn-and-bounce", "change-of-pace", "yorker", "slower-ball",
      "swing-bowling", "bounce drill"), "variation"),
    (("catching", "catch drill", "diving catch"), "catching"),
    (("ground-fielding", "long-barrier"), "ground_fielding"),
    (("throw", "underarm flick"), "throwing"),
    (("backing-up", "run-saving"), "fielding_game"),
    (("shadow bowling", "grip and release", "run-up", "stock-ball repetition", "single-stump", "target bowling",
      "target zone", "cone target", "seam-position"), "foundation"),
]
KIND_LABEL = {
    "trunk_stability": "Trunk", "rotation_power": "Rotational / throwing power", "shoulder_prehab": "Shoulder care",
    "mobility_balance": "Mobility and balance", "landing": "Landing mechanics", "lower_limb_resilience": "Calf and hamstring resilience",
    "grip_wrist": "Grip and wrist", "leg_strength": "Leg strength", "upper_strength": "Upper-body strength",
    "plyometric_power": "Jumps and power", "speed": "Speed", "agility": "Agility", "repeat_sprint": "Repeat sprints",
    "aerobic": "Easy aerobic",
    "analysis": "Video review", "match_prep": "Pressure and match-simulation", "tactical": "Tactical", "variation": "Variations",
    "catching": "Catching", "ground_fielding": "Ground fielding", "throwing": "Throwing", "fielding_game": "Run-saving and backing-up",
    "foundation": "Action and accuracy foundations",
}

# Which kinds are used in which phase. Conservative: power and intensity arrive after the base is built;
# the transition phase has no structured bowling or high-intensity work.
PHASE_KINDS = {
    "pre_season": ["trunk_stability", "leg_strength", "upper_strength", "shoulder_prehab", "mobility_balance", "grip_wrist",
                   "lower_limb_resilience", "aerobic", "landing", "agility", "foundation", "analysis", "catching",
                   "ground_fielding", "throwing"],
    "pre_competition": ["trunk_stability", "leg_strength", "upper_strength", "shoulder_prehab", "lower_limb_resilience",
                        "grip_wrist", "landing", "rotation_power", "plyometric_power", "speed", "agility", "repeat_sprint",
                        "foundation", "variation", "tactical", "match_prep", "analysis", "catching", "ground_fielding",
                        "throwing", "fielding_game"],
    "in_season": ["trunk_stability", "shoulder_prehab", "lower_limb_resilience", "mobility_balance", "landing",
                  "leg_strength", "rotation_power", "speed", "agility", "foundation", "variation", "tactical",
                  "match_prep", "analysis", "catching", "throwing", "fielding_game"],
    "transition": ["aerobic", "mobility_balance", "trunk_stability", "shoulder_prehab", "analysis"],
}


def classify(category: str, name: str) -> str:
    n = name.lower()
    for words, kind in (PHYSICAL_RULES if category == "physical" else SKILL_RULES):
        if any(w in n for w in words):
            return kind
    return "other"
