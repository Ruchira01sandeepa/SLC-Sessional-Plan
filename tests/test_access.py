"""Role-based access: who can see / change what. These are the privacy guarantees of the system."""
import sqlite3

import pytest

from app.config import settings
from app.models import AuditLog, UserRole
from .conftest import PW, make_user


def ids(resp):
    return {p["id"] for p in resp.json()}


# ───────────── player visibility ─────────────
def test_coach_sees_only_own_squad(client, world):
    w = world
    assert ids(client.get("/players", headers=w["h"]["coach_a"])) == {w["ann"], w["bob"]}
    assert ids(client.get("/players", headers=w["h"]["coach_b"])) == {w["cara"]}


def test_admin_sees_everyone(client, world):
    w = world
    assert ids(client.get("/players", headers=w["h"]["admin"])) == {w["ann"], w["bob"], w["cara"]}


def test_player_sees_only_self(client, world):
    w = world
    assert ids(client.get("/players", headers=w["h"]["ann_login"])) == {w["ann"]}
    assert client.get(f"/players/{w['ann']}", headers=w["h"]["ann_login"]).status_code == 200
    assert client.get(f"/players/{w['bob']}", headers=w["h"]["ann_login"]).status_code == 404   # teammate
    assert client.get(f"/players/{w['cara']}", headers=w["h"]["ann_login"]).status_code == 404


def test_cross_squad_access_is_404_not_403(client, world):
    """A coach must not be able to tell whether a player in another squad exists."""
    w = world
    other = client.get(f"/players/{w['cara']}", headers=w["h"]["coach_a"])
    missing = client.get("/players/99999", headers=w["h"]["coach_a"])
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


def test_squad_filter_cannot_widen_scope(client, world):
    w = world
    r = client.get(f"/players?squad_id={w['squad_b']}", headers=w["h"]["coach_a"])
    assert r.status_code == 200 and r.json() == []


def test_staff_with_no_squads_sees_nobody(client, db, world):
    make_user(db, "lonely@slc.lk", UserRole.coach)
    from .conftest import login
    assert client.get("/players", headers=login(client, "lonely@slc.lk")).json() == []


# ───────────── writes ─────────────
def _new_player(squad_id, **kw):
    return dict(squad_id=squad_id, full_name="New Kid", date_of_birth="2012-03-04", gender="male", role="batter", **kw)


def test_coach_creates_players_only_in_own_squad(client, world):
    w = world
    assert client.post("/players", json=_new_player(w["squad_a"]), headers=w["h"]["coach_a"]).status_code == 201
    assert client.post("/players", json=_new_player(w["squad_b"]), headers=w["h"]["coach_a"]).status_code == 403
    assert client.post("/players", json=_new_player(w["squad_b"]), headers=w["h"]["admin"]).status_code == 201


@pytest.mark.parametrize("who", ["sc_a", "physio_a", "ann_login"])
def test_other_roles_cannot_create_players(client, world, who):
    assert client.post("/players", json=_new_player(world["squad_a"]), headers=world["h"][who]).status_code == 403


def test_dob_must_be_plausible_u15(client, world):
    for dob in ("1990-01-01", "2022-01-01"):
        r = client.post("/players", json={**_new_player(world["squad_a"]), "date_of_birth": dob}, headers=world["h"]["coach_a"])
        assert r.status_code == 422


def test_coach_edits_own_squad_player_but_not_others(client, world):
    w = world
    assert client.patch(f"/players/{w['ann']}", json={"school_or_club": "Royal"}, headers=w["h"]["coach_a"]).status_code == 200
    assert client.patch(f"/players/{w['cara']}", json={"school_or_club": "X"}, headers=w["h"]["coach_a"]).status_code == 404


def test_player_cannot_edit_self(client, world):
    w = world
    assert client.patch(f"/players/{w['ann']}", json={"full_name": "Hacked"}, headers=w["h"]["ann_login"]).status_code == 403


def test_only_admin_moves_players_between_squads(client, world):
    w = world
    r = client.patch(f"/players/{w['ann']}", json={"squad_id": w["squad_b"]}, headers=w["h"]["coach_a"])
    assert r.status_code == 403
    r = client.patch(f"/players/{w['ann']}", json={"squad_id": w["squad_b"]}, headers=w["h"]["admin"])
    assert r.status_code == 200 and r.json()["squad_id"] == w["squad_b"]


