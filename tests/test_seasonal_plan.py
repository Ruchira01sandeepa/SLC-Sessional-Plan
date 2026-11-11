"""Admin-only mode, phase editing, role-specific measures, exercise library and the seasonal plan."""
import io
import json
from datetime import date

import openpyxl
import pytest

from app.config import settings
from app.exercise_kinds import PHASE_KINDS
from app.exercises import exercises_for, library
from app.models import UserRole
from app.role_kpis import ALL_KPIS, KPIS, validate_role_specific
from app.season_phases import suggest_phases
from .conftest import PW, login, make_user

H = lambda w, who: w["h"][who]


# ───────────── admin-only mode ─────────────
@pytest.fixture
def admin_only(monkeypatch):
    monkeypatch.setattr(settings, "enabled_roles", "admin")


def test_default_setting_is_admin_only():
    from app.config import Settings
    s = Settings(_env_file=None, enabled_roles="admin")
    assert s.role_enabled("admin") and not s.role_enabled("player") and not s.role_enabled("coach")
    assert Settings.model_fields["enabled_roles"].default == "admin"


def test_enabled_roles_validation():
    from pydantic import ValidationError
    from app.config import Settings
    assert Settings(enabled_roles="ALL").role_enabled("player")
    s = Settings(enabled_roles="admin, coach")
    assert s.role_enabled("coach") and not s.role_enabled("physio")
    for bad in ("", "admin,boss", "everyone"):
        with pytest.raises(ValidationError):
            Settings(enabled_roles=bad)


def test_only_admin_can_sign_in_when_admin_only(client, world, admin_only):
    ok = client.post("/auth/login", json={"email": "admin@slc.lk", "password": PW})
    assert ok.status_code == 200
    for who in ("coach_a", "sc_a", "physio_a", "ann_login"):
        r = client.post("/auth/login", json={"email": f"{who}@slc.lk", "password": PW})
        assert r.status_code == 403 and "administrators" in r.json()["detail"], who
    r = client.post("/auth/login", json={"email": "coach_a@slc.lk", "password": "WrongPassw0rd!"})
    assert r.status_code == 401                         # a wrong password never reveals that the role is disabled


def test_tokens_of_disabled_roles_stop_working(client, world, monkeypatch):
    coach, ann = H(world, "coach_a"), H(world, "ann_login")
    assert client.get("/players", headers=coach).status_code == 200
    monkeypatch.setattr(settings, "enabled_roles", "admin")
    assert client.get("/players", headers=coach).status_code == 401
    assert client.get("/players", headers=ann).status_code == 401
    assert client.get("/players", headers=H(world, "admin")).status_code == 200


# ───────────── season phases ─────────────
def test_phase_suggestion_endpoint(client, world):
    r = client.get("/season-phase-suggestion?start_date=2026-09-01&end_date=2027-06-30", headers=H(world, "admin"))
    ph = r.json()
    assert [p["phase_type"] for p in ph] == ["pre_season", "pre_competition", "in_season", "transition"]
    assert ph[0]["start_date"] == "2026-09-01" and ph[-1]["end_date"] == "2027-06-30"
    assert client.get("/season-phase-suggestion?start_date=2026-09-01&end_date=2026-09-20", headers=H(world, "admin")).status_code == 422


@pytest.mark.parametrize("start,end", [("2026-09-01", "2026-09-28"), ("2026-09-01", "2026-12-15"), ("2026-09-01", "2027-06-30"), ("2026-02-27", "2026-04-02")])
def test_suggested_phases_are_contiguous_and_cover_the_season(start, end):
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    ph = suggest_phases(s, e)
    assert ph[0]["start_date"] == s and ph[-1]["end_date"] == e
    for a, b in zip(ph, ph[1:]):
        assert (b["start_date"] - a["end_date"]).days == 1
    assert all(p["end_date"] >= p["start_date"] for p in ph)


