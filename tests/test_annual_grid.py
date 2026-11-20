"""The week-by-week annual plan grid (layout of the supplied annual plan sheet): rules, consistency and Excel output."""
import io
from datetime import date, timedelta

import openpyxl
import pytest

from app.annual_grid import (COMP, GENERAL, LOADING, PEAK, PHASE_RULES, PRECOMP, ROW_KINDS, SEASON_PHASE_OF, SPECIAL, TRANS,
                             build_grid)
from app.exercise_kinds import PHASE_KINDS
from app.season_phases import suggest_phases

H = lambda w, who: w["h"][who]


def grid(start=date(2027, 1, 1), end=date(2027, 9, 30), events=(), phases=None, name="Western U15"):
    return build_grid(squad_name=name, season={"name": "2027", "start_date": start, "end_date": end},
                      phases=phases or suggest_phases(start, end), events=list(events), generated_on=date(2027, 1, 1))


# ───────────── shape ─────────────
def test_weeks_and_spans_cover_every_week_once():
    g = grid()
    n = g["weeks"]
    assert n == 39 and len(g["week_starts"]) == 39 and g["week_starts"][1] - g["week_starts"][0] == timedelta(days=7)
    for key in ("periods", "phases", "mesos", "macros"):
        spans = g[key]
        assert spans[0][0] == 0 and spans[-1][1] == n - 1, key
        assert all(b[0] == a[1] + 1 for a, b in zip(spans, spans[1:])), key          # contiguous, no gaps or overlaps
    for k in ("days", "percentage", "hours", "match_weeks", "test_weeks", "recovery_weeks", "kinds"):
        assert len(g[k]) == n
    for sec in g["sections"]:
        assert all(len(r["marks"]) == n for r in sec["rows"])
    assert all(len(v) == n for v in g["loading"].values())


def test_phases_follow_the_season_phases_in_order():
    g = grid()
    assert [v for _, _, v in g["phases"]] == [GENERAL, SPECIAL, PRECOMP, COMP, TRANS]
    assert [v for _, _, v in g["periods"]] == ["Preparation", "Competition", "Transition"]
    sp = suggest_phases(date(2027, 1, 1), date(2027, 9, 30))
    pre = next(p for p in sp if p["phase_type"] == "pre_season")
    pre_weeks = sum(1 for k in g["kinds"] if k in (GENERAL, SPECIAL))
    assert pre_weeks == (pre["end_date"] - pre["start_date"]).days // 7 + 1
    assert g["kinds"].count(GENERAL) >= 1 and g["kinds"].count(SPECIAL) >= 1


def test_week_dates_and_months():
    g = grid()
    assert g["days"][:5] == [1, 8, 15, 22, 29] and g["days"][5] == 5                 # 1 Jan, 8, 15, 22, 29, then 5 Feb
    assert g["mesos"][0][2] == "January" and g["mesos"][1][2] == "February"
    two_years = grid(date(2026, 9, 1), date(2027, 6, 30))
    labels = [m[2] for m in two_years["mesos"]]
    assert labels[0] == "September 2026" and "January 2027" in labels and "October" in labels


def test_macro_blocks_stay_inside_phases_and_are_never_one_week():
    g = grid()
    for a, b, num in g["macros"]:
        assert len({g["kinds"][w] for w in range(a, b + 1)}) == 1
    sizes = [b - a + 1 for a, b, _ in g["macros"]]
    phase_len = {k: sum(1 for x in g["kinds"] if x == k) for k in set(g["kinds"])}
    assert all(s >= 2 for s in sizes) or min(phase_len.values()) == 1


def test_short_and_phaseless_seasons():
    assert grid(end=date(2027, 1, 20))["weeks"] == 3                                # short season (tournament) works
    with pytest.raises(ValueError):
        build_grid(squad_name="x", season={"name": "s", "start_date": date(2027, 1, 1), "end_date": date(2027, 6, 1)}, phases=[], events=[], generated_on=date(2027, 1, 1))
    g = grid(end=date(2027, 1, 28))                                                  # exactly four weeks still works
    assert g["weeks"] == 4


