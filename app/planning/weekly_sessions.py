"""Day-by-day session plans for the seasonal plan (the supplied workbook's Session plan layout), week by week. Pure module.

The week: Tuesday and Wednesday - practice with the trainer; Monday, Thursday and Friday - practice at school (with the player's
S&C homework); no practice on Sri Lankan public holidays (sl_holidays) or on "rest" days in the Calendar. Weekends are not planned
here (matches and match practice are in the Annual plan).

Every session follows the Annual plan of its week (what is marked in the Physical, Technical and Tactical rows) and the Load
distribution sheet (100 m speed, the speed-endurance set, the 120 / 150 / 300 m runs, the player's leg power, upper-body, core and
agility doses). The week's running and doses are split over the practice days:
  Tuesday (trainer): speed - 100 m + 120 m runs, the speed-endurance set; strength; role skills.
  Wednesday (trainer): leg power (jump contacts), agility, 150 m and 300 m runs; tactics.
  Monday / Thursday / Friday (school): school practice; homework - core (Monday, Thursday), upper body (Monday, Friday),
  agility drills (Thursday), flexibility (Friday).
Days around matches follow the competition days of the Annual plan (match, day before, day after, between two matches).
With a player's own grid (player_season_plan.personal_grid) the doses are the player's, with the weak-area extras.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.planning.annual_grid import PHASE_LABEL as GRID_PHASE_LABEL, SEASON_PHASE_OF, TRANS
from app.planning.load_distribution import build_interval_loads
from app.planning.session_plans import ROLE_LABEL, build_session
from app.reference.sl_holidays import holiday

TRAINER = {1, 2}                                             # Tuesday, Wednesday
SCHOOL = {0, 3, 4}                                           # Monday, Thursday, Friday
DAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
HEADER_LINES = 4
TABLE_LINES = 90                                             # at most this many rows in one session
FOCUS_LINES = 4


def week_label(monday: date) -> str:
    """'January week 2 (11-15 Jan 2027)': the week belongs to the month of its Monday."""
    n = (monday.day - 1) // 7 + 1
    fri = monday + timedelta(days=4)
    span = f"{monday.day}-{fri.day} {fri:%b %Y}" if monday.month == fri.month else f"{monday.day} {monday:%b}-{fri.day} {fri:%b %Y}"
    return f"{MONTHS[monday.month - 1]} week {n} ({span})"


def _r(part, desc, time="", rep="", sets="", org="", rest="", head=False):
    return {"part": part, "desc": desc, "time": time, "rep": rep, "set": sets, "org": org, "rest": rest, "head": head}


# a player whose sit and reach is short of the toes: 10 minutes after every practice (static holds when warm; youth guidelines)
FLEX_FOCUS = [_r("MAIN PART", "Seated hamstring reach (both legs, knees straight)", "", "2 x 30 s", "1", "Individual", "15 s"),
              _r("MAIN PART", "Lying hamstring stretch with a band, each leg", "", "2 x 30 s", "1", "Individual", "15 s"),
              _r("MAIN PART", "Cat-camel and child's pose (lower back)", "", "8 + 30 s", "1", "Individual", ""),
              _r("MAIN PART", "Hip flexor lunge stretch, each side", "", "30 s", "2", "Individual", "")]


def block(part: str, name: str, minutes: int, items: list[dict]) -> list[dict]:
    """A timed block, as on the supplied sheet: a heading row 'NAME  N MIN', then its exercises. Empty -> nothing."""
    return [_r(part, name.upper() if name.islower() or name[0].islower() else name.upper(), f"{minutes} MIN", head=True)] \
        + [{**x, "part": part} for x in items] if items else []


# ───────────── the exercise library, as on the supplied session plan (Monday lower-body session) ─────────────
# Every list is (exercise, time, rep, set). The supplied sheet's lists are used as they are in general preparation; the other
# phases change the programme the way the phase asks (strength, then power, then maintenance) with the same layout.
STRETCHES = ["Supine Lower Back Stretches", "Foot Behind Knee Lower Back", "Rocking", "Seated gluteus Stretch", "Supine knee to Chest",
             "Walking knee to Chest", "Calf Walk", "Lying knee flexion", "Soleus Stretch", "Standing Leg Swing", "Walking Hamstring Walk",
             "Standing Groin Stretch", "Supine Hamstring Stretch", "Overhead squat", "Lateral Arm Chest", "Vertical Arm Raises",
             "Arm Rotation", "Neck Stretch(R/L)"]
SLOW_NOTE = "Rest 1 minutes for all other exercises perform exercises at a slow to moderate pace 2-4s up, 2-4 down"
LOWER = {  # Tuesday with the trainer: lower body
    "general_prep": ("Hypertrophy program", [("Back Squat", "", "12,10,10,8,8", "5"), ("Incline Leg Press", "", "12,10,10,8,8", "5"),
                                             ("Leg Extension", "", "12,10,10,8", "4"), ("Weighted Lunges", "", "12,12,12", "3"),
                                             ("Lying Hamstring Curl", "", "12,10,10,8", "4"), ("Standing Hamstring Curl", "", "12,10,10", "3"),
                                             ("Standing Calf Raises", "", "12,10,10,8", "4")]),
    "special_prep": ("Strength program", [("Back Squat", "", "8,8,6,6", "4"), ("Romanian Deadlift", "", "8,8,6,6", "4"),
                                          ("Bulgarian Split Squat", "", "8,8,8", "3"), ("Step-ups (box)", "", "10,10,10", "3"),
                                          ("Nordic Hamstring Curl (assisted)", "", "5,5,5", "3"), ("Single-leg Calf Raises", "", "12,12,12", "3")]),
    "pre_competition": ("Power program", [("Jump Squat (light)", "", "5,5,5,5", "4"), ("Trap-bar Deadlift", "", "5,5,5", "3"),
                                          ("Box Jumps", "", "5,5,5", "3"), ("Split Squat Jumps", "", "6,6,6", "3"),
                                          ("Nordic Hamstring Curl (assisted)", "", "5,5", "2"), ("Standing Calf Raises", "", "12,12", "2")]),
    "competition": ("Maintenance program (short, heavy)", [("Trap-bar Deadlift", "", "5,5,5", "3"), ("Bulgarian Split Squat", "", "6,6", "2"),
                                                           ("Box Jumps", "", "4,4,4", "3"), ("Nordic Hamstring Curl (assisted)", "", "5,5", "2"),
                                                           ("Standing Calf Raises", "", "12,12", "2")]),
}
UPPER = {  # Wednesday with the trainer: upper body
    "general_prep": ("Hypertrophy program (upper body)", [("Bench Press", "", "12,10,10,8", "4"), ("Lat Pulldown", "", "12,10,10,8", "4"),
                                                          ("Seated Cable Row", "", "12,10,10", "3"), ("Dumbbell Shoulder Press", "", "12,10,10", "3"),
                                                          ("Push-ups", "", "12,12,12", "3"), ("Biceps Curl", "", "12,10,10", "3"),
                                                          ("Triceps Pushdown", "", "12,10,10", "3"), ("Face Pull", "", "15,15", "2")]),
    "special_prep": ("Strength program (upper body)", [("Bench Press", "", "8,8,6,6", "4"), ("Pull-ups (assisted)", "", "6,6,6,6", "4"),
                                                       ("One-arm Dumbbell Row", "", "8,8,8", "3"), ("Dumbbell Shoulder Press", "", "8,8,8", "3"),
                                                       ("Medicine Ball Chest Pass", "", "8,8,8", "3"), ("Face Pull", "", "15,15", "2")]),
    "pre_competition": ("Power program (upper body)", [("Medicine Ball Chest Pass", "", "6,6,6,6", "4"),
                                                       ("Medicine Ball Rotational Throw (each side)", "", "6,6,6,6", "4"),
                                                       ("Plyometric Push-ups", "", "5,5,5", "3"), ("Pull-ups (assisted)", "", "5,5,5", "3"),
                                                       ("Band External Rotation", "", "15,15", "2")]),
    "competition": ("Maintenance program (upper body)", [("Bench Press", "", "6,6", "2"), ("Pull-ups (assisted)", "", "6,6", "2"),
                                                         ("Medicine Ball Rotational Throw (each side)", "", "5,5,5", "3"),
                                                         ("Face Pull", "", "15,15", "2")]),
}
CRUNCHES = [("Hanging Leg Raises", "", "12", "3"), ("Star plank", "", "12", "3"), ("Hollow hold", "", "20s", "3"),
            ("Land mine Rotation", "", "12", "3"), ("Plank", "", "1min", "1"), ("Right Plank", "", "1min", "1"), ("Left Plank", "", "1min", "1")]
HOMEWORK_UPPER = [("Push-ups", "", "12,12,12", "3"), ("Inverted Rows", "", "10,10,10", "3"), ("Band Pull-aparts", "", "15,15", "2"),
                  ("Pike Push-ups", "", "8,8", "2")]
MOBILITY = [("Hip flexor stretch (each side)", "30s", "2", "1"), ("Pigeon stretch (each side)", "30s", "2", "1"),
            ("Thoracic rotation (each side)", "", "10", "2"), ("Cat-camel", "", "10", "2"), ("Sleeper stretch (each side)", "30s", "2", "1"),
            ("Ankle mobility (knee to wall)", "", "10", "2")]
TRAINING_UNIT = {"general_prep": "60-70% of the maximum weight (U15: technique first; maximum estimated, never tested)",
                 "special_prep": "70-80% of the maximum weight (U15: estimated maximum)",
                 "pre_competition": "30-60% of the maximum weight moved fast (power); full recovery",
                 "competition": "70-80% of the maximum weight, low volume (retain)", "transition": "Light, recreational"}


def _ex(lst, part="MAIN PART", first_rest=""):
    return [_r(part, e, t, rp, st, "", first_rest if i == 0 else "") for i, (e, t, rp, st) in enumerate(lst)]


def warm_up() -> list[dict]:
    """WARM UP 20 MIN: light jogging, as on the supplied sheet."""
    return block("INITIAL PART", "Warm up", 20, [_r("INITIAL PART", "Light jogging", "12min")])


def stretch() -> list[dict]:
    return [_r("MAIN PART", "Stretch", head=True)] + [
        _r("MAIN PART", n, "20s", "8", "1", "circle warm up" if i == 0 else "", "MICRO REST - 2 SEC" if i == 0 else "") for i, n in enumerate(STRETCHES)]


def warm_down(ice: bool = True) -> list[dict]:
    return block("FINAL PART", "Warm down", 20, [_r("FINAL PART", "Slow walk"), _r("FINAL PART", "Stretch")] + ([_r("FINAL PART", "Ice bath")] if ice else []))


def program(name: str, lst, *, focus_sets: int = 0) -> list[dict]:
    rows = [_r("MAIN PART", name, head=True)] + _ex(lst, first_rest="MICRO REST - 30 SEC")
    if focus_sets:
        rows.append(_r("MAIN PART", f"Extra sets on the first two exercises - FOCUS", "", "", f"+{focus_sets}", "", ""))
    return rows


def note(text: str) -> list[dict]:
    return [_r("MAIN PART", text, head=True)]


def _items(ses: dict, name: str) -> list[dict]:
    return next((p["items"] for p in ses["parts"] if p["name"].startswith(name)), [])


def _split(v, parts: int, i: int):
    if not v:
        return 0
    base, extra = divmod(int(v), parts)
    return base + (1 if i < extra else 0)


def _from(it: dict, part: str) -> dict:
    return _r(part, it["desc"], it.get("time", ""), it.get("rep", ""), it.get("set", ""), it.get("org", ""), it.get("rest", ""))


def build_weeks(g: dict, *, roles: list[str], extra_off: dict[date, str] | None = None) -> dict:
    """g: the annual grid (annual_grid.build_grid(year=True)) or a player's personal grid. Returns {weeks: [{label, monday,
    days: [{date, day, kind, title, header: [..4 lines], rows: [...], focus: [...]}]}], notes}."""
    extra_off = extra_off or {}
    n, kinds, starts = g["weeks"], g["kinds"], g["week_starts"]
    s0 = starts[0]
    last = starts[-1] + timedelta(days=6)
    d = g.get("daily") or {}
    dk = d.get("day_kind_keys") or []
    ld = build_interval_loads(g)
    focus = {f["area"]: f for f in ld["focus"]}
    marks = {(s["name"], r["label"]): r["marks"] for s in g["sections"] for r in s["rows"]}
    on = lambda sec, label, w: bool(marks.get((sec, label), [False] * n)[w])
    player = g.get("player")
    weak = {a["area"] for a in (player or {}).get("weak", [])}
    macros = {w: num for a, b, num in g["macros"] for w in range(a, b + 1)}
    sessions = {}

    def base_session(phase):
        if phase not in sessions:
            sessions[phase] = {r: build_session(r, phase) for r in roles}
        return sessions[phase]

    def day_plan(day: date) -> dict:
        wd = day.weekday()
        if day < s0 or day > last:
            return {"kind": "outside", "title": f"{DAY_NAME[wd]} {day:%d %b %Y} - outside this plan's year", "header": [], "rows": []}
        w = (day - s0).days // 7
        k = kinds[w]
        phase = SEASON_PHASE_OF[k]
        idx = (day - s0).days
        kday = dk[idx] if idx < len(dk) else ""
        meta = [f"Phase: {GRID_PHASE_LABEL[k]} · Macro {macros.get(w, '-')} · Micro {w + 1} · planned load {int(round(g['percentage'][w] * 100))}%"]
        hol = holiday(day) or extra_off.get(day)
        if hol:
            return {"kind": "holiday", "title": f"{DAY_NAME[wd]} {day:%d %b %Y} - NO PRACTICE: {hol}",
                    "header": [f"Public holiday / rest day: {hol}. No practice.", meta[0], "Optional: rest, family time, easy walk or swim.", ""],
                    "rows": [_r("REST", "No practice (public holiday / rest day)", "", "", "", "Home", "Full day")]}
        ses = base_session(phase)
        first = ses[roles[0]]
        warm = [_from(x, "INITIAL PART") for x in _items(first, "Warm-up")][:4] or [_r("INITIAL PART", "Easy jog and dynamic mobility", "10 min")]
        cool = [_from(x, "FINAL PART") for x in _items(first, "Cool-down")][:3] or [_r("FINAL PART", "Easy walk and stretching", "10 min")]
        strength = _items(first, "Strength") or _items(first, "Trunk")
        power = _items(first, "Power")
        injury = _items(first, "Injury")
        stations = [_r("MAIN PART", f"[{ROLE_LABEL[r]}] {it['desc']}", it.get("time", ""), it.get("rep", ""), it.get("set", ""),
                       it.get("org", "") or "Role stations", it.get("rest", "")) for r in roles for it in _items(ses[r], "Role-specific")[:2 if len(roles) > 1 else 4]]
        rows: list[dict] = []
        # around matches: the competition days of the Annual plan
        if kday == "match":
            return {"kind": "match", "title": f"{DAY_NAME[wd]} {day:%d %b %Y} - MATCH DAY", "header": ["Match day: warm-up, activation, match, recovery.", meta[0],
                    "Fluids every drinks break; food within 30 min after.", "Fast bowlers: match overs count towards the bowling limits."],
                    "rows": [_r("INITIAL PART", "Match warm-up: easy jog, dynamic mobility, 3-4 strides at 80-90%", "20 min", "", "", "Team"),
                             _r("MAIN PART", "MATCH", "match", "", "", "Team"),
                             _r("FINAL PART", "Recovery: easy walk, stretching, fluids and food", "15 min", "", "", "Team")]}
        if kday in ("after", "between"):
            rows = block("INITIAL PART", "Warm-up (easy)", 10, warm[:2]) \
                + block("MAIN PART", "Recovery", 25, [_r("MAIN PART", "Easy aerobic: bike, swim or walk-jog at talking pace", "15 min", "", "", "Group"),
                                                      _r("MAIN PART", "Mobility and injury prevention", "10 min", "", "", "Individual")]) \
                + (block("MAIN PART", "Upper body and trunk (short retaining strength)", 15,
                         [_r("MAIN PART", "Push-ups, band rows, side plank", "", "10", "2", "Stations", "60 s")]) if kday == "after" else []) \
                + (block("MAIN PART", "Activation for the next match", 5, [_r("MAIN PART", "Quick feet, short strides", "", "2-3", "1", "Group", "full")])
                   if kday == "between" else []) + block("FINAL PART", "Cool-down", 10, cool[:2])
            kind = "recovery"
            title = f"{DAY_NAME[wd]} {day:%d %b %Y} - RECOVERY ({'day after a match' if kday == 'after' else 'between two matches'})"
            topic = "Recovery between matches"
        elif kday == "before":
            rows = block("INITIAL PART", "Warm-up", 15, warm[:3]) \
                + block("MAIN PART", "Speed (fresh, no heavy work)", 10, [_r("MAIN PART", "20 m at about 90% effort", "", "3", "1", "Small groups", "full recovery")]) \
                + block("MAIN PART", "Match preparation (role stations)", 30, stations[:4]) + block("FINAL PART", "Cool-down", 10, cool[:2])
            kind, title, topic = "prematch", f"{DAY_NAME[wd]} {day:%d %b %Y} - DAY BEFORE A MATCH", "Activation and match preparation"
        elif k == TRANS:
            if wd in TRAINER:
                rows = block("INITIAL PART", "Warm-up", 10, warm[:2]) \
                    + block("MAIN PART", "Active rest", 55, [_r("MAIN PART", "Recreational games (football, basketball) or swimming", "40 min", "", "", "Group"),
                                                             _r("MAIN PART", "Trunk and mobility circuit", "15 min", "", "2", "Stations")]) \
                    + block("FINAL PART", "Cool-down", 10, cool[:2])
                kind, title, topic = "trainer", f"{DAY_NAME[wd]} {day:%d %b %Y} - WITH THE TRAINER: active rest", "Active rest (transition)"
            else:
                rows = block("MAIN PART", "Free play", 40, [_r("MAIN PART", "Free play or another sport; no structured cricket training", "30-40 min", "", "", "Free")]) \
                    + block("FINAL PART", "Stretching", 10, [_r("FINAL PART", "Stretching: hips, hamstrings, shoulders", "10 min", "", "", "Individual")])
                kind, title, topic = "school", f"{DAY_NAME[wd]} {day:%d %b %Y} - SCHOOL: free play (transition)", "Active rest (transition)"
        elif wd == 1:                                            # Tuesday, with the trainer: lower body + speed
            name, lst = LOWER[k]
            sp, speed = ld["speed_100m"][w], []
            if sp:
                speed.append(_r("MAIN PART", f"100 m runs at {int(round(sp * 100))}% of maximal speed", "", "3-4", "1", "Small groups", "walk back, full recovery"))
            if ld["speed_endurance_reps"][w]:
                speed.append(_r("MAIN PART", f"Anaerobic endurance (speed): {ld['speed_endurance_m'][w]} m runs" + (" - FOCUS (speed)" if "speed" in weak else ""),
                                "", str(ld["speed_endurance_reps"][w]), "1", "Pairs", "1:5 work:rest"))
            if ld["runs"][120][w]:
                speed.append(_r("MAIN PART", "Interval run 120 m" + (" - FOCUS (endurance)" if "endurance" in weak else ""), "", str(ld["runs"][120][w]), "1",
                                "Group", "1:3 work:rest"))
            rows = warm_up() + stretch() + note(SLOW_NOTE) \
                + (program(name, lst, focus_sets=1 if "power" in weak else 0) if on("Physical", "Strength", w) or k != "general_prep" else []) \
                + note("MACRO REST 3 MIN") + block("MAIN PART", "Speed and running", 20, speed) \
                + [_r("MAIN PART", "Crunches", head=True)] + _ex(CRUNCHES) + warm_down()
            kind, title, topic = "trainer", f"{DAY_NAME[wd]} {day:%d %b %Y} - WITH THE TRAINER: lower body and speed", "Lower body and speed"
            unit = TRAINING_UNIT[k]
        elif wd == 2:                                            # Wednesday, with the trainer: upper body, power, conditioning, skills
            name, lst = UPPER[k]
            pw = []
            jumps = (focus.get("power") or {}).get("values", [None] * n)[w]
            if jumps:
                pw.append(_r("MAIN PART", f"Leg power: jumps and bounds ({jumps} contacts)" + (" - FOCUS" if "power" in weak else ""), "", "", "",
                             "Small groups, grass", "full recovery"))
            agi = (focus.get("agility") or {}).get("values", [None] * n)[w]
            if agi:
                pw.append(_r("MAIN PART", "Agility: change-of-direction drills (5-10-5, T-drill)" + (" - FOCUS" if "agility" in weak else ""),
                             "", str(_split(agi, 2, 0)), "1", "Cones", "30 s"))
            cond = [_r("MAIN PART", label + (" - FOCUS (endurance)" if "endurance" in weak else ""), "", str(ld["runs"][m][w]), "1", "Group", "1:3 work:rest")
                    for m, label in ((150, "Interval run 150 m"), (300, "Interval run 300 m")) if ld["runs"][m][w]]
            tac = [_r("MAIN PART", "Field placings, match scenarios and plans", "20 min", "", "", "Squad")] \
                if any(on("Tactical", t, w) for t in ("Basic", "Offensive", "Defensive")) else []
            rows = warm_up() + stretch() + note(SLOW_NOTE) + program(name, lst, focus_sets=2 if "upper_strength" in weak else 0) \
                + note("MACRO REST 3 MIN") + block("MAIN PART", "Power and agility", 20, pw) + block("MAIN PART", "Conditioning", 25, cond) \
                + block("MAIN PART", "Tactics", 20, tac) + block("MAIN PART", "Role skills with the trainer", 30, stations[:4]) + warm_down()
            kind, title, topic = "trainer", f"{DAY_NAME[wd]} {day:%d %b %Y} - WITH THE TRAINER: upper body, power and conditioning", "Upper body, power and conditioning"
            unit = TRAINING_UNIT[k]
        else:                                                    # Monday, Thursday, Friday at school: practice + homework
            core = (focus.get("core") or {}).get("values", [None] * n)[w]
            upper = (focus.get("upper_strength") or {}).get("values", [None] * n)[w]
            agi = (focus.get("agility") or {}).get("values", [None] * n)[w]
            school = block("MAIN PART", "School practice", 60, [_r("MAIN PART", "Nets and fielding with the school coach", "60min", "", "", "School team")])
            if wd == 0:                                          # Monday: school practice + the Crunches block
                extra = [_r("MAIN PART", f"Extra core work ({_split(core, 2, 0)} min) - FOCUS", f"{_split(core, 2, 0)}min", "", "", "Individual", "30 s")] \
                    if core and "core" in weak else []
                rows = warm_up() + stretch() + school + [_r("MAIN PART", "Crunches", head=True)] + _ex(CRUNCHES) + extra + warm_down(ice=False)
                topic = "School practice and core"
            elif wd == 3:                                        # Thursday: school practice + upper-body homework + quick feet
                hw = [_r("MAIN PART", "Homework - upper body (body weight)", head=True)] + _ex(HOMEWORK_UPPER, first_rest="MICRO REST - 30 SEC")
                if upper and "upper_strength" in weak:
                    hw.append(_r("MAIN PART", f"Extra upper-body sets - FOCUS", "", "8-12", str(_split(upper, 2, 1)), "Individual", "60 s"))
                if agi:
                    hw.append(_r("MAIN PART", "Quick feet and ladder drills" + (" - FOCUS" if "agility" in weak else ""), "", str(_split(agi, 2, 1)), "1", "Individual", "30 s"))
                if core and "core" in weak:
                    hw.append(_r("MAIN PART", f"Extra core work ({_split(core, 2, 1)} min) - FOCUS", f"{_split(core, 2, 1)}min", "", "", "Individual", "30 s"))
                rows = warm_up() + stretch() + school + hw + warm_down(ice=False)
                topic = "School practice and upper-body homework"
            else:                                                # Friday: school practice + flexibility and mobility
                rows = warm_up() + stretch() + school + [_r("MAIN PART", "Flexibility and mobility", head=True)] + _ex(MOBILITY) + warm_down(ice=False)
                topic = "School practice and flexibility"
            kind, title = "school", f"{DAY_NAME[wd]} {day:%d %b %Y} - SCHOOL PRACTICE ({topic.split(' and ', 1)[1]})"
            unit = "Body weight and bands (homework); school practice as planned by the school coach"
        if "flexibility" in weak and kind in ("trainer", "school"):   # sit and reach short of the toes: daily hamstring / lower-back work
            at = next((i for i, r in enumerate(rows) if r["part"] == "FINAL PART"), len(rows))
            rows = rows[:at] + block("MAIN PART", "Flexibility - FOCUS", 10, FLEX_FOCUS) + rows[at:]
        minutes = sum(int(r["time"].split()[0]) for r in rows if r.get("head") and r["time"])
        minutes += sum(15 for r in rows if r.get("head") and r["desc"] in {n for n, _ in LOWER.values()} | {n for n, _ in UPPER.values()}
                       | {"Crunches", "Homework - upper body (body weight)", "Flexibility and mobility"})
        minutes += 3 if any(r.get("head") and r["desc"] == "MACRO REST 3 MIN" for r in rows) else 0
        who = f"{player['name']} ({player['role']})" if player else "Squad"
        header = [f"{topic} · {who}", meta[0],
                  ("Focus areas: " + ", ".join(a["label"] for a in player["weak"])) if player and player.get("weak") else "Focus areas: as the squad plan",
                  f"Duration about {minutes} min · Tue/Wed with the trainer · Mon/Thu/Fri at school · no practice on public holidays"]
        return {"kind": kind, "title": title, "header": header, "rows": rows[:TABLE_LINES], "minutes": minutes, "unit": locals().get("unit")}

    monday = s0 - timedelta(days=s0.weekday())
    weeks = []
    while monday <= last:
        days = []
        for i in range(5):
            day = monday + timedelta(days=i)
            plan = day_plan(day)
            days.append({"date": day, "day": DAY_NAME[i], **plan})
        weeks.append({"label": week_label(monday), "monday": monday, "days": days})
        monday += timedelta(days=7)
    return {"weeks": weeks}


def practice_counts(g: dict, weeks: dict) -> list[tuple[int, int, int]]:
    """Per Annual-plan week: (trainer days, school days, no-practice days) - for the charts."""
    s0 = g["week_starts"][0]
    out = [[0, 0, 0] for _ in range(g["weeks"])]
    for wk in weeks["weeks"]:
        for d in wk["days"]:
            w = (d["date"] - s0).days // 7
            if not 0 <= w < g["weeks"] or d["kind"] == "outside":
                continue
            if d["kind"] == "holiday":
                out[w][2] += 1
            elif d["date"].weekday() in TRAINER:
                out[w][0] += 1
            else:
                out[w][1] += 1
    return [tuple(x) for x in out]