def _season(client, w, who="admin", squad="squad_a", phases=None):
    r = client.post(f"/squads/{w[squad]}/seasons", json={"name": "2026/27", "start_date": "2026-09-01", "end_date": "2027-06-30", "phases": phases or []}, headers=H(w, who))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_edit_phases(client, world):
    w = world
    sid = _season(client, w)
    good = [{"phase_type": "pre_season", "start_date": "2026-09-01", "end_date": "2026-11-30"},
            {"phase_type": "in_season", "start_date": "2026-12-01", "end_date": "2027-04-30", "focus": "Matches"}]
    r = client.put(f"/seasons/{sid}/phases", json=good, headers=H(w, "admin"))
    assert r.status_code == 200 and [p["phase_type"] for p in r.json()["phases"]] == ["pre_season", "in_season"]
    r = client.put(f"/seasons/{sid}/phases", json=good[:1], headers=H(w, "admin"))          # replaced, not appended
    assert len(r.json()["phases"]) == 1
    bad = {
        "overlap": [good[0], {**good[1], "start_date": "2026-11-30"}],
        "outside": [{**good[0], "start_date": "2026-08-01"}],
        "duplicate type": [good[0], {**good[1], "phase_type": "pre_season"}],
        "end before start": [{**good[0], "end_date": "2026-08-31"}],
    }
    for name, body in bad.items():
        assert client.put(f"/seasons/{sid}/phases", json=body, headers=H(w, "admin")).status_code == 422, name
    assert client.put(f"/seasons/{sid}/phases", json=good, headers=H(w, "coach_b")).status_code == 404     # other squad
    assert client.put(f"/seasons/{sid}/phases", json=good, headers=H(w, "ann_login")).status_code == 403
    assert client.put("/seasons/9999/phases", json=good, headers=H(w, "admin")).status_code == 404


def test_admin_can_list_and_see_squad_staff(client, world):
    w = world
    names = [u["email"] for u in client.get(f"/admin/squads/{w['squad_a']}/staff", headers=H(w, "admin")).json()]
    assert names == ["coach_a@slc.lk", "physio_a@slc.lk", "sc_a@slc.lk"]
    assert client.get(f"/admin/squads/{w['squad_a']}/staff", headers=H(w, "coach_a")).status_code == 403


# ───────────── role-specific measures ─────────────
def test_every_role_has_measures_and_shared_ones_are_identical():
    from app.models import PlayerRole
    assert set(KPIS) == set(PlayerRole) and all(KPIS[r] for r in PlayerRole)
    assert "gather_to_release_s" in ALL_KPIS and ALL_KPIS["gather_to_release_s"].higher_is_better is False


def test_validate_role_specific_rules():
    from app.models import PlayerRole as R
    assert validate_role_specific(R.fast_bowler, {"avg_speed_kmh": 95.5, "new_ball_role": 3}) == {"avg_speed_kmh": 95.5, "new_ball_role": 3}
    assert validate_role_specific(R.fast_bowler, {"avg_speed_kmh": None}) == {"avg_speed_kmh": None}
    for role, bad in [(R.fast_bowler, {"strike_rate": 100}), (R.fast_bowler, {"avg_speed_kmh": 950}), (R.fast_bowler, {"new_ball_role": 3.5}),
                      (R.fast_bowler, {"new_ball_role": 6}), (R.spin_bowler, {"avg_speed_kmh": 90}), (R.batter, {"strike_rate": "fast"}),
                      (R.batter, {"strike_rate": True})]:
        with pytest.raises(ValueError):
            validate_role_specific(role, bad)


def test_role_kpi_endpoint(client, world):
    r = client.get("/meta/role-kpis/bat_wicketkeeper", headers=H(world, "coach_a")).json()
    assert [m["field"] for m in r] == ["batting_average", "strike_rate", "catch_success_pct", "gather_to_release_s"]
    assert next(m for m in r if m["field"] == "gather_to_release_s")["higher_is_better"] is False


def _put(client, w, who, pid, season, phase, body):
    return client.put(f"/players/{pid}/fitness/{season}/{phase}", json=body, headers=H(w, who))