def test_partial_phases_do_not_break():
    ph = [{"phase_type": "in_season", "start_date": date(2027, 1, 1), "end_date": date(2027, 3, 31), "focus": None}]
    g = grid(end=date(2027, 3, 31), phases=ph)
    assert set(g["kinds"]) == {COMP} and [v for _, _, v in g["periods"]] == ["Competition"]
    gap = [{"phase_type": "pre_season", "start_date": date(2027, 1, 15), "end_date": date(2027, 2, 28), "focus": None},
           {"phase_type": "in_season", "start_date": date(2027, 3, 15), "end_date": date(2027, 5, 31), "focus": None}]
    g = grid(end=date(2027, 5, 31), phases=gap)                                       # weeks before the first phase / in the gap are placed sensibly
    assert g["kinds"][0] in (GENERAL, SPECIAL) and len(g["kinds"]) == g["weeks"]


# ───────────── planned load ─────────────
def test_percentage_ramps_dips_and_stays_below_peak():
    g = grid()
    pct = g["percentage"]
    assert all(0 < p <= PEAK for p in pct)
    prep = [w for w, k in enumerate(g["kinds"]) if k in (GENERAL, SPECIAL)]
    assert pct[prep[0]] == 0.25 and max(pct[w] for w in prep) == PEAK
    for w in prep:
        if g["recovery_weeks"][w]:
            assert pct[w] < pct[w - 1]                                                # the last week of a block is lighter
    first_comp = g["kinds"].index(PRECOMP)
    assert pct[first_comp] < PEAK and pct[-1] < pct[first_comp]                       # load comes down for competition, lower again in transition


def test_loading_index_follows_phase():
    g = grid()
    for w, k in enumerate(g["kinds"]):
        assert (g["loading"]["Volume"][w], g["loading"]["Intensity"][w]) == LOADING[k]
        p = g["percentage"][w]                                                         # Load never contradicts the % row
        assert g["loading"]["Load"][w] == ("High" if p >= 0.75 else "Medium" if p >= 0.5 else "low")
    assert LOADING[GENERAL] == ("High", "low") and LOADING[SPECIAL] == ("High", "Medium") and LOADING[COMP] == ("low", "High")
    peak = g["percentage"].index(max(g["percentage"]))
    assert g["loading"]["Load"][peak] == "High"
    d = g["daily"]
    assert all(d["loading"]["Load"][i] == ("" if not p else "High" if p >= 0.75 else "Medium" if p >= 0.5 else "low")
               for i, p in enumerate(d["percentage"]))


def test_nutrition_marks_the_emphasis_not_every_week():
    g = grid()
    k, pct = g["kinds"], g["percentage"]
    carb, fat = row(g, "Nutrition", "Carbohydrate"), row(g, "Nutrition", "Fat")
    assert not all(carb) and all(carb[w] for w in range(g["weeks"]) if k[w] in (PRECOMP, COMP) or pct[w] >= 0.6)
    assert all(fat[w] == (k[w] in (GENERAL, TRANS, COMP)) for w in range(g["weeks"]))          # competition: on recovery days (daily grid)
    d = g["daily"]
    dfat = next(r for s in d["sections"] if s["name"] == "Nutrition" for r in s["rows"] if r["label"] == "Fat")["marks"]
    assert not any(dfat[i] for i, x in enumerate(d["day_kind_keys"]) if x in ("match", "before"))   # never on a match day or the day before
    assert row(g, "Nutrition", "Protein") == [s or k[w] == TRANS for w, s in enumerate(row(g, "Physical", "Strength"))]
    assert all(row(g, "Nutrition", "Vitamin")) and any("EMPHASISED" in x for x in g["notes"])


# ───────────── marks and calendar ─────────────
def row(g, sec, label):
    s = next(x for x in g["sections"] if x["name"] == sec)
    return next(r for r in s["rows"] if r["label"] == label)["marks"]


