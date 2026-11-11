"""U15 and U17 squads in one system: each squad's age group picks its rules (app/age_groups.py)."""
from datetime import date, timedelta

import pytest

from app import workload_rules as wr
from app.age_groups import PROFILES, check_dob, profile
from app.annual_grid import build_grid
from app.load_distribution import build_loads
from app.plan_load import verify
from app.season_phases import suggest_phases
from app.seasonal_plan import workload_rules_for
from app.models import Squad, UserRole
from .conftest import login, make_user

TODAY = date.today()


# ───────────── profiles (pure) ─────────────
def test_profiles_and_fallback():
    assert set(PROFILES) == {"U15", "U17"}
    assert profile(None).code == profile("nonsense").code == "U15"           # unknown falls back to the strictest rules
    assert profile("u17").code == "U17"
    u15, u17 = PROFILES["U15"].fast_limits, PROFILES["U17"].fast_limits
    assert u15 == wr.DEFAULT_FAST_LIMITS                                      # U15 is unchanged
    assert u17["max_spell_overs"] > u15["max_spell_overs"] and u17["max_match_day_overs"] > u15["max_match_day_overs"]
    assert PROFILES["U17"].provisional and any("PLACEHOLDER" in n for n in PROFILES["U17"].notes)


def test_dob_ranges_follow_the_age_group():
    seventeen = date(TODAY.year - 17, TODAY.month, 1)
    check_dob("U17", seventeen, TODAY)
    with pytest.raises(ValueError, match="U15"):
        check_dob("U15", seventeen, TODAY)
    with pytest.raises(ValueError, match="U17"):
        check_dob("U17", date(TODAY.year - 9, 1, 1), TODAY)


def test_fast_bowler_limits_follow_the_age_group():
    assert wr.effective_limits("fast_bowler", None, "U17")["max_spell_overs"] == 6
    assert wr.effective_limits("fast_bowler", None)["max_spell_overs"] == 5
    assert wr.effective_limits("fast_bowler", {"max_spell_overs": 4}, "U17")["max_spell_overs"] == 4   # the coach's own limit wins
    assert wr.effective_limits("batter", None, "U17") is None                                         # no automatic limit, any age


def test_six_over_spell_is_a_stop_for_u15_but_not_for_u17():
    day = TODAY - timedelta(days=1)
    logs = [wr.Log(date=day, session_type="match", duration_min=120, rpe=6, overs_bowled=6, spells=[{"overs": 6}])]
    codes = lambda age: {a.rule_code for a in wr.evaluate(logs, [], "fit", "fast_bowler", None, TODAY, age)[0]}
    assert "BOWL_SPELL_OVERS" in codes("U15")
    assert "BOWL_SPELL_OVERS" not in codes("U17")


def test_annual_plan_peak_and_bowling_follow_the_age_group():
    start, end = date(2027, 1, 1), date(2027, 9, 30)
    g = lambda age: build_grid(squad_name="X", season={"name": "2027", "start_date": start, "end_date": end},
                               phases=suggest_phases(start, end), events=[], generated_on=start, age_group=age)
    g15, g17 = g("U15"), g("U17")
    assert g15["age_group"] == "U15" and g17["age_group"] == "U17"
    assert max(g15["percentage"]) == PROFILES["U15"].load_peak and max(g17["percentage"]) == PROFILES["U17"].load_peak
    for grid, age in ((g15, "U15"), (g17, "U17")):
        ld = build_loads(grid)
        spell_max = PROFILES[age].fast_limits["max_spell_overs"]
        assert all(int(o) <= spell_max for s in ld["spells"] if s for o in s.split("+"))
        assert f"Spells never exceed {spell_max} overs" in " ".join(ld["notes"])
    assert "16 overs on a match day" in " ".join(r["rule"] for r in workload_rules_for("U15"))
    assert "18 overs on a match day" in " ".join(r["rule"] for r in workload_rules_for("U17"))


def test_plan_verify_uses_the_age_group_limits():
    week = {"week": 1, "match_over_limit": False, "rise_cap_pct": None, "load_ratio": None, "match_load": 0, "bowl_load": 0,
            "focus_load": 0, "planned_load": 1000, "bowl_days": 1, "matches": 0, "spells": "6"}
    assert any("spell" in v for v in verify({"weeks": [week]}, fast=True))                                  # U15: 5-over spells
    assert not verify({"weeks": [week]}, fast=True, limits=PROFILES["U17"].fast_limits)


# ───────────── API ─────────────
def test_admin_creates_u17_squad_and_unknown_age_group_is_rejected(client, db):
    make_user(db, "admin@slc.lk", UserRole.admin)
    h = login(client, "admin@slc.lk")
    r = client.post("/admin/squads", headers=h, json={"name": "Western U17", "province": "Western", "age_group": "u17"})
    assert r.status_code == 201 and r.json()["age_group"] == "U17"
    assert client.post("/admin/squads", headers=h, json={"name": "Odd", "province": "W", "age_group": "U99"}).status_code == 422
    assert client.post("/admin/squads", headers=h, json={"name": "Default", "province": "W"}).json()["age_group"] == "U15"


def test_player_age_is_checked_against_the_squad(client, db):
    make_user(db, "admin@slc.lk", UserRole.admin)
    h = login(client, "admin@slc.lk")
    u15 = client.post("/admin/squads", headers=h, json={"name": "W U15", "province": "W", "age_group": "U15"}).json()["id"]
    u17 = client.post("/admin/squads", headers=h, json={"name": "W U17", "province": "W", "age_group": "U17"}).json()["id"]
    seventeen = date(TODAY.year - 17, TODAY.month, 1).isoformat()
    body = dict(full_name="Older Kid", date_of_birth=seventeen, gender="male", role="fast_bowler")
    r = client.post("/players", headers=h, json={**body, "squad_id": u15})
    assert r.status_code == 422 and "U15" in r.text
    r = client.post("/players", headers=h, json={**body, "squad_id": u17})
    assert r.status_code == 201
    pid = r.json()["id"]
    moved = client.patch(f"/players/{pid}", headers=h, json={"squad_id": u15})            # cannot be moved into a younger squad
    assert moved.status_code == 422
    assert client.post("/players", headers=h, json={**body, "squad_id": u17, "date_of_birth": "1990-01-01"}).status_code == 422


def test_effective_limits_endpoint_and_rules_use_the_squad_age_group(client, db):
    make_user(db, "admin@slc.lk", UserRole.admin)
    h = login(client, "admin@slc.lk")
    u17 = client.post("/admin/squads", headers=h, json={"name": "W U17", "province": "W", "age_group": "U17"}).json()["id"]
    pid = client.post("/players", headers=h, json=dict(squad_id=u17, full_name="Quick", date_of_birth=date(TODAY.year - 16, 1, 1).isoformat(),
                                                         gender="male", role="fast_bowler")).json()["id"]
    summary = client.get(f"/players/{pid}/workload/summary", headers=h)
    assert summary.status_code == 200, summary.text
    assert summary.json()["summary"]["bowling"]["limits"]["max_spell_overs"] == 6
    rules = client.get("/workload/rules?age_group=U17", headers=h).json()
    assert rules["age_group"] == "U17" and rules["fast_bowler_defaults"]["max_match_day_overs"] == 18
    assert any("PLACEHOLDER" in n for n in rules["notes"])
    ages = client.get("/meta/age-groups", headers=h).json()
    assert [a["code"] for a in ages] == ["U15", "U17"]