def test_role_measures_are_stored_merged_and_validated(client, world):
    w = world
    sid = _season(client, w)
    base = {"test_date": "2026-09-05", "role_specific": {"stock_ball_accuracy_pct": 40, "drift_dip": 2}}        # Ann: spin bowler
    r = _put(client, w, "admin", w["ann"], sid, "baseline", base)
    assert r.status_code == 200 and r.json()["role_specific"] == {"stock_ball_accuracy_pct": 40, "drift_dip": 2}
    r = _put(client, w, "admin", w["ann"], sid, "baseline", {"role_specific": {"new_ball_role": 3}})            # merged
    assert r.json()["role_specific"] == {"stock_ball_accuracy_pct": 40, "drift_dip": 2, "new_ball_role": 3}
    r = _put(client, w, "admin", w["ann"], sid, "baseline", {"role_specific": {"drift_dip": None}})              # one cleared
    assert r.json()["role_specific"] == {"stock_ball_accuracy_pct": 40, "new_ball_role": 3}
    r = _put(client, w, "admin", w["ann"], sid, "baseline", {"role_specific": None})                             # all cleared
    assert r.json()["role_specific"] is None
    for bad in ({"avg_speed_kmh": 90}, {"stock_ball_accuracy_pct": 140}, {"drift_dip": 2.5}):
        assert _put(client, w, "admin", w["ann"], sid, "mid_season", {"test_date": "2026-12-05", "role_specific": bad}).status_code == 422
    # a test that only has an empty role_specific is not a result
    assert _put(client, w, "admin", w["ann"], sid, "end_season", {"test_date": "2027-05-05", "role_specific": {}}).status_code == 422


def test_role_measures_in_progress_report(client, world):
    w = world
    sid = _season(client, w)
    _put(client, w, "admin", w["bob"], sid, "baseline", {"test_date": "2026-09-05", "role_specific": {"avg_speed_kmh": 80, "dot_ball_pct_bowling": 40}})   # Bob: fast
    _put(client, w, "admin", w["bob"], sid, "mid_season", {"test_date": "2026-12-05", "role_specific": {"avg_speed_kmh": 84}})
    rep = client.get(f"/players/{w['bob']}/fitness/progress?season_id={sid}", headers=H(w, "coach_a")).json()
    assert rep["role"] == "fast_bowler" and [m["field"] for m in rep["role_metrics"]] == ["avg_speed_kmh", "dot_ball_pct_bowling", "new_ball_role"]
    sp = rep["role_metrics"][0]
    assert (sp["baseline"], sp["current"], sp["current_phase"], sp["change_from_baseline"], sp["improved"]) == (80, 84, "mid_season", 4, True)
    assert rep["role_metrics"][1]["current_phase"] == "baseline" and rep["role_metrics"][2]["current"] is None
    assert all(m["field"] != "avg_speed_kmh" for m in rep["metrics"])          # role measures are not mixed into the fitness tests


def test_role_measure_targets(client, world):
    w = world
    sid = _season(client, w)
    _put(client, w, "admin", w["bob"], sid, "baseline", {"test_date": "2026-09-05", "role_specific": {"avg_speed_kmh": 80}})
    assert client.put(f"/players/{w['bob']}/fitness-targets", json={"field_name": "avg_speed_kmh", "target_value": 85}, headers=H(w, "admin")).status_code == 200
    assert client.put(f"/players/{w['bob']}/fitness-targets", json={"field_name": "stock_ball_accuracy_pct", "target_value": 60}, headers=H(w, "admin")).status_code == 422   # spin measure
    assert client.put(f"/players/{w['bob']}/fitness-targets", json={"field_name": "avg_speed_kmh", "target_value": 900}, headers=H(w, "admin")).status_code == 422
    rep = client.get(f"/players/{w['bob']}/fitness/progress?season_id={sid}", headers=H(w, "admin")).json()
    row = rep["role_metrics"][0]
    assert (row["individual_target"], row["individual_target_status"]) == (85, "not_yet")


# ───────────── exercise library ─────────────
def test_library_matches_the_supplied_file_and_is_reproducible():
    from scripts.build_exercise_library import build
    from app.exercises import ADDED_GROUPS
    lib = library()
    supplied = {**lib, "groups": {k: v for k, v in lib["groups"].items() if k not in ADDED_GROUPS}}
    assert build() == supplied                          # the supplied part is exactly what the text file produces
    g = lib["groups"]
    assert {k: (len(v["physical"]), len(v["skill"])) for k, v in g.items() if k not in ADDED_GROUPS} == {"spin": (21, 19), "fast": (29, 19), "fielding": (25, 18)}
    assert all(e.get("added") for k in ADDED_GROUPS for e in g[k]["skill"]) and not any(e.get("added") for k in ("spin", "fast", "fielding") for e in g[k]["skill"])
    assert sum(x["minutes"] for x in library()["session_template"]) == 60
    assert "low and progressive" in library()["guidance"][0]


