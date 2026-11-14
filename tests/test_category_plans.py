"""Separate plans per development category, built from the individual plan (which stays the main plan)."""
import io

import openpyxl
import pytest

from app.category_plans import CATEGORIES, HEAVY_LEGS, INJURY_KINDS, MAX_MAIN, build_category_plans
from .test_personal_plan import plan as make_plan
from .test_plan_versions import setup  # noqa: F401  (fixture)

PDP = {"Physical": ["Speed", "Endurance", "Functional Strength", "Agility", "Recovery practices"],
       "Nutrition": ["Skinfolds", "Hydration", "Diet habits", "Recovery nutrition", "Alcohol intake"],
       "Pace Bowl": ["Repeatable action", "Ball Speed", "Control", "Variations", "New Ball Old Ball"],
       "Spin Bowl": ["Repeatable action", "Sideway Spin", "Control", "Variations", "New Ball Old Ball"],
       "Field": ["Throwing", "Outfield catching", "Close catching", "Run saving ability", "Anticipation"],
       "Wk": ["Clean takes", "Up to stumps", "Back from stumps", "Agility Left / Right", "Fielding leader"]}


def cats(role="fast_bowler", bowling_types=None, **kw):
    p = make_plan(role=role, pcts=kw.pop("pcts", {"plank": 10.0, "shuttle_5_10_5": 20.0, "pushups": 70.0}), **kw)
    return p, build_category_plans(p, PDP, role, bowling_types)


def cat(out, key):
    return next(c for c in out["categories"] if c["key"] == key)


def test_all_ten_categories_and_role_first():
    _, out = cats("fast_bowler")
    assert [c["group"] for c in out["categories"]][0] == "Physical" and len(out["categories"]) == len(CATEGORIES) == 10
    rel = {c["group"]: c["relevant"] for c in out["categories"]}
    assert rel["Pace Bowl"] and rel["Tactical - Bowling"] and not rel["Spin Bowl"] and not rel["Wk"]
    assert [c["relevant"] for c in out["categories"]] == sorted([c["relevant"] for c in out["categories"]], reverse=True)   # role first
    _, keeper = cats("bat_wicketkeeper")
    assert cat(keeper, "wk")["relevant"] and not cat(keeper, "pace_bowl")["relevant"]
    _, ar = cats("all_rounder", {"spin"})
    assert cat(ar, "spin_bowl")["relevant"] and not cat(ar, "pace_bowl")["relevant"]


def test_sc_sessions_cover_every_exercise_once_and_never_exceed_the_cap():
    p, out = cats()
    sc = cat(out, "physical")
    for main_ph, ph in zip(p["phases"], sc["phases"]):
        planned = sorted(e["name"] for a in main_ph["areas"] for e in a["exercises"])
        got = sorted(i["name"] for s in ph["sessions"] for part in s["parts"] if part["part"] in ("Main work", "Injury prevention") for i in part["items"])
        assert got == planned, ph["phase"]                                       # same exercises as the main plan, each once
        for s in ph["sessions"]:
            main = next(x for x in s["parts"] if x["part"] == "Main work")["items"]
            inj = next(x for x in s["parts"] if x["part"] == "Injury prevention")["items"]
            assert len(main) <= MAX_MAIN and all(i["kind"] not in INJURY_KINDS for i in main) and all(i["kind"] in INJURY_KINDS for i in inj)
            assert s["parts"][0]["part"] == "Warm-up" and s["parts"][-1]["part"] == "Cool-down"
            assert all("set" in i and "rep" in i for i in main)                  # each exercise keeps its personal dose


def test_versions_rotate_week_by_week():
    _, out = cats()
    sc = cat(out, "physical")
    ph = next(x for x in sc["phases"] if x["sessions"] and x["sessions"][0]["versions"] > 1)
    names = [w["sessions"] for w in sc["weeks"] if w["phase"] == ph["phase"]]
    assert names[0] != names[1] and names[0] == names[ph["sessions"][0]["versions"]]


