from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.models import AuditLog, User, UserRole
from .conftest import PW, login, make_user


def test_login_ok_and_me(client, db):
    make_user(db, "a@slc.lk", UserRole.coach)
    h = login(client, "a@slc.lk")
    assert client.get("/auth/me", headers=h).json()["email"] == "a@slc.lk"


def test_email_is_case_insensitive(client, db):
    make_user(db, "a@slc.lk", UserRole.coach)
    assert client.post("/auth/login", json={"email": "A@SLC.lk", "password": PW}).status_code == 200


def test_unauthenticated_and_garbage_token_rejected(client):
    assert client.get("/players").status_code == 401
    assert client.get("/players", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_wrong_password_and_unknown_email_look_identical(client, db):
    make_user(db, "a@slc.lk", UserRole.coach)
    r1 = client.post("/auth/login", json={"email": "a@slc.lk", "password": "WrongPassw0rd!"})
    r2 = client.post("/auth/login", json={"email": "nobody@slc.lk", "password": "WrongPassw0rd!"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()


def test_lockout_after_repeated_failures_even_with_correct_password(client, db):
    make_user(db, "a@slc.lk", UserRole.coach)
    for _ in range(settings.max_failed_logins):
        client.post("/auth/login", json={"email": "a@slc.lk", "password": "WrongPassw0rd!"})
    assert client.post("/auth/login", json={"email": "a@slc.lk", "password": PW}).status_code == 401
    assert db.query(AuditLog).filter_by(action="login.locked").count() == 1


def test_lockout_expires(client, db):
    u = make_user(db, "a@slc.lk", UserRole.coach)
    u.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.post("/auth/login", json={"email": "a@slc.lk", "password": PW}).status_code == 200


def test_first_login_forces_password_change(client, db):
    make_user(db, "new@slc.lk", UserRole.coach, must_change=True)
    h = login(client, "new@slc.lk")
    assert client.get("/players", headers=h).status_code == 403          # blocked
    assert client.get("/players", headers=h).json()["detail"] == "password_change_required"
    assert client.get("/auth/me", headers=h).status_code == 200          # still allowed
    r = client.post("/auth/change-password", headers=h, json={"current_password": PW, "new_password": "Br4ndNewPassword"})
    assert r.status_code == 204
    assert client.get("/players", headers=h).status_code == 200


def test_password_rules(client, db):
    make_user(db, "a@slc.lk", UserRole.coach)
    h = login(client, "a@slc.lk")
    for bad in ["short1A", "alllowercase123", "ALLUPPERCASE123", "NoDigitsHereAtAll"]:
        r = client.post("/auth/change-password", headers=h, json={"current_password": PW, "new_password": bad})
        assert r.status_code == 422, bad
    r = client.post("/auth/change-password", headers=h, json={"current_password": "Wr0ngCurrentPw", "new_password": "Br4ndNewPassword"})
    assert r.status_code == 400
    r = client.post("/auth/change-password", headers=h, json={"current_password": PW, "new_password": PW})
    assert r.status_code == 400


def test_deactivated_user_loses_access_immediately(client, db):
    u = make_user(db, "a@slc.lk", UserRole.coach)
    h = login(client, "a@slc.lk")
    u.is_active = False
    db.commit()
    assert client.get("/players", headers=h).status_code == 401


def test_role_change_invalidates_old_token(client, db):
    u = make_user(db, "a@slc.lk", UserRole.coach)
    h = login(client, "a@slc.lk")
    u.role = UserRole.physio
    db.commit()
    assert client.get("/players", headers=h).status_code == 401


def test_expired_and_forged_tokens_rejected(client, db):
    u = make_user(db, "a@slc.lk", UserRole.admin)
    now = datetime.now(timezone.utc)
    base = {"sub": str(u.id), "role": "admin", "iat": now}
    expired = jwt.encode({**base, "exp": now - timedelta(minutes=1)}, settings.jwt_secret, algorithm="HS256")
    forged = jwt.encode({**base, "exp": now + timedelta(hours=1)}, "attacker-key-attacker-key-attacker!!", algorithm="HS256")
    none_alg = jwt.encode({**base, "exp": now + timedelta(hours=1)}, key=None, algorithm="none")
    for t in (expired, forged, none_alg):
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401