def test_every_exercise_is_classified_and_complete():
    for grp in library()["groups"].values():
        for cat in grp.values():
            for e in cat:
                assert e["kind"] != "other" and e["name"] and e["purpose"] and e["areas"], e


def test_phase_mapping_is_conservative():
    names = lambda groups, ph: {e["name"] for e in exercises_for(groups, ph)}
    assert "Plank" in names(["fast"], "pre_season") and "Yorker drill" not in names(["fast"], "pre_season")      # base first
    assert "Yorker drill" in names(["fast"], "pre_competition") and "Bounding" in names(["fast"], "pre_competition")
    assert "Bounding" not in names(["fast"], "pre_season")
    tr = names(["fast", "spin", "fielding"], "transition")
    assert not any(w in n for n in tr for w in ("bowling", "Yorker", "Bounding", "sprint", "jump")), tr          # no bowling or high intensity
    assert "Easy aerobic running" in tr
    assert PHASE_KINDS.keys() == {"pre_season", "pre_competition", "in_season", "transition"}


# ───────────── plan generation (API) ─────────────
FULL = [{"phase_type": "pre_season", "start_date": "2026-09-01", "end_date": "2026-11-30"},
        {"phase_type": "pre_competition", "start_date": "2026-12-01", "end_date": "2027-01-31"},
        {"phase_type": "in_season", "start_date": "2027-02-01", "end_date": "2027-05-31"},
        {"phase_type": "transition", "start_date": "2027-06-01", "end_date": "2027-06-30"}]


@pytest.fixture
def planned(client, world, seeded):
    w = world
    sid = _season(client, w, phases=FULL)
    ev = f"/squads/{w['squad_a']}/events"
    client.post(ev, json={"event_type": "match", "title": "vs Kandy", "start_at": "2026-12-12T09:00:00+05:30"}, headers=H(w, "admin"))
    client.post(ev, json={"event_type": "fitness_test", "title": "Baseline testing", "start_at": "2026-09-05T09:00:00+05:30"}, headers=H(w, "admin"))
    client.post(ev, json={"event_type": "rest", "title": "Recovery day", "start_at": "2027-03-01T09:00:00+05:30"}, headers=H(w, "admin"))
    client.post(ev, json={"event_type": "match", "title": "Outside the season", "start_at": "2027-08-01T09:00:00+05:30"}, headers=H(w, "admin"))
    return sid


def plan_url(w, sid, suffix=""):
    return f"/squads/{w['squad_a']}/seasons/{sid}/seasonal-plan{suffix}"


def test_plan_structure(client, world, planned):
    w = world
    p = client.get(plan_url(w, planned), headers=H(w, "admin")).json()
    assert p["roles"] == ["fast_bowler", "spin_bowler"]                           # the roles actually in squad A, in a fixed order
    assert len(p["rows"]) == 4 * (6 + 3 * 2)                                       # phases x (6 common areas + 3 per role)
    assert [x["phase_type"] for x in p["phases"]] == ["pre_season", "pre_competition", "in_season", "transition"]
    assert p["phases_source"] == "defined" and p["saved"] is False
    areas = {r["development_area"] for r in p["rows"]}
    assert areas == {"technical", "tactical", "physical", "mental", "nutrition", "recovery"}
    for r in p["rows"]:                                                            # every row has everything the brief asks for
        for f in ("goal", "start_date", "end_date", "planned_activities", "responsible", "measurement_method", "target_outcome", "status"):
            assert r[f], (r["key"], f)
    assert len({r["key"] for r in p["rows"]}) == len(p["rows"])
    pre = p["phases"][0]
    assert pre["fitness_tests"][0]["title"] == "Baseline testing" and pre["weeks"] == 13
    assert p["phases"][1]["matches"] == 1 and p["phases"][2]["rest_days"] == 1
    assert sum(x["matches"] for x in p["phases"]) == 1                             # the match outside the season is not counted
    assert p["testing"][0]["scheduled"][0]["title"] == "Baseline testing" and "scheduled" not in p["testing"][1]
    assert any("Fast bowlers" == x["applies_to"] and "16 overs" in x["rule"] for x in p["workload_rules"])