def test_fast_bowler_day_after_bowling_session_has_no_heavy_leg_work():
    _, out = cats("fast_bowler")
    restricted = [s for ph in cat(out, "physical")["phases"] for s in ph["sessions"] if s["note"]]
    assert restricted                                                             # pre-season puts a session after a bowling day
    for s in restricted:
        assert not any(i["kind"] in HEAVY_LEGS for part in s["parts"] for i in part["items"] if "kind" in i)


def test_hold_has_no_sessions():
    _, out = cats(ready={"status": "hold", "label": "Hold", "reason": "x"})
    sc = cat(out, "physical")
    assert all(not ph["sessions"] for ph in sc["phases"]) and all(w["dose_step"].startswith("On hold") for w in sc["weeks"])


def test_ratings_goals_and_drills_per_category():
    pdp = {("Physical", "Speed"): 2, ("Pace Bowl", "Control"): 1, ("Nutrition", "Hydration"): 2, ("Field", "Throwing"): 5}
    _, out = cats("fast_bowler", extra={"pdp": pdp})
    assert next(x for x in cat(out, "physical")["pdp"] if x["skill"] == "Speed")["rating"] == 2
    pb = cat(out, "pace_bowl")
    assert pb["skills"][0] == {"skill": "Control", "rating": 1, "status": "priority"} and pb["priorities"] == 1
    assert any("Control" in g["label"] for g in pb["goals"])
    pre = next(ph for ph in pb["phases"] if ph["phase"] == "pre_season")
    ctl = next(i for i in pre["items"] if i["skill"] == "Control")
    assert ctl["drills"] and all(d["name"] for d in ctl["drills"])
    nu = cat(out, "nutrition")
    assert next(i for i in nu["phases"][0]["items"] if i["skill"] == "Hydration")["action"]
    assert any(g["kind"] == "habit" for g in nu["goals"])
    assert next(x for x in cat(out, "field")["skills"] if x["skill"] == "Throwing")["status"] == "strength"
    assert "No coach ratings yet" in cat(out, "wk")["notes"][0]


# ───────────── API ─────────────
def test_endpoint_follows_the_saved_plan_and_exports_sc(client, world, setup):  # noqa: F811
    pid, sid = setup
    h = world["h"]["coach_a"]
    gen = client.get(f"/players/{pid}/individual-plan?season_id={sid}&window=baseline", headers=h).json()
    ph = gen["phases"][0]
    a = next(x for x in ph["areas"] if x["exercises"] and x["alternatives"])
    swap = {"type": "swap", "phase": ph["phase"], "area": a["area"], "index": 0, "exercise": a["alternatives"][0]["name"]}
    assert client.post(f"/players/{pid}/individual-plan/versions", headers=h,
                       json={"base": "fresh", "edits": [swap], "season_id": sid, "window": "baseline"}).status_code == 201
    r = client.get(f"/players/{pid}/category-plans?season_id={sid}&window=baseline", headers=h)
    assert r.status_code == 200
    sc = cat(r.json(), "physical")
    names = {i["name"] for p in sc["phases"] for s in p["sessions"] for part in s["parts"] for i in part["items"]}
    assert swap["exercise"] in names                                             # the coach's edit is in the S&C plan
    assert client.get(f"/players/{pid}/individual-plan?season_id={sid}", headers=h).json()["phases"]   # the main plan is still there
    x = client.get(f"/players/{pid}/sc-plan.xlsx?season_id={sid}&window=baseline", headers=world["h"]["admin"])
    assert x.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["S&C summary", "Sessions", "Week by week"]
    assert swap["exercise"] in [c.value for row in wb["Sessions"].iter_rows() for c in row]
    assert client.get(f"/players/{pid}/category-plans?season_id={sid}", headers=world["h"]["coach_b"]).status_code in (403, 404)
    assert client.get(f"/players/{pid}/category-plans?season_id={sid}").status_code == 401
