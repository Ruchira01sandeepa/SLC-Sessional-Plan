import datetime as dt

import openpyxl
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (FitnessTest, PdpRubricItem, PlayerRole, Scenario, SkillTemplate, TemplateKind, FitnessPhase)
from app.seed_templates import TEMPLATE_DIR, WORKBOOKS, seed, _s

DEV, ADP_P, ADP_S, PSK, PTK = (TemplateKind.development, TemplateKind.adaptability_primary,
                               TemplateKind.adaptability_secondary, TemplateKind.progress_skill, TemplateKind.progress_task)


def count(db, role, kind):
    return db.scalar(select(func.count()).select_from(SkillTemplate).where(SkillTemplate.player_role == role, SkillTemplate.kind == kind))


def test_seed_loads_every_role(db, seeded):
    assert db.scalar(select(func.count()).select_from(PdpRubricItem)) == 50          # 10 PDP groups x 5 skills
    assert db.scalar(select(func.count()).select_from(Scenario)) == 5                # one per role in the templates
    for role in PlayerRole:
        assert count(db, role, DEV) > 0 and count(db, role, ADP_P) > 0 and count(db, role, ADP_S) > 0, role


def test_seed_known_counts(db, seeded):
    assert count(db, PlayerRole.spin_bowler, DEV) == 22
    assert count(db, PlayerRole.batter, DEV) == 60            # includes the repeated "Range Hitting" blocks
    assert count(db, PlayerRole.batter, PSK) == 12            # batter progress sheet has its own layout
    assert count(db, PlayerRole.fast_bowler, PTK) == 18


def test_seed_is_idempotent(db, seeded):
    assert seed(db) == {"rubric": 0, "skills": 0, "scenarios": 0}


def test_spin_unlabelled_group_is_not_misfiled_under_tactical(db, seeded):
    rows = db.scalars(select(SkillTemplate).where(SkillTemplate.player_role == PlayerRole.spin_bowler,
                                                  SkillTemplate.kind == DEV, SkillTemplate.skill_name == "Field-setting plan")).all()
    assert rows[0].group_name == "Ungrouped"


def test_scenario_flags_follow_the_workbook(db, seeded):
    s = db.scalar(select(Scenario).where(Scenario.player_role == PlayerRole.fast_bowler))
    assert s.title == "Defend 10 runs in the final over"
    assert s.technical and s.tactical and s.mental and s.physical


def test_every_seeded_skill_points_at_the_right_cell_in_its_workbook(db, seeded):
    """The Excel export (Phase 5) writes by source_cell, so this must hold for ALL rows."""
    checked = 0
    for role, fname in WORKBOOKS.items():
        wb = openpyxl.load_workbook(TEMPLATE_DIR / fname, data_only=True)
        sheets = {
            DEV: [ws for ws in wb if "development" in ws.title.lower()][0],
            ADP_P: [ws for ws in wb if "adaptability" in ws.title.lower()][0],
            PSK: wb["Progress Status"], PTK: wb["Progress Status"],
        }
        sheets[ADP_S] = sheets[ADP_P]
        for t in db.scalars(select(SkillTemplate).where(SkillTemplate.player_role == role)):
            assert _s(sheets[t.kind][t.source_cell].value) == t.skill_name, (role, t.kind, t.source_cell)
            checked += 1
    assert checked > 250


def test_pdp_rubric_matches_workbook_layout(db, seeded):
    groups = [g for (g,) in db.execute(select(PdpRubricItem.group_name).distinct().order_by(PdpRubricItem.sort_order))]
    assert groups == ["Physical", "Nutrition", "Batting to Pace", "Batting to Spin", "Tactical - Batting",
                      "Pace Bowl", "Spin Bowl", "Tactical - Bowling", "Field", "Wk"]


def _season(db, squad_id):
    from app.models import Season
    s = Season(squad_id=squad_id, name="2026/27", start_date=dt.date(2026, 9, 1), end_date=dt.date(2027, 6, 30))
    db.add(s)
    db.commit()
    return s


def test_fitness_phases_coexist_but_each_only_once_per_season(db, world):
    s = _season(db, world["squad_a"])
    kw = dict(player_id=world["ann"], season_id=s.id, test_date=dt.date(2026, 9, 5))
    db.add_all([FitnessTest(**kw, phase=FitnessPhase.baseline, cmj_cm=31.5, sprint_20m_s=3.4, yoyo_level="15.3"),
                FitnessTest(**kw, phase=FitnessPhase.mid_season),
                FitnessTest(**kw, phase=FitnessPhase.end_season)])
    db.commit()
    db.add(FitnessTest(**kw, phase=FitnessPhase.baseline))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_fitness_requires_a_season(db, world):
    db.add(FitnessTest(player_id=world["ann"], phase=FitnessPhase.baseline, test_date=dt.date(2026, 9, 5)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_foreign_keys_are_enforced(db):
    from app.models import Player, Gender
    db.add(Player(full_name="Ghost", squad_id=9999, role=PlayerRole.batter, gender=Gender.male, date_of_birth=dt.date(2012, 1, 1)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_a_player_removes_their_medical_and_fitness_rows(db, world):
    from app.models import Player, PlayerMedical
    db.add(PlayerMedical(player_id=world["ann"], current_health={"text": "x"}))
    db.add(FitnessTest(player_id=world["ann"], season_id=_season(db, world["squad_a"]).id,
                       phase=FitnessPhase.baseline, test_date=dt.date(2026, 9, 5)))
    db.commit()
    db.delete(db.get(Player, world["ann"]))
    db.commit()
    assert db.scalar(select(func.count()).select_from(PlayerMedical)) == 0
    assert db.scalar(select(func.count()).select_from(FitnessTest)) == 0


def test_age_is_computed_from_dob(db, world):
    from app.models import Player
    p = db.get(Player, world["ann"])
    t = dt.date.today()
    assert p.age == t.year - 2012 - ((t.month, t.day) < (6, 1))


def test_placeholder_secrets_give_a_clear_error_not_a_crash_deep_in_the_app():
    import pytest as _p
    from pydantic import ValidationError
    from app.config import Settings
    with _p.raises(ValidationError, match="make_env"):
        Settings(medical_key="CHANGE-ME-fernet-key")
    with _p.raises(ValidationError, match="make_env"):
        Settings(jwt_secret="CHANGE-ME-long-random-string")
    Settings()      # defaults stay valid


def test_make_env_writes_a_loadable_env(tmp_path, monkeypatch):
    import runpy
    import pytest
    from app.config import Settings
    default_key = Settings().medical_key                      # captured BEFORE the new .env exists
    monkeypatch.chdir(tmp_path)
    runpy.run_module("scripts.make_env", run_name="__main__")
    lines = dict(l.split("=", 1) for l in (tmp_path / ".env").read_text().splitlines())
    assert len(lines["SLC_JWT_SECRET"]) >= 32 and lines["SLC_MEDICAL_KEY"] != default_key
    Settings(jwt_secret=lines["SLC_JWT_SECRET"], medical_key=lines["SLC_MEDICAL_KEY"])     # both accepted by validation
    with pytest.raises(SystemExit):
        runpy.run_module("scripts.make_env", run_name="__main__")                           # second run refuses to overwrite