def test_responsible_staff_come_from_the_squad(client, world, planned):
    w = world
    p = client.get(plan_url(w, planned), headers=H(w, "admin")).json()
    by = lambda area: next(r for r in p["rows"] if r["development_area"] == area and r["applies_to"] is None)["responsible"]
    assert by("technical") == "coach_a" and by("physical") == "sc_a, coach_a" and by("recovery") == "physio_a, sc_a"
    assert p["staff"] == {"coach": ["coach_a"], "sc_coach": ["sc_a"], "physio": ["physio_a"]}


def test_roles_filter_and_validation(client, world, planned):
    w = world
    p = client.get(plan_url(w, planned) + "?roles=batter,all_rounder", headers=H(w, "admin")).json()
    assert p["roles"] == ["batter", "all_rounder"] and len(p["rows"]) == 4 * (6 + 6)
    assert any("no batting or wicketkeeping drills" in n for n in p["notes"])
    assert client.get(plan_url(w, planned) + "?roles=goalkeeper", headers=H(w, "admin")).status_code == 422


def test_plan_content_is_role_and_phase_appropriate(client, world, planned):
    w = world
    p = client.get(plan_url(w, planned), headers=H(w, "admin")).json()
    row = lambda ph, area, role: next(r for r in p["rows"] if (r["phase"], r["development_area"], r["applies_to"]) == (ph, area, role))
    assert "Yorker" not in row("pre_season", "technical", "fast_bowler")["planned_activities"]
    assert "Yorker" in row("pre_competition", "technical", "fast_bowler")["planned_activities"]
    assert "Googly" not in row("pre_competition", "technical", "fast_bowler")["planned_activities"]               # no spin drills for fast bowlers
    assert "Top-spinner" in row("pre_competition", "technical", "spin_bowler")["planned_activities"]
    assert "Nordic" in row("pre_season", "physical", "fast_bowler")["planned_activities"]
    assert "Nordic" not in row("pre_season", "physical", "spin_bowler")["planned_activities"]
    assert "Plank" in row("pre_season", "physical", "spin_bowler")["planned_activities"]
    tr = row("transition", "physical", "fast_bowler")["planned_activities"]
    assert "Easy aerobic" in tr and not any(w_ in tr for w_ in ("Bounding", "sprint", "Yorker"))
    assert "Average bowling speed (km/h)" in row("pre_season", "technical", "fast_bowler")["measurement_method"]            # role measures are linked
    assert "Stock-ball accuracy" in row("pre_season", "technical", "spin_bowler")["measurement_method"]
    assert "wicket-taking opportunity" in row("pre_season", "tactical", "spin_bowler")["planned_activities"]            # Scenario sheet is used
    assert "Core Action" in row("pre_season", "technical", "spin_bowler")["goal"]                                       # workbook skill groups are used
    assert "low and progressive" in row("pre_season", "physical", "fast_bowler")["planned_activities"]


def test_plan_has_no_adult_standards_or_invented_numeric_targets(client, world, planned):
    p = client.get(plan_url(w := world, planned), headers=H(w, "admin")).json()
    for r in p["rows"]:
        assert not any(x in r["target_outcome"].lower() for x in ("pass", "fail", "elite", "international standard"))
    assert any("No adult standards" in r["target_outcome"] for r in p["rows"] if r["development_area"] == "physical")


def test_season_without_phases_gets_a_suggested_split(client, world, seeded):
    w = world
    sid = _season(client, w)
    p = client.get(plan_url(w, sid), headers=H(w, "admin")).json()
    assert p["phases_source"] == "suggested" and len(p["phases"]) == 4
    assert any("SUGGESTED" in n for n in p["notes"])


def test_partial_phases_are_flagged(client, world, seeded):
    w = world
    sid = _season(client, w, phases=FULL[:2])
    p = client.get(plan_url(w, sid), headers=H(w, "admin")).json()
    assert len(p["phases"]) == 2 and any("in season, transition" in n.replace("_", " ") for n in p["notes"])


