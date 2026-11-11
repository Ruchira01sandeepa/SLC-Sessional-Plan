import os
import tempfile

# Must be set BEFORE the app is imported (settings are read at import time).
_tmp = tempfile.mkdtemp()
os.environ["SLC_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SLC_JWT_SECRET"] = "test-secret-test-secret-test-secret!!"
os.environ["SLC_ENABLED_ROLES"] = "all"      # the app defaults to admin-only; most tests exercise every role

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Gender, Player, PlayerRole, Squad, SquadStaff, User, UserRole
from app.security import hash_password
from app.seed_templates import seed

import app.security as _sec
_sec._ph = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)   # fast hashing for tests only

PW = "Str0ngPassw0rd!"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    return TestClient(app)


def make_user(db, email, role, *, must_change=False, name=None):
    u = User(email=email, full_name=name or email.split("@")[0], role=role,
             password_hash=hash_password(PW), must_change_password=must_change)
    db.add(u)
    db.commit()
    return u


def login(client, email, password=PW):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def world(db, client):
    """Two squads, staff of every role, three players. Returns handy auth headers + ids.

        Squad A: coach_a, sc_a, physio_a      players: ann (spin, has login), bob (fast)
        Squad B: coach_b                      players: cara (batter)
    """
    sa, sb = Squad(name="Western U15", province="Western"), Squad(name="Central U15", province="Central")
    db.add_all([sa, sb])
    db.flush()
    users = {n: make_user(db, f"{n}@slc.lk", r) for n, r in [
        ("admin", UserRole.admin), ("coach_a", UserRole.coach), ("sc_a", UserRole.sc_coach),
        ("physio_a", UserRole.physio), ("coach_b", UserRole.coach), ("ann_login", UserRole.player),
        ("bob_login", UserRole.player)]}
    db.add_all([SquadStaff(user_id=users[n].id, squad_id=sa.id) for n in ("coach_a", "sc_a", "physio_a")])
    db.add(SquadStaff(user_id=users["coach_b"].id, squad_id=sb.id))

    def player(name, squad, role, login=None, dob="2012-06-01"):
        p = Player(full_name=name, squad_id=squad.id, role=role, gender=Gender.male,
                   date_of_birth=__import__("datetime").date.fromisoformat(dob),
                   user_id=users[login].id if login else None)
        db.add(p)
        db.flush()
        return p
    ann = player("Ann", sa, PlayerRole.spin_bowler, "ann_login")
    bob = player("Bob", sa, PlayerRole.fast_bowler, "bob_login")
    cara = player("Cara", sb, PlayerRole.batter)
    db.commit()
    h = {n: login(client, f"{n}@slc.lk") for n in users}
    return dict(h=h, squad_a=sa.id, squad_b=sb.id, ann=ann.id, bob=bob.id, cara=cara.id, users=users)


@pytest.fixture
def seeded(db):
    return seed(db)
