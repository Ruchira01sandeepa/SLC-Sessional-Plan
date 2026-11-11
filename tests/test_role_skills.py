"""Role skill grids (entry screen API), batting / keeping drills, and how both reach the individual plan."""
from datetime import date, timedelta

import pytest

from app.models import SkillTemplate, TemplateKind, PlayerRole
from app.role_skills import drill_groups, match_drills
from app.workload_service import today_lk
from .test_personal_plan import plan as make_plan
from .test_testing import add_players, fill, get_template, good_row, make_season, upload


@pytest.mark.parametrize("role,group,skill,phase,expect", [
    ("batter", "Stroks front foot(New balls)", "Cover Drive", "pre_season", "Front-foot drive drill off throw-downs"),
    ("batter", "Technic & Triger", "Grip", "pre_season", "Shadow batting: grip, stance and trigger"),
    ("bat_wicketkeeper", "Keeping Skills", "Standing up", "pre_competition", "Standing-up drill to spin with stumping"),
    ("fast_bowler", "Control", "Good-length accuracy", "pre_season", "Good-length target zone drill"),
    ("fast_bowler", "Run-up", "Rhythm and acceleration", "pre_season", "Run-up rhythm drill"),
    ("spin_bowler", "Variations", "Arm ball", "pre_competition", "Arm-ball or slider drill"),
])
def test_role_skills_get_the_matching_drill(role, group, skill, phase, expect):
    names = [d["name"] for d in match_drills(group, skill, role, None, phase)]
    assert expect in names[:2], names


def test_drill_lists_follow_the_role():
    assert drill_groups("Keeping Skills", "Standing back", "bat_wicketkeeper", None) == ["keeping"]
    assert drill_groups("Batting Set-up", "Grip, stance and balance", "bat_wicketkeeper", None) == ["batting"]
    assert drill_groups("Bowling Action", "Front-foot contact", "all_rounder", {"fast"}) == ["fast"]
    assert drill_groups("Fielding", "Catching", "all_rounder", {"spin"}) == ["fielding"]
    assert all(d["added"] for d in match_drills("Keeping Skills", "Standing up", "bat_wicketkeeper", None, "pre_season"))


def test_batting_pdp_items_now_get_batting_drills():
    p = make_plan(role="batter", pcts={"plank": 10.0}, extra={"pdp": {("Batting to Spin", "Weight transfer front foot"): 2,
                                                                       ("Batting to Pace", "Weight transfer back foot"): 1}})
    pre = next(x for x in p["phases"] if x["phase"] == "pre_season")
    spin = next(s for s in pre["skills"] if s["group"] == "Batting to Spin")
    assert spin["drills"][0]["name"] == "Use-of-feet drill against spin" and spin["drills"][0]["added"] and not spin["note"]
    pace = next(s for s in pre["skills"] if s["group"] == "Batting to Pace")
    assert pace["drills"][0]["name"] == "Back-foot defence and punch drill"


def test_role_skill_statuses_shape_the_plan():
    rs = [{"group": "Control", "skill": "Good-length accuracy", "status": "have_to_improve"},
          {"group": "Run-up", "skill": "Rhythm and acceleration", "status": "improving"},
          {"group": "Release", "skill": "Release height", "status": "good"}]
    p = make_plan(pcts={"plank": 10.0}, extra={"role_skills": rs})
    pre = next(x for x in p["phases"] if x["phase"] == "pre_season")
    assert [r["skill"] for r in pre["role_skills"]] == ["Good-length accuracy", "Rhythm and acceleration"]       # priority first, then improving
    assert pre["role_skills"][0]["drills"][0]["name"] == "Good-length target zone drill"
    assert any(g["kind"] == "role_skill" and "Good-length accuracy" in g["label"] for g in p["goals"])
    assert any("Release height" in s["label"] for s in p["strengths"])
    assert any("Good-length accuracy" in s["label"] for s in p["priorities"])


# ───────────── API ─────────────
def test_role_skill_grid_api(client, world, db, seeded):
    w = world
    h = w["h"]["coach_a"]
    r = client.get(f"/players/{w['bob']}/role-skills", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "development" and {k["kind"] for k in j["kinds"]} >= {"development", "progress_task"}
    assert j["legend"]["have_to_improve"] == "Have to improve"
    item = j["groups"][0]["items"][0]
    day = (today_lk() - timedelta(days=3)).isoformat()
    put = client.put(f"/players/{w['bob']}/role-skills", headers=h, json={"period_start": day, "items": [
        {"template_id": item["id"], "status": "have_to_improve", "coach_note": "Late on the gather"}]})
    assert put.status_code == 200
    saved = next(i for g in put.json()["groups"] for i in g["items"] if i["id"] == item["id"])
    assert saved["status"] == "have_to_improve" and saved["coach_note"] == "Late on the gather" and put.json()["last_assessed"] == day
    other = db.query(SkillTemplate).filter(SkillTemplate.player_role == PlayerRole.batter).first()
    assert client.put(f"/players/{w['bob']}/role-skills", headers=h, json={"items": [{"template_id": other.id, "status": "good"}]}).status_code == 422
    assert client.put(f"/players/{w['bob']}/role-skills", headers=h, json={"period_start": (today_lk() + timedelta(days=2)).isoformat(),
                                                                          "items": [{"template_id": item["id"], "status": "good"}]}).status_code == 422
    assert client.put(f"/players/{w['bob']}/role-skills", headers=w["h"]["physio_a"], json={"items": []}).status_code == 403
    clear = client.put(f"/players/{w['bob']}/role-skills", headers=h, json={"period_start": day, "items": [{"template_id": item["id"], "status": None}]})
    assert next(i for g in clear.json()["groups"] for i in g["items"] if i["id"] == item["id"])["status"] is None
    pt = client.get(f"/players/{w['bob']}/role-skills?kind=progress_task", headers=h).json()
    assert pt["kind"] == "progress_task" and pt["groups"]


def test_role_skills_reach_the_players_plan(client, world, db, seeded):
    w = world
    ids = add_players(db, w)
    sid = make_season(client, w)
    upload(client, w, fill(get_template(client, w, sid).content, {pid: good_row(i) for i, pid in enumerate(ids)}), sid, confirm=True)
    pid = ids[0]                                                                    # a batter
    grid = client.get(f"/players/{pid}/role-skills", headers=w["h"]["coach_a"]).json()
    drive = next(i for g in grid["groups"] for i in g["items"] if "Drive" in i["skill"])
    client.put(f"/players/{pid}/role-skills", headers=w["h"]["coach_a"], json={"items": [{"template_id": drive["id"], "status": "have_to_improve"}]})
    j = client.get(f"/players/{pid}/individual-plan?season_id={sid}&window=baseline&fresh=true", headers=w["h"]["coach_a"]).json()
    assert any(g["kind"] == "role_skill" and drive["skill"] in g["label"] for g in j["goals"])
    pre = next(x for x in j["phases"] if x["phase"] == "pre_season")
    assert pre["role_skills"] and pre["role_skills"][0]["drills"][0]["name"] == "Front-foot drive drill off throw-downs"