def test_empty_squad_plans_every_role(client, world, seeded):
    w = world
    sid = _season(client, w, who="admin", squad="squad_b")                           # squad B has one batter...
    client.patch(f"/players/{w['cara']}", json={"is_active": False}, headers=H(w, "admin"))
    p = client.get(f"/squads/{w['squad_b']}/seasons/{sid}/seasonal-plan", headers=H(w, "admin")).json()
    assert len(p["roles"]) == 5 and any("no players yet" in n for n in p["notes"])


def test_short_season_cannot_be_planned_without_phases(client, world, seeded):
    w = world
    r = client.post(f"/squads/{w['squad_a']}/seasons", json={"name": "Short", "start_date": "2030-01-01", "end_date": "2030-01-20"}, headers=H(w, "admin"))
    assert client.get(plan_url(w, r.json()["id"]), headers=H(w, "admin")).status_code == 422


# ───────────── save, status, review ─────────────
def test_save_then_track_status_and_review(client, world, planned):
    w = world
    r = client.post(plan_url(w, planned, "/save"), headers=H(w, "admin"))
    assert r.json() == {"new": 48, "updated": 0, "removed": 0}
    p = client.get(plan_url(w, planned), headers=H(w, "admin")).json()
    assert p["saved"] and all(x["plan_item_id"] and x["status"] == "not_started" for x in p["rows"])
    item = p["rows"][0]["plan_item_id"]
    r = client.patch(f"/plan-items/{item}", json={"status": "in_progress", "coach_review": "  Good start  "}, headers=H(w, "admin"))
    assert r.json() == {"id": item, "status": "in_progress", "coach_review": "Good start"}
    r = client.post(plan_url(w, planned, "/save"), headers=H(w, "admin"))                # idempotent, keeps status and review
    assert r.json() == {"new": 0, "updated": 48, "removed": 0}
    first = client.get(plan_url(w, planned), headers=H(w, "admin")).json()["rows"][0]
    assert (first["status"], first["coach_review"]) == ("in_progress", "Good start")
    assert client.patch(f"/plan-items/{item}", json={"coach_review": None}, headers=H(w, "admin")).json()["coach_review"] is None
    assert client.patch(f"/plan-items/{item}", json={"status": "finished"}, headers=H(w, "admin")).status_code == 422
    assert client.patch(f"/plan-items/{item}", json={"coach_review": "x" * 2001}, headers=H(w, "admin")).status_code == 422
    assert client.patch("/plan-items/99999", json={"status": "achieved"}, headers=H(w, "admin")).status_code == 404


def test_resave_with_fewer_roles_removes_only_untouched_rows(client, world, planned):
    w = world
    client.post(plan_url(w, planned, "/save"), headers=H(w, "admin"))
    rows = client.get(plan_url(w, planned), headers=H(w, "admin")).json()["rows"]
    spin = next(r for r in rows if r["applies_to"] == "spin_bowler")
    client.patch(f"/plan-items/{spin['plan_item_id']}", json={"coach_review": "keep me"}, headers=H(w, "admin"))
    r = client.post(plan_url(w, planned, "/save") + "?roles=fast_bowler", headers=H(w, "admin"))
    assert r.json()["removed"] == 11                                                       # 12 spin rows minus the one with a review
    rows = client.get(plan_url(w, planned) + "?roles=fast_bowler,spin_bowler", headers=H(w, "admin")).json()["rows"]
    assert next(r for r in rows if r["key"] == spin["key"])["coach_review"] == "keep me"


