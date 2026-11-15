"""The squad's Physical page: dashboard, S&C groups, re-test and progress, growth."""
from datetime import date

from app import physical_hub as ph
from app.exercise_kinds import PHASE_KINDS
from .test_testing import add_players, fill, get_template, good_row, make_season, upload

H = lambda w, who: w["h"][who]


def cat(pid, pcts):
    areas = [{"area": a, "label": a, "percentile": v} for a, v in pcts.items()]
    focus = sorted(({"area": a, "label": a, "percentile": v} for a, v in pcts.items() if v is not None and v < 50), key=lambda x: x["percentile"])
    return {"areas": areas, "band": 3, "band_label": "Competent", "overall": 50.0, "focus_areas": focus}


PL = [{"id": i, "name": f"P{i}", "role": "fast_bowler" if i < 2 else "batter", "squad_no": i} for i in range(9)]
CATS = {0: cat(0, {"endurance": 20, "core": 30, "speed": 80}), 1: cat(1, {"endurance": 25, "core": 60, "speed": 40}),
        2: cat(2, {"endurance": 10, "core": 70, "speed": 60}), 3: cat(3, {"endurance": 70, "core": 20, "speed": 60}),
        4: cat(4, {"endurance": 60, "core": 15, "speed": 70}), 5: cat(5, {"endurance": 80, "core": 35, "speed": 75}),
        6: cat(6, {"endurance": 60, "core": 60, "speed": 30}), 7: cat(7, {"endurance": 90, "core": 90, "speed": 90})}


def test_heatmap_counts_and_untested():
    d = ph.heatmap(PL, CATS)
    assert d["tested"] == 8 and d["squad_size"] == 9 and d["untested"] == ["P8"]
    end = next(s for s in d["summary"] if s["area"] == "endurance")
    assert end["priority"] == 3 and end["strength"] == 3 and end["weakest_first"] == 3
    assert [p["name"] for p in d["pace"]] == ["P0", "P1"] and d["pace"][0]["watch"] == ["Endurance", "Core"]


def test_groups_by_weakest_area_and_everyone_once():
    rows = ph.heatmap(PL, CATS)["rows"]
    gs = ph.make_groups(rows)
    names = [p["name"] for g in gs for p in g["players"]]
    assert sorted(names) == sorted(r["name"] for r in rows) and len(names) == len(set(names))       # every tested player exactly once
    by = {g["area"]: [p["name"] for p in g["players"]] for g in gs}
    assert set(by["endurance"]) == {"P0", "P1", "P2"} and set(by["core"]) == {"P3", "P4", "P5"}
    assert "P6" in by[None] and "P7" in by[None]                     # speed has too few players: maintenance group


def test_group_session_follows_the_phase_and_has_no_duplicates():
    rows = ph.heatmap(PL, CATS)["rows"]
    g = next(x for x in ph.make_groups(rows) if x["area"] == "endurance")
    for phase in ("pre_season", "in_season", "transition"):
        s = ph.group_session(g, phase, ["fast", "fielding"])
        items = [i for p in s["parts"] if p["part"] in ("Main work", "Landing and injury prevention") for i in p["items"]]
        assert all(i["kind"] in PHASE_KINDS[phase] for i in items), phase
        assert len({ph._stem(i["name"]) for i in items}) == len(items)
        assert len(next(p for p in s["parts"] if p["part"] == "Main work")["items"]) <= ph.GROUP_MAIN


def test_retest_suggestions():
    long = {"start_date": date(2027, 1, 1), "end_date": date(2027, 9, 30)}
    phases = [{"phase_type": "in_season", "start_date": date(2027, 4, 1), "end_date": date(2027, 8, 31)}]
    r = ph.retest_plan(long, phases, ["baseline"], [], date(2027, 2, 1))
    assert r["next_window"] == "mid_season" and date(2027, 6, 1) <= r["suggested_date"] <= date(2027, 6, 30)
    short = {"start_date": date(2026, 11, 26), "end_date": date(2026, 12, 5)}
    r = ph.retest_plan(short, [], ["baseline"], [date(2026, 12, 12)], date(2026, 11, 15))
    assert r["next_window"] == "end_season" and r["suggested_date"] == date(2026, 12, 12) and r["scheduled"] == [date(2026, 12, 12)]
    assert ph.retest_plan(long, phases, ["baseline", "mid_season", "end_season"], [], date(2027, 2, 1))["next_window"] is None


def test_growth_rate_bmi_and_stage():
    g = ph.growth_rows([{"id": 1, "name": "A", "role": "fast_bowler", "maturity_status": "unknown"}],
                       {1: [{"date": date(2026, 1, 10), "height_cm": 150.0, "weight_kg": 40.0}, {"date": date(2026, 7, 10), "height_cm": 155.0, "weight_kg": 44.0}]})[0]
    assert g["velocity_cm_yr"] == round(5 / (181 / 365.25), 1) and g["in_spurt"] and g["bowling_window"]
    assert g["bmi"] == round(44 / 1.55 ** 2, 1) and len(g["measures"]) == 2
    assert ph.growth_rows([{"id": 2, "name": "B", "role": "batter", "maturity_status": "post_phv"}], {})[0]["stage"] == "post"


def test_physical_page_endpoint(client, world, db):
    ids = add_players(db, world)
    sid = make_season(client, world)
    upload(client, world, fill(get_template(client, world, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    r = client.get(f"/squads/{world['squad_a']}/seasons/{sid}/physical", headers=H(world, "sc_a"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["window"] == "baseline" and d["dashboard"]["tested"] == len(ids)
    assert sum(len(g["players"]) for g in d["groups"]) == len(ids) and all(g["session"] for g in d["groups"])
    assert d["retest"]["next_window"] == "mid_season" and not d["progress"]["any_compared"]
    assert {g["name"] for g in d["growth"]} >= {f"Test Player {i}" for i in range(len(ids))}
    assert next(g for g in d["growth"] if g["player_id"] == ids[1])["height_cm"] == 151.0
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/physical", headers=H(world, "coach_b")).status_code in (403, 404)
    assert client.get(f"/squads/{world['squad_a']}/seasons/{sid}/physical?window=x", headers=H(world, "admin")).status_code == 422
