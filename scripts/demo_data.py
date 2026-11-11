"""Fill an EMPTY database with a demo squad so the UI has something to show.
DEMO ONLY: every account uses the password below. Never run this against real data.
    python -m scripts.demo_data
"""
import datetime as dt
import sys

from app.db import Base, SessionLocal, engine
from app import models as m
from app.security import hash_password
from app.seed_templates import seed

PW = "Demo-Pass-2026"


def run():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(m.User).count():
            sys.exit("Database is not empty - refusing to add demo data.")
        seed(db)
        mk = lambda email, name, role: db.add(u := m.User(email=email, full_name=name, role=role, password_hash=hash_password(PW),
                                                          must_change_password=False)) or u
        admin = mk("admin@demo.slc.lk", "Demo Admin", m.UserRole.admin)
        coach = mk("coach@demo.slc.lk", "Coach Perera", m.UserRole.coach)
        sc = mk("sc@demo.slc.lk", "S&C Coach Silva", m.UserRole.sc_coach)
        physio = mk("physio@demo.slc.lk", "Physio Fernando", m.UserRole.physio)
        pl = mk("kavindu@demo.slc.lk", "Kavindu Player", m.UserRole.player)
        sq = m.Squad(name="Western Province U15", province="Western")
        db.add(sq)
        db.flush()
        db.add_all(m.SquadStaff(user_id=x.id, squad_id=sq.id) for x in (coach, sc, physio))
        R = m.PlayerRole
        roster = [("Kavindu Silva", R.spin_bowler, 3, "Right", "Right", pl), ("Nimal Perera", R.fast_bowler, 5, "Right", "Right", None),
                  ("Sachith Jayawardena", R.batter, 2, "Left", "Right", None), ("Dilan Fernando", R.bat_wicketkeeper, 1, "Right", "Right", None),
                  ("Ravindu Bandara", R.all_rounder, 8, "Right", "Left", None), ("Tharindu Wickrama", R.fast_bowler, 11, "Right", "Right", None)]
        players = []
        for i, (n, role, no, bh, ba, login) in enumerate(roster):
            p = m.Player(full_name=n, role=role, squad_no=no, batting_hand=bh, bowling_arm=ba, squad_id=sq.id, gender=m.Gender.male,
                         date_of_birth=dt.date(2011 + (i % 2), 3 + i, 10 + i), user_id=login.id if login else None)
            db.add(p)
            players.append(p)
        s = m.Season(squad_id=sq.id, name="2026/27", start_date=dt.date(2026, 9, 1), end_date=dt.date(2027, 6, 30))
        s.phases = [m.SeasonPhase(phase_type=m.SeasonPhaseType.pre_season, start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 11, 30)),
                    m.SeasonPhase(phase_type=m.SeasonPhaseType.in_season, start_date=dt.date(2026, 12, 1), end_date=dt.date(2027, 4, 30))]
        db.add(s)
        db.flush()
        base = dict(bodyweight_kg=46, height_cm=157, cmj_cm=30, squat_jump_cm=28, sprint_5m_s=1.1, sprint_10m_s=1.9, sprint_20m_s=3.4,
                    yoyo_distance_m=1000, prone_plank_s=90, side_plank_front_s=45, side_plank_back_s=44, calf_raises_front_leg=25, calf_raises_back_leg=27)
        for i, p in enumerate(players):
            db.add(m.FitnessTest(player_id=p.id, season_id=s.id, phase=m.FitnessPhase.baseline, test_date=dt.date(2026, 9, 12),
                                 **{k: (v + (i - 2) * (0.04 if isinstance(v, float) and v < 5 else 1.2 if isinstance(v, float) else 20 if v > 500 else 2)) for k, v in base.items()}))
        # SLC U15 SOP test results (baseline, Super Provincial): demo numbers only
        for i, p in enumerate(players):
            ts = m.TestSession(player_id=p.id, season_id=s.id, window=m.FitnessPhase.baseline, level="super_provincial", test_date=dt.date(2026, 9, 12),
                               cleared=True, height_cm=150 + i * 2, weight_kg=40 + i, test_version="SOP v1", surface="Grass", timing_method="Stopwatch")
            for key, final in (("run_2km", 540 + (i * 37) % 120), ("broad_jump", 170 + ((i * 3) % 6) * 8), ("pushups", 12 + (i * 5) % 14),
                               ("inverted_row", 8 + (i * 3) % 9), ("sprint_20m", round(3.6 - ((i * 2) % 6) * 0.1, 2)),
                               ("shuttle_5_10_5", round(5.6 - ((i * 5) % 6) * 0.15, 2)), ("plank", 60 + ((i * 7) % 6) * 12)):
                ts.results.append(m.TestResult(test_key=key, trial_1=final, final_value=final))
            db.add(ts)
        now = dt.datetime(2026, 10, 24, 3, 30, tzinfo=dt.timezone.utc)
        for d, t, title, inten in [(0, m.EventType.training, "Nets: skills session", 6), (2, m.EventType.match, "Practice match vs Southern", 8),
                                   (3, m.EventType.rest, "Recovery day", 1), (7, m.EventType.fitness_test, "Mid-block fitness testing", 9)]:
            db.add(m.CalendarEvent(squad_id=sq.id, event_type=t, title=title, start_at=now + dt.timedelta(days=d), intensity_planned=inten))
        db.commit()
        print("Demo data ready. Logins (password %s):\n  admin@demo.slc.lk  coach@demo.slc.lk  sc@demo.slc.lk  physio@demo.slc.lk  kavindu@demo.slc.lk" % PW)


if __name__ == "__main__":
    run()
