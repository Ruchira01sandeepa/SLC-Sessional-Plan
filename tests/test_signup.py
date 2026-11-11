"""Self sign-up with administrator approval."""
from app.config import settings
from app.models import ApprovalStatus, AuditLog, User, UserRole
from .conftest import PW, login, make_user

NEW = {"full_name": "Kasun Perera", "email": "Kasun@slc.lk", "password": "N3wCoachPassword", "role": "coach", "note": "Western U15 head coach"}


def _signup(client, **over):
    return client.post("/auth/signup", json={**NEW, **over})


def _admin(client, db):
    make_user(db, "admin@slc.lk", UserRole.admin)
    return login(client, "admin@slc.lk")


def test_config_is_public(client):
    r = client.get("/auth/config")
    assert r.status_code == 200
    body = r.json()
    assert body["signup_enabled"] is True and "admin" not in body["signup_roles"]


def test_signup_creates_pending_account_that_cannot_sign_in(client, db):
    r = _signup(client)
    assert r.status_code == 202
    u = db.query(User).filter_by(email="kasun@slc.lk").one()
    assert u.approval_status == ApprovalStatus.pending and u.role == UserRole.coach and not u.must_change_password
    assert u.signup_note == "Western U15 head coach"
    ok_pw = client.post("/auth/login", json={"email": "kasun@slc.lk", "password": NEW["password"]})
    assert ok_pw.status_code == 403 and ok_pw.json()["detail"] == "account_pending"
    # a wrong password must not reveal that the account exists or is pending
    bad_pw = client.post("/auth/login", json={"email": "kasun@slc.lk", "password": "WrongPassw0rd!"})
    unknown = client.post("/auth/login", json={"email": "nobody@slc.lk", "password": "WrongPassw0rd!"})
    assert bad_pw.status_code == unknown.status_code == 401 and bad_pw.json() == unknown.json()


def test_duplicate_email_gets_the_same_answer_and_changes_nothing(client, db):
    make_user(db, "kasun@slc.lk", UserRole.physio)
    first_hash = db.query(User).filter_by(email="kasun@slc.lk").one().password_hash
    r = _signup(client)
    fresh = _signup(client, email="someone.else@slc.lk")
    assert r.status_code == fresh.status_code == 202 and r.json() == fresh.json()
    db.expire_all()
    u = db.query(User).filter_by(email="kasun@slc.lk").one()
    assert u.role == UserRole.physio and u.password_hash == first_hash
    assert db.query(AuditLog).filter_by(action="signup.duplicate").count() == 1


def test_signup_validation(client):
    assert _signup(client, role="admin").status_code == 422             # admin access is never self-service
    assert _signup(client, password="weakpassword").status_code == 422
    assert _signup(client, full_name=" ").status_code == 422
    assert _signup(client, email="not-an-email").status_code == 422
    assert _signup(client, note="x" * 301).status_code == 422


def test_signup_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    assert _signup(client).status_code == 404
    assert client.get("/auth/config").json()["signup_enabled"] is False


def test_pending_cap(client, db, monkeypatch):
    monkeypatch.setattr(settings, "max_pending_signups", 1)
    assert _signup(client).status_code == 202
    assert _signup(client, email="second@slc.lk").status_code == 503


def test_admin_approves_with_a_different_role_then_user_signs_in(client, db):
    h = _admin(client, db)
    _signup(client)
    reqs = client.get("/admin/signup-requests", headers=h).json()
    assert [r["email"] for r in reqs] == ["kasun@slc.lk"] and reqs[0]["role_can_sign_in"] is True
    assert "kasun@slc.lk" not in [u["email"] for u in client.get("/admin/users", headers=h).json()]
    r = client.post(f"/admin/signup-requests/{reqs[0]['id']}/approve", headers=h, json={"role": "sc_coach"})
    assert r.status_code == 200 and r.json()["role"] == "sc_coach" and r.json()["approval_status"] == "approved"
    assert client.get("/admin/signup-requests", headers=h).json() == []
    me = client.get("/auth/me", headers=login(client, "kasun@slc.lk", NEW["password"])).json()
    assert me["role"] == "sc_coach"
    u = db.query(User).filter_by(email="kasun@slc.lk").one()
    assert u.reviewed_by is not None and u.reviewed_at is not None
    # approving twice is not possible
    assert client.post(f"/admin/signup-requests/{u.id}/approve", headers=h, json={}).status_code == 404


def test_rejected_account_looks_like_a_wrong_password(client, db):
    h = _admin(client, db)
    _signup(client)
    uid = client.get("/admin/signup-requests", headers=h).json()[0]["id"]
    assert client.post(f"/admin/signup-requests/{uid}/reject", headers=h).status_code == 204
    r = client.post("/auth/login", json={"email": "kasun@slc.lk", "password": NEW["password"]})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password"
    listed = {u["email"]: u for u in client.get("/admin/users", headers=h).json()}
    assert listed["kasun@slc.lk"]["approval_status"] == "rejected"
    # an administrator can still change their mind
    assert client.post(f"/admin/signup-requests/{uid}/approve", headers=h, json={"role": None}).status_code == 200
    assert client.post("/auth/login", json={"email": "kasun@slc.lk", "password": NEW["password"]}).status_code == 200


def test_only_admins_review_requests(client, db):
    make_user(db, "coach@slc.lk", UserRole.coach)
    h = login(client, "coach@slc.lk")
    _signup(client)
    uid = db.query(User).filter_by(email="kasun@slc.lk").one().id
    assert client.get("/admin/signup-requests", headers=h).status_code == 403
    assert client.post(f"/admin/signup-requests/{uid}/approve", headers=h, json={}).status_code == 403
    assert client.post(f"/admin/signup-requests/{uid}/reject", headers=h).status_code == 403


def test_pending_user_cannot_be_squad_staff(client, db):
    h = _admin(client, db)
    sq = client.post("/admin/squads", headers=h, json={"name": "Western U15", "province": "Western"}).json()
    _signup(client)
    uid = db.query(User).filter_by(email="kasun@slc.lk").one().id
    assert client.put(f"/admin/squads/{sq['id']}/staff", headers=h, json={"user_ids": [uid]}).status_code == 400


def test_token_stops_working_if_account_is_set_back_to_pending(client, db):
    u = make_user(db, "a@slc.lk", UserRole.coach)
    h = login(client, "a@slc.lk", PW)
    u.approval_status = ApprovalStatus.pending
    db.commit()
    assert client.get("/auth/me", headers=h).status_code == 401
