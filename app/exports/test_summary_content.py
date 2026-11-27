"""What the squad test results summary says, worked out once for every format (PDF and Word).

summary_content() turns the Fitness page data (squad_test_results + the window's categorisation) into plain values and texts:
key numbers, key findings, the squad against the age-group reference, bands, the player overview, priorities, players to
watch, next steps and the method notes. The PDF and Word builders only lay these out, so both documents always agree.
Texts are plain (no markup); a finding or step is (bold lead, rest)."""
from __future__ import annotations

from datetime import date

from app.assessment.test_battery import AREA_LABEL, BY_KEY, display
from app.core.clock import today_lk

AGE_BAR = {"strong": "#3c8d40", "on_track": "#2f6db5", "developing": "#e0a526", "below": "#c94a4a"}
AGE_FILL = {"strong": "#cfe9cc", "on_track": "#dcebfa", "developing": "#fff0cc", "below": "#f8dcdc"}
AGE_TXT = {"strong": "Strong for age", "on_track": "On track", "developing": "Developing", "below": "Below reference"}
BAND_BAR = ["#c94a4a", "#e0a526", "#7fa7d9", "#2f6db5", "#3c8d40"]
BAND_FILL = ["#f8dcdc", "#fff0cc", "#e8f0fa", "#dcebfa", "#cfe9cc"]
SR_BAR = {"strong": "#3c8d40", "ok": "#2f6db5", "short": "#e0a526"}
COPIED_BAR = "#9aa7b8"
AREA_WORK = {
    "endurance": "aerobic intervals twice a week (e.g. 4-6 x 3 min hard, 2 min easy) plus one longer steady run",
    "power": "jumps, bounds and medicine-ball throws 2-3 times a week: low volume, full recovery, best quality",
    "upper_strength": "push-up and inverted-row progressions three times a week (tempo, then volume, then load)",
    "speed": "short sprints of 10-20 m with full recovery twice a week, plus acceleration technique",
    "agility": "change-of-direction and reaction drills twice a week, with deceleration technique first",
    "core": "plank, side-plank and anti-rotation circuits 3-4 times a week, adding time before difficulty",
}
FLEX_WORK = "daily hamstring and lower-back work (seated hamstring reach, band hamstring stretch, cat-camel, hip flexor stretch)"


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def f1(v) -> str:
    return "-" if v is None else f"{v:.1f}"


def sr(v) -> str:
    return "-" if v is None else f"{v:+.1f}"


def show(key: str, v) -> str:
    t = BY_KEY[key]
    return "-" if v is None else display(t, round(v) if t.kind != "decimal" else v)


def short(name: str) -> str:
    p = name.split()
    return f"{p[0]} {p[-1][0]}." if len(p) > 1 else name


def names(xs) -> str:
    """Short names in a sentence, never ending in '..'."""
    return ", ".join(short(n) for n in xs).rstrip(".")


def sr_colour(r: dict) -> str:
    v = r["sit_reach"]
    return COPIED_BAR if r.get("sit_reach_copied") else SR_BAR["strong"] if v >= 10 else SR_BAR["ok"] if v >= 0 else SR_BAR["short"]


def _when(dates: list) -> str:
    if not dates:
        return "Not tested yet"
    a = date.fromisoformat(str(dates[0]))
    if len(dates) == 1:
        return f"Tested {a:%d %b %Y}"
    return f"Tested {a:%d %b %Y} to {date.fromisoformat(str(dates[-1])):%d %b %Y}"