def test_link_user_rules(client, world):
    w = world
    u = w["users"]
    assert client.put(f"/players/{w['cara']}/link-user", json={"user_id": u["coach_a"].id}, headers=w["h"]["admin"]).status_code == 400  # not a player login
    assert client.put(f"/players/{w['cara']}/link-user", json={"user_id": u["ann_login"].id}, headers=w["h"]["admin"]).status_code == 409  # already Ann's
    assert client.put(f"/players/{w['cara']}/link-user", json={"user_id": u["bob_login"].id}, headers=w["h"]["coach_a"]).status_code in (403, 404)


# ───────────── admin area ─────────────
def test_only_admin_manages_users_and_squads(client, world):
    w = world
    body = dict(email="new@slc.lk", full_name="New", role="coach", temp_password="Temp0raryPass!")
    for who in ("coach_a", "sc_a", "physio_a", "ann_login"):
        assert client.post("/admin/users", json=body, headers=w["h"][who]).status_code == 403, who
        assert client.get("/admin/users", headers=w["h"][who]).status_code == 403
        assert client.post("/admin/squads", json=dict(name="Z", province="Z"), headers=w["h"][who]).status_code == 403
    assert client.post("/admin/users", json=body, headers=w["h"]["admin"]).status_code == 201
    assert client.post("/admin/users", json=body, headers=w["h"]["admin"]).status_code == 409   # duplicate email


def test_admin_created_user_must_change_password(client, world):
    w = world
    client.post("/admin/users", json=dict(email="n@slc.lk", full_name="N", role="coach", temp_password="Temp0rary1Pass"), headers=w["h"]["admin"])
    h = {"Authorization": "Bearer " + client.post("/auth/login", json={"email": "n@slc.lk", "password": "Temp0rary1Pass"}).json()["access_token"]}
    assert client.get("/players", headers=h).status_code == 403


def test_staff_assignment_limits_visibility_and_rejects_players(client, world):
    w = world
    u = w["users"]
    # give coach_b access to squad A as well
    r = client.put(f"/admin/squads/{w['squad_a']}/staff", json={"user_ids": [u["coach_a"].id, u["coach_b"].id]}, headers=w["h"]["admin"])
    assert r.status_code == 200
    assert {w["ann"], w["bob"], w["cara"]} == ids(client.get("/players", headers=w["h"]["coach_b"]))
    # sc_a / physio_a were removed from squad A by that replace -> they lose sight of it
    assert client.get("/players", headers=w["h"]["physio_a"]).json() == []
    assert client.put(f"/admin/squads/{w['squad_a']}/staff", json={"user_ids": [u["ann_login"].id]}, headers=w["h"]["admin"]).status_code == 400


def test_admin_cannot_lock_themselves_out(client, world):
    w = world
    me = w["users"]["admin"].id
    assert client.patch(f"/admin/users/{me}", json={"is_active": False}, headers=w["h"]["admin"]).status_code == 400
    assert client.patch(f"/admin/users/{me}", json={"role": "coach"}, headers=w["h"]["admin"]).status_code == 400


# ───────────── medical & injury data ─────────────
MED = {"current_health": "Mild lower-back stiffness",
       "injury_history": {"has_history": True, "notes": "Stress reaction L4 in 2025", "first_injury_age": 12, "times_out_of_play": 2},
       "reports": {"mri": "L4 pars oedema, resolved"},
       "injured_body_parts": {"core": "lumbar"}}


def test_physio_reads_and_writes_medical(client, world):
    w = world
    r = client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    assert r.status_code == 200 and r.json()["injury_history"]["notes"].startswith("Stress")
    r = client.get(f"/players/{w['ann']}/medical", headers=w["h"]["physio_a"])
    assert r.json()["current_health"] == "Mild lower-back stiffness" and r.json()["reports"]["mri"].startswith("L4")