def test_marks_follow_phases():
    g = grid()
    k = g["kinds"]
    end = row(g, "Physical", "Endurance")
    assert all(end[w] for w in range(g["weeks"]) if k[w] in (GENERAL, SPECIAL, TRANS)) and not any(end[w] for w in range(g["weeks"]) if k[w] in (PRECOMP, COMP))
    assert not any(row(g, "Physical", "Speed")[w] for w in range(g["weeks"]) if k[w] in (GENERAL, SPECIAL, TRANS))
    assert not any(row(g, "Technical", "Explosive power")[w] for w in range(g["weeks"]) if k[w] in (GENERAL, SPECIAL, TRANS))
    assert not any(row(g, "Technical", "Anaerobic endurance")[w] for w in range(g["weeks"]) if k[w] != PRECOMP)
    assert all(row(g, "Nutrition", "Minerals")) and all(row(g, "Physical", "Flexibility"))
    st = row(g, "Physical", "Strength")
    assert not any(st[w] for w in range(g["weeks"]) if g["recovery_weeks"][w] and k[w] in (GENERAL, SPECIAL))
    goal = row(g, "Mental", "Goal setting")
    assert goal[0] and goal[-1]
    assert not row(g, "Mental", "Relaxation")[0] and not row(g, "Mental", "Focusing")[0]
    assert sum(row(g, "Technical", "Reaction speed")[w] for w in range(g["weeks"]) if k[w] == GENERAL) < g["kinds"].count(GENERAL)   # every second week


def test_no_mark_outside_the_allowed_kinds():
    """Every marked phase must allow at least one matching exercise kind in exercise_kinds.PHASE_KINDS."""
    for sec, rows in PHASE_RULES.items():
        for label, rules in rows:
            kinds = ROW_KINDS.get((sec, label))
            if not kinds:
                continue
            for phase in (GENERAL, SPECIAL, PRECOMP, COMP, TRANS):
                if rules.get(phase):
                    assert kinds & set(PHASE_KINDS[SEASON_PHASE_OF[phase]]), (sec, label, phase)
    for key in ROW_KINDS:
        assert key[1] in [r for r, _ in dict(PHASE_RULES)[key[0]]] or key[1] in [x[0] for x in PHASE_RULES[key[0]]]