def summary_content(d: dict, cats: dict, *, band_names=None, next_label: str | None = None, prepared: date | None = None) -> dict:
    """d: squad_test_results(...) for one window; cats: {player_id: categorisation} for the same window."""
    ag = d.get("ref_label") or d["age_group"]
    tests = {t["key"]: t for t in d["tests"]}
    tested = [r for r in d["players"] if r["level"]]
    used = [t for t in d["tests"] if any(r["values"].get(t["key"]) is not None for r in tested)]
    dates = sorted({r["test_date"] for r in tested if r["test_date"]})
    levels = sorted({r["level_label"] for r in tested if r["level_label"]})
    when = _when(dates)
    c = {"ag": ag, "tests": tests, "tested": tested, "used": used, "levels": levels, "when": when,
         "prepared": prepared or today_lk(), "band_names": list(band_names or [f"Band {i}" for i in range(1, 6)]),
         "title": f"Test results summary - {d['squad']} - {d['season']['name']} - {d['window_label']}",
         "sub": f"{d['season']['name']}  ·  {d['window_label']}  ·  {when}"}
    c["meta"] = (f"{d['squad']}  ·  {ag}  ·  {d['season']['name']}  ·  {d['window_label']}  ·  {when}"
                 + (f"  ·  {', '.join(levels)}" if levels else "") + f"  ·  Prepared {c['prepared']:%d %b %Y}")
    c["empty"] = (f"No {d['window_label'].lower()} results have been recorded for this squad yet. Import the test template on the "
                  "Tests page or enter results on the Fitness page, then download this summary again.")
    if not tested:
        return c

    # squad against the reference, test by test
    vs = []
    for t in used:
        k = t["key"]
        have = [r for r in tested if r["age"].get(k)]
        ok = [r for r in have if r["age"][k] in ("on_track", "strong")]
        vals = [r["values"][k] for r in tested if r["values"].get(k) is not None]
        ranked = sorted((r for r in tested if r["values"].get(k) is not None), key=lambda r: r["values"][k], reverse=t["higher_is_better"])
        vs.append({"t": t, "have": have, "ok": ok, "pct": round(100 * len(ok) / len(have)) if have else None, "avg": mean(vals),
                   "n": len(vals), "best": ranked[0] if ranked else None, "ranked": ranked,
                   "weak": [r for r in have if r["age"][k] in ("below", "developing")]})
    age_vals = [b for r in tested for b in r["age"].values() if b]
    meets = sum(1 for b in age_vals if b in ("on_track", "strong"))
    pct_all = round(100 * meets / len(age_vals)) if age_vals else None
    pts = [(r, cats[r["player_id"]]["benchmark"]) for r in tested if cats.get(r["player_id"]) and cats[r["player_id"]].get("benchmark")]
    srs = [r for r in tested if r["sit_reach"] is not None]
    sr_avg = mean([r["sit_reach"] for r in srs])
    sr_short = [r for r in srs if r["sit_reach"] < 0]
    sf_avg = mean([r["skinfold_sum"] for r in tested])
    c.update(vs=vs, age_vals=age_vals, meets=meets, pct_all=pct_all, pts=pts, srs=srs, sr_avg=sr_avg, sr_short=sr_short, sf_avg=sf_avg,
             sr_strong=[r for r in srs if r["sit_reach"] >= 10], sr_copied=[r["name"] for r in srs if r.get("sit_reach_copied")],
             sr_missing=[r["name"] for r in d["players"] if r["sit_reach"] is None],
             skinfolds=sorted((r for r in tested if r["skinfold_sum"] is not None), key=lambda r: r["skinfold_sum"]))

    # key numbers
    c["tiles"] = [
        ("Players tested", f"{len(tested)} / {len(d['players'])}", f"{len(used)} tests · best of 3 trials"),
        (f"At or above {ag} expected", "-" if pct_all is None else f"{pct_all}%", f"{meets} of {len(age_vals)} results"),
        (f"Average {ag} points", f1(mean([b["total"] for _, b in pts])) if pts else "-",
         f"out of {pts[0][1]['max']} · SLC benchmark" if pts else
         "no SLC benchmark for this age group" if d.get("gender") != "female" and d["age_group"] != "U15" else "Super Provincial players only"),
        ("Sit and reach", f"{sr(sr_avg)} cm" if sr_avg is not None else "-",
         f"{len(sr_short)} of {len(srs)} short of the toes" if srs else "not tested"),
        ("Squad body size", f"{f1(mean([r['height_cm'] for r in tested]))} cm",
         f"{f1(mean([r['weight_kg'] for r in tested]))} kg · skinfolds {f1(sf_avg)} mm"),
    ]

    # key findings
    ranked = [v for v in vs if v["pct"] is not None]
    findings = []
    if ranked:
        top = max(ranked, key=lambda v: v["pct"])
        low = min(ranked, key=lambda v: v["pct"])
        findings.append((f"Strongest test: {top['t']['label']}",
                         f". {len(top['ok'])} of {len(top['have'])} players ({top['pct']}%) are at or above the {ag} expected value; squad "
                         f"average {show(top['t']['key'], top['avg'])} {top['t']['unit']} against {top['t']['reference']['expected_display']} expected."))
        if low is not top:
            findings.append((f"Biggest gap: {low['t']['label']}",
                             f". Only {len(low['ok'])} of {len(low['have'])} players ({low['pct']}%) reach the {ag} expected value; squad average "
                             f"{show(low['t']['key'], low['avg'])} {low['t']['unit']} against {low['t']['reference']['expected_display']} expected."))
    if pct_all is not None:
        findings.append(("Overall", f": {pct_all}% of all results ({meets} of {len(age_vals)}) are at or above the {ag} expected value"
                         + (" - a solid base for the season." if pct_all >= 60 else " - room to improve before the next test." if pct_all >= 40
                            else " - physical development is a clear priority.")))
    if pts:
        best3 = sorted(pts, key=lambda x: -x[1]["total"])[:3]
        findings.append(("Top overall", " (SLC benchmark points): " + ", ".join(f"{r['name']} ({b['total']})" for r, b in best3) + "."))
    ch = [x.get("state") for r in tested if r.get("change") for x in r["change"]["tests"].values()]
    if ch:
        findings.append(("Since the previous test", f": {ch.count('improved')} results improved and {ch.count('worse')} got worse "
                         f"({sum(1 for r in tested if r.get('change'))} players with an earlier test)."))
    if srs:
        findings.append(("Flexibility", f": {len(srs) - len(sr_short)} of {len(srs)} players reach their toes in the sit and reach (squad "
                         f"average {sr(sr_avg)} cm)" + (f"; {len(sr_short)} are short of the toes and get a daily flexibility block."
                                                        if sr_short else ".")))
    gaps = [r["name"] for r in d["players"] if not r["level"]]
    if gaps:
        findings.append(("Not tested in this window", ": " + ", ".join(gaps) + "."))
    c["findings"], c["gaps"] = findings, gaps

    # bands
    c["band_counts"] = [sum(1 for r in tested if (cats.get(r["player_id"]) or {}).get("band") == b) for b in range(1, 6)]

    # player overview, sorted by points
    order = sorted(d["players"], key=lambda r: (not r["level"], -((cats.get(r["player_id"]) or {}).get("benchmark") or {}).get("total", -1), r["name"]))
    overview = []
    for i, r in enumerate(order, 1):
        cat = cats.get(r["player_id"]) or {}
        bm = cat.get("benchmark")
        bands = list(r["age"].values())
        focus = [f["label"] for f in cat.get("focus_areas", [])]
        if r["sit_reach"] is not None and r["sit_reach"] < 0:
            focus.append("Flexibility")
        overview.append({"rank": str(i) if r["level"] else "-", "r": r, "name": r["name"] + (" (stand-by)" if r["standby"] else ""),
                         "role": r["role"].replace("_", " ").title(), "level": r["level_label"] or "Not tested",
                         "points": f"{bm['total']} / {bm['max']}" if bm else "-", "band": cat.get("band"),
                         "band_text": f"{cat['band']} {cat['band_label']}" if cat.get("band") else "-",
                         "good": str(sum(1 for b in bands if b in ("on_track", "strong"))) if r["level"] else "-",
                         "weak": str(sum(1 for b in bands if b in ("developing", "below"))) if r["level"] else "-",
                         "sit_reach": f"{sr(r['sit_reach'])} cm" + (" *" if r.get("sit_reach_copied") else "") if r["sit_reach"] is not None else "-",
                         "sit_reach_fill": None if r["sit_reach"] is None else AGE_FILL["developing"] if r["sit_reach"] < 0
                         else AGE_FILL["strong"] if r["sit_reach"] >= 10 else AGE_FILL["on_track"],
                         "focus": ", ".join(focus) or "-"})
    c["order"], c["overview"] = order, overview

    # priorities: tests where fewer than half reach the expected value, weakest first
    pri = []
    for v in sorted((v for v in vs if v["pct"] is not None and v["pct"] < 50), key=lambda v: v["pct"]):
        t = v["t"]
        area = BY_KEY[t["key"]].area
        pri.append({"label": t["label"], "share": f"{v['pct']}% ({len(v['ok'])}/{len(v['have'])})",
                    "work": f"{AREA_LABEL.get(area, '')}: {AREA_WORK.get(area, 'targeted work in the plan')}",
                    "players": ", ".join(short(r["name"]) for r in sorted(v["weak"], key=lambda r: r["values"][t["key"]],
                                                                          reverse=not t["higher_is_better"]))})
    c["priorities"] = pri
    c["flex_note"] = (f"Flexibility: {len(sr_short)} players are short of the toes - {FLEX_WORK}." if sr_short else None)

    attention = []
    for r in tested:
        below = [tests[k]["label"] for k, b in r["age"].items() if b == "below" and k in tests]
        if len(below) >= 2:
            attention.append({"name": r["name"], "below": ", ".join(below),
                              "focus": ", ".join(f["label"] for f in (cats.get(r["player_id"]) or {}).get("focus_areas", [])) or "-",
                              "n": len(below)})
    c["attention"] = sorted(attention, key=lambda x: -x["n"])

    # next steps
    steps = [("Next test", f": {next_label or 'the next test window'} - repeat the same tests in the same order, at the same time of day, "
                           "on the same surface, after the same warm-up.")]
    if gaps:
        steps.append(("Test the missing players", ": " + ", ".join(gaps) + "."))
    for lead, xs in (("Sit and reach still to record", [r["name"] for r in tested if r["sit_reach"] is None]),
                     ("Measure skinfolds", [r["name"] for r in tested if r["copied"]]),
                     ("Measure sit and reach", [r["name"] for r in tested if r.get("sit_reach_copied")]),
                     ("Third trial needed", [r["name"] for r in tested if r.get("third_needed")])):
        if xs:
            extra = {"Measure skinfolds": " (copied, not measured this time)", "Measure sit and reach": " (copied, not measured this time)",
                     "Third trial needed": " (first two trials too far apart)"}.get(lead, "")
            steps.append((lead, f"{extra}: {names(xs)}."))
    steps.append(("Personal plans", ": each player's annual plan and week plans (Plans page, PDF or Excel) are built from their own "
                                    "results above, with their focus areas and next-test targets."))
    c["steps"] = steps

    notes = [f"Tests follow the SLC {ag} SOP. Each result is the best of 3 trials (fastest time for timed tests); times are written as mm.ss.",
             f"Reference values: {ag} youth norms - published where available, otherwise SLC estimates. Developing / expected / strong "
             "thresholds are per test; 'at or above expected' counts On track and Strong for age.",
             "SLC benchmark points and bands are calculated inside each level group, so a player is compared with players at the same level.",
             "Sit and reach: cm from the toes (0 = toes; + past them, - short of them). Recorded and used for the flexibility focus, not ranked.",
             "Skinfolds: ISAK 8 sites, right side, mm; two measures per site and a third when they differ by more than 5%. Only the sum "
             "of 8 is reported: no % body-fat equation is used for growing players.",
             "* = not measured: the result of the comparison player the coach chose. Replace it with a real measurement at the next test.",
             "This summary uses the data on the Fitness page at the time of download. Correct any result there and download again."]
    if d.get("gender") == "female":
        notes.insert(2, f"Women's and girls' squads: the {ag} references and the women's benchmark points are PROVISIONAL. Few published "
                        "female values exist for these tests (broad jump, push-ups and plank are from girls' youth data; the others are "
                        "estimated from the boys' values and the usual sex difference). Replace them with SLC's own women's data.")
    c["notes"] = notes

    # full results matrix and past tests
    c["matrix"] = [r for r in order if r["level"]]
    c["history"] = d.get("history") or []
    return c