def test_plan_access_rules(client, world, planned):
    w = world
    url = plan_url(w, planned)
    for who in ("coach_a", "sc_a", "physio_a", "admin"):
        assert client.get(url, headers=H(w, who)).status_code == 200, who
    assert client.get(url, headers=H(w, "ann_login")).status_code == 403                    # not shared with players
    assert client.get(url, headers=H(w, "coach_b")).status_code == 404                      # other squad
    assert client.get(f"/squads/{w['squad_b']}/seasons/{planned}/seasonal-plan", headers=H(w, "admin")).status_code == 404   # season of another squad
    assert client.post(url + "/save", headers=H(w, "sc_a")).status_code == 403
    assert client.post(url + "/save", headers=H(w, "physio_a")).status_code == 403
    assert client.post(url + "/save", headers=H(w, "coach_b")).status_code == 404
    assert client.post(url + "/save", headers=H(w, "coach_a")).status_code == 200
    item = client.get(url, headers=H(w, "coach_a")).json()["rows"][0]["plan_item_id"]
    assert client.patch(f"/plan-items/{item}", json={"status": "achieved"}, headers=H(w, "coach_b")).status_code == 404
    assert client.patch(f"/plan-items/{item}", json={"status": "achieved"}, headers=H(w, "ann_login")).status_code == 403
    assert client.get(url + ".xlsx", headers=H(w, "ann_login")).status_code == 403
    assert client.get(url).status_code == 401


# ───────────── Excel ─────────────
def test_excel_download(client, world, planned):
    w = world
    client.post(plan_url(w, planned, "/save"), headers=H(w, "admin"))
    item = client.get(plan_url(w, planned), headers=H(w, "admin")).json()["rows"][0]["plan_item_id"]
    client.patch(f"/plan-items/{item}", json={"status": "achieved", "coach_review": "Done well"}, headers=H(w, "admin"))
    r = client.get(plan_url(w, planned, ".xlsx"), headers=H(w, "admin"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="seasonal-plan-Western-U15-2026-27.xlsx"' in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Overview", "Seasonal Plan", "Role Programmes", "Workload Rules", "Session Template", "Calendar"]
    ws = wb["Seasonal Plan"]
    head = [c.value for c in ws[4]]
    assert head == ["Phase", "Applies to", "Development area", "Goal", "Start", "End", "Planned activities", "Responsible coach",
                    "Measurement method", "Target outcome", "Progress status", "Coach review"]
    assert ws.max_row == 4 + 48
    assert (ws["K5"].value, ws["L5"].value) == ("Achieved", "Done well")                    # saved status and review are in the export
    assert ws["K6"].value == "Not started" and ws["A5"].value == "Pre-season"
    assert ws.data_validations.dataValidation and "Achieved" in ws.data_validations.dataValidation[0].formula1
    assert wb["Role Programmes"].max_row > 100 and wb["Session Template"]["B5"].value == 10
    assert wb["Calendar"].max_row == 4 + 3                                                    # the three in-season events, not the outside one
    assert wb["Overview"]["A5"].value == "Pre-season"


def test_excel_never_turns_text_into_formulas(client, world, seeded):
    w = world
    client.post("/admin/squads", json={"name": "=HYPERLINK(\"http://x\")", "province": "W"}, headers=H(w, "admin"))
    sq = [s for s in client.get("/admin/squads", headers=H(w, "admin")).json() if s["name"].startswith("=")][0]["id"]
    sid = client.post(f"/squads/{sq}/seasons", json={"name": "=1+1", "start_date": "2026-09-01", "end_date": "2027-06-30", "phases": FULL}, headers=H(w, "admin")).json()["id"]
    r = client.get(f"/squads/{sq}/seasons/{sid}/seasonal-plan.xlsx", headers=H(w, "admin"))
    assert r.status_code == 200 and 'filename="seasonal-plan-HYPERLINK-http-x-1-1.xlsx"' in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    cell = wb["Overview"]["A1"]
    assert cell.data_type == "s" and cell.value.startswith("Seasonal plan - =HYPERLINK")
    for ws in wb:
        for row in ws.iter_rows():
            assert all(c.data_type != "f" for c in row)


def test_plan_does_not_leak_medical_data(client, world, planned):
    w = world
    client.put(f"/players/{w['ann']}/medical", json={"current_health": "Stress reaction L4"}, headers=H(w, "physio_a"))
    body = client.get(plan_url(w, planned), headers=H(w, "admin")).text
    wb = openpyxl.load_workbook(io.BytesIO(client.get(plan_url(w, planned, ".xlsx"), headers=H(w, "admin")).content))
    cells = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    assert "Stress" not in body + cells and "L4" not in body + cells and "Ann" not in cells          # no medical data, no player names