def test_calendar_drives_competition_tests_and_hours():
    from datetime import datetime  # noqa
    ev = [{"event_type": "match", "date": date(2027, 4, 10), "hours": 6.0},
          {"event_type": "training", "date": date(2027, 4, 12), "hours": 1.5},
          {"event_type": "training", "date": date(2027, 4, 13), "hours": 1.5},
          {"event_type": "fitness_test", "date": date(2027, 2, 6), "hours": None},
          {"event_type": "match", "date": date(2028, 1, 1), "hours": 5.0},               # outside the season: ignored
          {"event_type": "training", "date": date(2027, 4, 9), "hours": None}]
    g = grid(events=ev)
    w = (date(2027, 4, 10) - date(2027, 1, 1)).days // 7
    assert g["match_weeks"][w] and g["match_weeks"].count(True) == 1
    assert g["hours"][w] == 9.0 and sum(h for h in g["hours"] if h) == 9.0
    assert g["tests_source"] == "calendar" and [i for i, t in enumerate(g["test_weeks"]) if t] == [(date(2027, 2, 6) - date(2027, 1, 1)).days // 7]


def test_suggested_tests_when_calendar_has_none():
    g = grid()
    idx = [i for i, t in enumerate(g["test_weeks"]) if t]
    assert g["tests_source"] == "suggested" and idx[0] == 0 and idx[-1] == g["weeks"] - 1 and len(idx) == 3
    assert any("SUGGESTED" in n for n in g["notes"])
    d = g["daily"]                                                     # the day-by-day sheet shows them too, one fresh day per test week
    days = [i for i, t in enumerate(d["test_weeks"]) if t]
    assert [d["week_of_day"][i] for i in days] == idx and all(d["day_kind_keys"][i] not in ("rest", "match", "before") for i in days)


# ───────────── API and Excel ─────────────
def season(client, w, who="admin", squad="squad_a", **kw):
    body = {"name": "2027", "start_date": "2027-01-01", "end_date": "2027-09-30", "phases": []}
    body.update(kw)
    r = client.post(f"/squads/{w[squad]}/seasons", json=body, headers=H(w, who))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def xlsx(client, w, sid, who="admin", squad="squad_a"):
    r = client.get(f"/squads/{w[squad]}/seasons/{sid}/annual-plan.xlsx", headers=H(w, who))
    return r, (openpyxl.load_workbook(io.BytesIO(r.content)) if r.status_code == 200 else None)


def test_workbook_layout_matches_the_supplied_sheet(client, world):
    sid = season(client, world)
    r, wb = xlsx(client, world, sid)
    assert r.status_code == 200 and "annual-plan-Western-U15-2027.xlsx" in r.headers["content-disposition"]
    assert wb.sheetnames == ["Annual plan"]
    ws = wb.active
    labels = {4: "Periods", 5: "Phases", 6: "Mesos", 7: "Macros", 8: "Micros", 9: "Dates", 10: "Percentage", 11: "week hours", 12: "Competition",
              14: "Test", 15: "Medical", 16: "Lab", 17: "Field", 19: "Physical", 20: "Endurance", 21: "Strength", 22: "Speed", 23: "Flexibility",
              24: "Coordination", 26: "Mental", 27: "Concentration", 28: "Relaxation", 29: "Goal setting", 30: "Focusing", 31: "Imagination",
              32: "Confidence", 34: "Technical", 35: "Basic", 36: "Advance", 37: "Competition", 38: "Explosive power", 39: "Reaction speed",
              40: "Anaerobic endurance", 42: "Tactical", 43: "Basic", 44: "Offensive", 45: "Defensive", 47: "Nutrition", 48: "Carbohydrate",
              49: "Fat", 50: "Protein", 51: "Vitamin", 52: "Minerals", 53: "Electrolytes", 56: "Loading index", 57: "Volume", 58: "Intensity",
              59: "Load", 60: "Performance index"}
    for row_no, text in labels.items():
        assert ws.cell(row=row_no, column=1).value == text, row_no
    # week by week, like the supplied sheet, for a whole year: 52 weeks end at BA (the 39-week season, then the rest of the year)
    assert ws["A2"].value.startswith("ANNUAL PLAN FOR WESTERN U15") and "A2:BA2" in {str(m) for m in ws.merged_cells.ranges}
    assert ws["A2"].value.endswith("01 JAN 2027 TO 30 DEC 2027")
    assert ws["B4"].value == "Preparation" and ws["B5"].value == "General preparation" and ws["B6"].value == "January"
    assert [ws.cell(row=8, column=c).value for c in (2, 3, 40, 53)] == [1, 2, 39, 52]
    assert [ws.cell(row=9, column=c).value for c in (2, 3, 4, 5, 6, 7)] == [1, 8, 15, 22, 29, 5]
    assert ws["B10"].value == 0.25 and ws["B10"].number_format == "0%"
    for r_ in (12, 14, 19, 26, 34, 42, 47):
        assert ws.cell(row=r_, column=3).fill.fgColor.rgb.endswith("002060"), r_
    assert ws["B57"].value == "High" and ws["B58"].value == "low" and ws["AN57"].value == "low"
    assert ws["B20"].value == "*" and ws["B15"].value == "*" and ws["B16"].value is None           # medical and field in test weeks; lab empty
    assert ws["B49"].value == "*" and ws["B48"].value is None              # week 1 (25%): fat for growth emphasised, extra carbohydrate not yet
    assert ws["B60"].value == "results"                                     # Performance index: results go in the test weeks
    assert any("proposal" in str(c.value).lower() for c in ws["A"])


def test_workbook_uses_calendar_and_phases(client, world):
    phases = [{"phase_type": "pre_season", "start_date": "2027-01-01", "end_date": "2027-03-31"},
              {"phase_type": "pre_competition", "start_date": "2027-04-01", "end_date": "2027-05-15"},
              {"phase_type": "in_season", "start_date": "2027-05-16", "end_date": "2027-08-15"},
              {"phase_type": "transition", "start_date": "2027-08-16", "end_date": "2027-09-30"}]
    sid = season(client, world, phases=phases)
    ev = f"/squads/{world['squad_a']}/events"
    for body in ({"event_type": "match", "title": "Final", "start_at": "2027-06-12T09:00:00+05:30", "end_at": "2027-06-12T16:00:00+05:30"},
                 {"event_type": "fitness_test", "title": "Mid tests", "start_at": "2027-07-03T09:00:00+05:30"}):
        assert client.post(ev, json=body, headers=H(world, "admin")).status_code in (200, 201)
    g = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan", headers=H(world, "admin")).json()
    w = (date(2027, 6, 12) - date(2027, 1, 1)).days // 7
    assert g["match_weeks"][w] and g["hours"][w] == 7.0 and g["tests_source"] == "calendar"
    assert g["kinds"][(date(2027, 4, 2) - date(2027, 1, 1)).days // 7] == "pre_competition"
    assert not any("SUGGESTED split" in n for n in g["notes"])
    _, wb = xlsx(client, world, sid)
    ws = wb.active
    assert ws.cell(row=12, column=w + 2).value == "*" and ws.cell(row=11, column=w + 2).value == 7.0   # one column per week
    t = (date(2027, 7, 3) - date(2027, 1, 1)).days // 7
    assert ws.cell(row=15, column=t + 2).value == "*"


def test_no_phases_uses_suggestion_and_says_so(client, world):
    sid = season(client, world)
    g = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan", headers=H(world, "coach_a")).json()
    assert any("SUGGESTED split" in n for n in g["notes"]) and g["weeks"] == 52 and g["year"]


def test_access_rules(client, world):
    sid = season(client, world)
    for who in ("admin", "coach_a", "sc_a", "physio_a"):
        assert xlsx(client, world, sid, who)[0].status_code == 200, who
    for who in ("coach_b", "ann_login"):
        assert xlsx(client, world, sid, who)[0].status_code in (403, 404), who
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan.xlsx").status_code == 401
    assert client.get(f"/squads/{world['squad_a']}/seasons/9999/annual-plan.xlsx", headers=H(world, "admin")).status_code == 404
    other = season(client, world, squad="squad_b")
    assert client.get(f"/squads/{world['squad_a']}/seasons/{other}/annual-plan.xlsx", headers=H(world, "admin")).status_code == 404   # season of another squad


def test_short_season_is_a_tournament_plan(client, world):
    """A season under 4 weeks (e.g. a 10-day tournament) gets a year plan: the tournament first, then the rest of the year;
    never a test week during the tournament (tests are at the start of each preparation block)."""
    sid = season(client, world, end_date="2027-01-10")
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan.xlsx", headers=H(world, "admin"))
    assert r.status_code == 200
    g = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan", headers=H(world, "admin")).json()
    assert g["weeks"] == 52 and g["kinds"][:2] == ["competition", "competition"] and g["kinds"][2] == "transition"
    assert g["test_weeks"][:2] == [False, False] and g["tests_source"] == "suggested" and sum(g["test_weeks"]) == 3


def test_short_season_phase_suggestion_is_one_competition_phase():
    sp = suggest_phases(date(2026, 11, 26), date(2026, 12, 5))
    assert [(p["phase_type"], p["start_date"], p["end_date"]) for p in sp] == [("in_season", date(2026, 11, 26), date(2026, 12, 5))]
    assert [p["phase_type"] for p in suggest_phases(date(2027, 1, 1), date(2027, 1, 28))] == ["pre_season", "pre_competition", "in_season", "transition"]
    with pytest.raises(ValueError):
        suggest_phases(date(2026, 12, 5), date(2026, 11, 26))


def test_one_week_tournament_grid():
    g = grid(date(2026, 11, 26), date(2026, 11, 30), phases=[{"phase_type": "in_season", "start_date": date(2026, 11, 26), "end_date": date(2026, 11, 30)}])
    assert g["weeks"] == 1 and g["kinds"] == ["competition"] and g["season_end"] == date(2026, 11, 30)


def test_text_is_never_a_formula(client, world, db):
    from app.models import Squad
    db.get(Squad, world["squad_a"]).name = "=HYPERLINK(\"http://x\")"
    db.commit()
    sid = season(client, world, name="@SUM(1)")
    _, wb = xlsx(client, world, sid)
    cell = wb.active["A2"]
    assert cell.data_type == "s" and cell.value.startswith("ANNUAL PLAN FOR =HYPERLINK")


def test_no_medical_text_in_grid(client, world, db):
    from app.models import PlayerMedical
    db.add(PlayerMedical(player_id=world["bob"], current_health={"note": "SECRET-LUMBAR-STRESS"}))
    db.commit()
    sid = season(client, world)
    r, wb = xlsx(client, world, sid)
    text = " ".join(str(c.value) for row in wb.active.iter_rows() for c in row if c.value is not None)
    assert "SECRET" not in text
    assert "SECRET" not in client.get(f"/squads/{world['squad_a']}/seasons/{sid}/annual-plan", headers=H(world, "coach_a")).text


def test_tournament_sheet_is_day_by_day():
    """A season under 4 weeks is drawn with one column per day; the days follow the match days in the calendar."""
    from app.annual_grid_excel import build_grid_workbook
    s, e = date(2026, 11, 26), date(2026, 12, 5)
    matches = [date(2026, 11, 27), date(2026, 11, 30), date(2026, 12, 3)]
    g = build_grid(squad_name="Galle U15", season={"name": "T", "start_date": s, "end_date": e}, phases=suggest_phases(s, e),
                   events=[{"event_type": "match", "date": d, "hours": 6} for d in matches], generated_on=s)
    assert g["weeks"] == 2                                            # the weekly grid stays for the plans built on it
    d = g["daily"]
    assert d["weeks"] == 10 and d["days"][0] == 26 and d["days"][-1] == 5 and not d["assumed_matches"]
    assert [i for i, m in enumerate(d["match_weeks"]) if m] == [1, 4, 7]
    assert d["percentage"][1] == 0.5 and d["percentage"][0] == 0.3               # match day vs day before (rule of 60%)
    strength = next(r for r in d["sections"][0]["rows"] if r["label"] == "Strength")["marks"]
    assert not strength[0] and not strength[1] and strength[2]                    # never before or on a match day; the day after
    assert d["hours"][1] == 6
    ws = openpyxl.load_workbook(io.BytesIO(build_grid_workbook(g))).active
    assert ws["B9"].value == "Thu 26" and ws["K9"].value == "Sat 5" and ws["A11"].value == "day hours"
    assert ws["C12"].value == "*" and ws["C13"].value == "Match"
    long = grid()
    assert long["weeks"] == 39 and long["daily"]["weeks"] == 273         # every season is drawn day by day too


# ───────────── the annual plan covers a whole year (52 weeks from the season's start) ─────────────
def year_grid(start, end, phases=None, events=()):
    return build_grid(squad_name="Galle U15", season={"name": "T", "start_date": start, "end_date": end},
                      phases=phases or suggest_phases(start, end), events=list(events), generated_on=start, year=True)


def test_tournament_year_runs_competition_transition_preparation_and_pre_competition():
    s, e = date(2026, 11, 26), date(2026, 12, 5)
    g = year_grid(s, e, phases=[{"phase_type": "in_season", "start_date": s, "end_date": e}])
    assert g["weeks"] == 52 and g["week_starts"][-1] == s + timedelta(days=7 * 51) and g["year"]
    assert [p for _, _, p in g["phases"]] == [COMP, TRANS, GENERAL, SPECIAL, PRECOMP]
    trans = [b - a + 1 for a, b, p in g["phases"] if p == TRANS][0]
    pre = [b - a + 1 for a, b, p in g["phases"] if p == PRECOMP][0]
    assert trans == 3 and pre == 4                                                 # 3 weeks active rest, 4 weeks run-in
    assert [i for i, m in enumerate(g["match_weeks"]) if m] == [0, 1]              # assumed tournament matches, said in the notes
    assert any("ASSUMED matches" in n for n in g["notes"]) and "TO 24 NOV 2027" in g["title"]
    first = {p: a for a, _, p in reversed(g["phases"])}
    assert {w for w, t in enumerate(g["test_weeks"]) if t} == {first[GENERAL], first[SPECIAL], first[PRECOMP]}
    assert max(g["percentage"]) == PEAK and not g["daily"]["short"] and g["daily"]["weeks"] == 364   # drawn week by week


def test_long_season_year_gets_its_own_second_preparation():
    g = year_grid(date(2027, 1, 1), date(2027, 9, 30))
    kinds = [p for _, _, p in g["phases"]]
    assert kinds[:2] == [GENERAL, SPECIAL] and kinds[-3:] == [GENERAL, SPECIAL, PRECOMP]   # each preparation is split on its own
    ramps = [g["percentage"][a] for a, _, p in g["phases"] if p == GENERAL]
    assert ramps == [0.25, 0.25]                                                   # each preparation ramps from the start
    assert g["notes"][0].startswith("The plan covers ONE YEAR")


def test_year_never_shortens_a_season_longer_than_a_year():
    g = year_grid(date(2027, 1, 1), date(2028, 2, 28))
    assert g["weeks"] == 61 and not any("transition (3 weeks" in n for n in g["notes"])