def test_partial_medical_update_keeps_other_fields(client, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    client.put(f"/players/{w['ann']}/medical", json={"current_health": "Recovered"}, headers=w["h"]["physio_a"])
    r = client.get(f"/players/{w['ann']}/medical", headers=w["h"]["physio_a"]).json()
    assert r["current_health"] == "Recovered" and r["injury_history"]["first_injury_age"] == 12


@pytest.mark.parametrize("who", ["coach_a", "sc_a", "admin", "ann_login", "bob_login"])
def test_everyone_else_is_denied_medical(client, world, who):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    assert client.get(f"/players/{w['ann']}/medical", headers=w["h"][who]).status_code in (403, 404)
    assert client.put(f"/players/{w['ann']}/medical", json={"current_health": "x"}, headers=w["h"][who]).status_code in (403, 404)


def test_player_cannot_read_even_own_medical(client, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    assert client.get(f"/players/{w['ann']}/medical", headers=w["h"]["ann_login"]).status_code == 403


def test_physio_of_other_squad_cannot_see_medical(client, db, world):
    w = world
    make_user(db, "physio_b@slc.lk", UserRole.physio)
    from app.models import SquadStaff
    db.add(SquadStaff(user_id=db.query(type(w["users"]["admin"])).filter_by(email="physio_b@slc.lk").one().id, squad_id=w["squad_b"]))
    db.commit()
    from .conftest import login
    hb = login(client, "physio_b@slc.lk")
    assert client.get(f"/players/{w['ann']}/medical", headers=hb).status_code == 404
    assert client.get(f"/players/{w['cara']}/medical", headers=hb).status_code == 200


def test_medical_never_leaks_through_player_endpoints(client, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    for who in ("physio_a", "coach_a", "ann_login", "admin"):
        body = client.get(f"/players/{w['ann']}", headers=w["h"][who]).text
        for secret in ("lower-back", "Stress reaction", "L4", "oedema", "injury_history", "medical"):
            assert secret not in body, (who, secret)
        listing = client.get("/players", headers=w["h"][who]).text
        assert "lower-back" not in listing and "Stress reaction" not in listing


def test_medical_is_encrypted_in_the_database_file(client, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    path = settings.database_url.replace("sqlite:///", "")
    raw = sqlite3.connect(path).execute("select current_health, injury_history, reports, injured_body_parts from player_medical").fetchone()
    blob = " ".join(raw)
    for secret in ("lower-back", "Stress", "oedema", "lumbar", "has_history"):
        assert secret not in blob
    assert all(v.startswith("gAAAA") for v in raw)          # Fernet tokens


def test_medical_cannot_be_decrypted_with_wrong_key(db, world):
    from cryptography.fernet import Fernet, InvalidToken
    import sqlite3 as s
    # write something, then try to open it with a different key
    from app.models import PlayerMedical
    db.add(PlayerMedical(player_id=world["ann"], current_health={"text": "secret"}))
    db.commit()
    path = settings.database_url.replace("sqlite:///", "")
    token = s.connect(path).execute("select current_health from player_medical").fetchone()[0]
    with pytest.raises(InvalidToken):
        Fernet(Fernet.generate_key()).decrypt(token.encode())


def test_medical_access_is_audited_including_denials(client, db, world):
    w = world
    client.put(f"/players/{w['ann']}/medical", json=MED, headers=w["h"]["physio_a"])
    client.get(f"/players/{w['ann']}/medical", headers=w["h"]["physio_a"])
    client.get(f"/players/{w['ann']}/medical", headers=w["h"]["coach_a"])           # denied
    acts = [(a.action, a.user_id) for a in db.query(AuditLog).filter(AuditLog.action.like("medical.%"))]
    assert ("medical.write", w["users"]["physio_a"].id) in acts
    assert ("medical.read", w["users"]["physio_a"].id) in acts
    assert ("medical.denied", w["users"]["coach_a"].id) in acts
    # the audit trail itself must not contain medical content
    assert not any("lower-back" in (a.detail or "") for a in db.query(AuditLog))


# ───────────── availability (the coach-safe summary) ─────────────
def test_availability_set_by_physio_visible_to_coach_and_player(client, world):
    w = world
    r = client.put(f"/players/{w['ann']}/availability", json={"availability": "modified", "availability_note": "No bowling this week"}, headers=w["h"]["physio_a"])
    assert r.status_code == 200
    for who in ("coach_a", "sc_a", "ann_login"):
        p = client.get(f"/players/{w['ann']}", headers=w["h"][who]).json()
        assert p["availability"] == "modified" and p["availability_note"] == "No bowling this week"


@pytest.mark.parametrize("who", ["coach_a", "sc_a", "admin", "ann_login"])
def test_only_physio_sets_availability(client, world, who):
    r = client.put(f"/players/{world['ann']}/availability", json={"availability": "unavailable"}, headers=world["h"][who])
    assert r.status_code in (403, 404)
