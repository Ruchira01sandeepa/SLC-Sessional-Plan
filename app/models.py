"""Database schema.

Every table is traced back to a sheet of the PDP workbooks. See docs/DATA_MODEL.md for
the sheet -> table mapping.

Design decisions:
* One schema for all five roles. What differs between the role workbooks (the skill rows on
  the Development / Adaptability / Progress sheets, and the Scenario text) is DATA held in
  `skill_templates` and `scenarios`, not extra tables.
* Medical and injury data lives in its own table (`player_medical`) with encrypted columns.
* Fitness data is stored once per test phase (baseline / mid / end) so progress is a query.
"""
import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .security import EncryptedJSON


def _now():
    return datetime.now(timezone.utc)


def _enum(e):
    # store the enum *value* (readable, stable) rather than the Python member name
    return Enum(e, values_callable=lambda x: [m.value for m in x], native_enum=False, length=32)


# ───────────────────────────── enums ─────────────────────────────
class UserRole(str, enum.Enum):
    player = "player"
    coach = "coach"
    sc_coach = "sc_coach"        # strength & conditioning
    physio = "physio"            # physiotherapist / medical
    admin = "admin"


class PlayerRole(str, enum.Enum):
    fast_bowler = "fast_bowler"
    spin_bowler = "spin_bowler"
    batter = "batter"
    bat_wicketkeeper = "bat_wicketkeeper"
    all_rounder = "all_rounder"


class Gender(str, enum.Enum):
    male = "male"
    female = "female"


class MaturityStatus(str, enum.Enum):
    pre_phv = "pre_phv"
    circa_phv = "circa_phv"
    post_phv = "post_phv"
    unknown = "unknown"


class Availability(str, enum.Enum):
    """The only medical fact a coach sees: can the player train, and how."""
    fit = "fit"
    modified = "modified"        # train with restrictions
    unavailable = "unavailable"


class DevArea(str, enum.Enum):
    technical = "technical"
    tactical = "tactical"
    physical = "physical"
    mental = "mental"
    nutrition = "nutrition"
    recovery = "recovery"


class ProgressStatus(str, enum.Enum):
    """Workbook legend: ? / Naturally Good / Have to improve / Improving / Good / Complete."""
    no_clue = "no_clue"
    naturally_good = "naturally_good"
    have_to_improve = "have_to_improve"
    improving = "improving"
    good = "good"
    complete = "complete"


class GoalStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    achieved = "achieved"
    revised = "revised"
    dropped = "dropped"


class TemplateKind(str, enum.Enum):
    development = "development"          # "<Role> Development" sheet: skill grid
    adaptability_primary = "adaptability_primary"
    adaptability_secondary = "adaptability_secondary"
    progress_skill = "progress_skill"    # Progress Status: "Core ... Skills / Phases"
    progress_task = "progress_task"      # Progress Status: "Core ... Tasks"


class FitnessPhase(str, enum.Enum):
    baseline = "baseline"
    mid_season = "mid_season"
    end_season = "end_season"


class SeasonPhaseType(str, enum.Enum):
    pre_season = "pre_season"
    pre_competition = "pre_competition"
    in_season = "in_season"
    transition = "transition"


class EventType(str, enum.Enum):
    training = "training"
    match = "match"
    fitness_test = "fitness_test"
    rest = "rest"
    review = "review"
    camp = "camp"


class PlanLevel(str, enum.Enum):
    annual = "annual"
    seasonal = "seasonal"
    monthly = "monthly"
    weekly = "weekly"


class ApprovalStatus(str, enum.Enum):
    """Self sign-up: an account stays `pending` until an administrator approves or rejects it.
    Accounts created by an administrator are `approved` from the start."""
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ───────────────────────────── people & teams ─────────────────────────────
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole))
    language: Mapped[str] = mapped_column(String(2), default="en")  # en / si / ta
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    approval_status: Mapped[ApprovalStatus] = mapped_column(_enum(ApprovalStatus), default=ApprovalStatus.approved,
                                                            server_default=ApprovalStatus.approved.value)
    signup_note: Mapped[str | None] = mapped_column(String(300))     # what the person wrote when asking for access
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    squad_links: Mapped[list["SquadStaff"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Squad(Base):
    __tablename__ = "squads"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    province: Mapped[str] = mapped_column(String(100))
    age_group: Mapped[str] = mapped_column(String(10), default="U15")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    staff: Mapped[list["SquadStaff"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    players: Mapped[list["Player"]] = relationship(back_populates="squad")


class SquadStaff(Base):
    """Which staff member works with which squad. Drives 'coaches see only their squad'."""
    __tablename__ = "squad_staff"
    __table_args__ = (UniqueConstraint("user_id", "squad_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"), index=True)
    user: Mapped[User] = relationship(back_populates="squad_links")
    squad: Mapped[Squad] = relationship(back_populates="staff")


class Player(Base):
    """Workbook: Initial Screening > PLAYER PROFILE (+ the role fields on the other sheets)."""
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), index=True)
    squad_no: Mapped[int | None] = mapped_column(Integer)                      # "Player No" on Skill Analysis

    full_name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[date] = mapped_column(Date)                          # age is computed, never stored
    gender: Mapped[Gender] = mapped_column(_enum(Gender))
    maturity_status: Mapped[MaturityStatus] = mapped_column(_enum(MaturityStatus), default=MaturityStatus.unknown)
    role: Mapped[PlayerRole] = mapped_column(_enum(PlayerRole))

    vegetarian: Mapped[bool | None] = mapped_column(Boolean)
    other_sports: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[list | None] = mapped_column(JSON)                        # ["school","club","national"]
    school_or_club: Mapped[str | None] = mapped_column(String(200))

    batting_hand: Mapped[str | None] = mapped_column(String(10))               # Fitness Report: "Batting hand"
    bowling_arm: Mapped[str | None] = mapped_column(String(10))                # Fitness Report: "Bowling arm"
    front_side: Mapped[str | None] = mapped_column(String(10))                 # Fitness Report: "Front side"
    style: Mapped[str | None] = mapped_column(String(50))                      # SPIN/BOWLING/BATTING TYPE / KEEPING STYLE (A15)

    guardian_name: Mapped[str | None] = mapped_column(String(200))
    guardian_contact: Mapped[str | None] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only fact about health that coaches/players may see (details are in PlayerMedical).
    availability: Mapped[Availability] = mapped_column(_enum(Availability), default=Availability.fit)
    availability_note: Mapped[str | None] = mapped_column(String(300))        # coach-safe wording only
    # Coach-set bowling limits, e.g. {"max_spell_overs": 4}. Fast bowlers have defaults; others are unchecked until set.
    workload_limits: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    squad: Mapped[Squad] = relationship(back_populates="players")
    medical: Mapped["PlayerMedical | None"] = relationship(back_populates="player", uselist=False, cascade="all, delete-orphan")
    screenings: Mapped[list["Screening"]] = relationship(back_populates="player", cascade="all, delete-orphan")

    @property
    def age(self) -> int:
        t = date.today()
        d = self.date_of_birth
        return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


class PlayerMedical(Base):
    """Workbook: Initial Screening > PHYSICAL & INJURY STATUS. Encrypted; physio-only (see permissions.py)."""
    __tablename__ = "player_medical"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), unique=True)
    current_health: Mapped[dict | None] = mapped_column(EncryptedJSON)         # "CURRENT HEALTH – note"
    injury_history: Mapped[dict | None] = mapped_column(EncryptedJSON)         # history, first-injury age, times out, notes
    reports: Mapped[dict | None] = mapped_column(EncryptedJSON)                # doctor/physio: ultrasound, MRI, operations
    injured_body_parts: Mapped[dict | None] = mapped_column(EncryptedJSON)     # upper / lower / core / other
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    player: Mapped[Player] = relationship(back_populates="medical")


# ───────────────────────────── Initial Screening ─────────────────────────────
class Screening(Base):
    """Workbook: Initial Screening (non-medical part). One row per screening date."""
    __tablename__ = "screenings"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    screening_date: Mapped[date] = mapped_column(Date)                         # A41 DATE
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # RESEARCH OF PLAY (A19-A32); checkbox groups kept as JSON {"3day":true,...}
    years_playing_band: Mapped[str | None] = mapped_column(String(30))
    start_age: Mapped[int | None] = mapped_column(Integer)
    achievement_levels: Mapped[dict | None] = mapped_column(JSON)
    format_played_pct: Mapped[dict | None] = mapped_column(JSON)               # {"3day":..,"oneday":..,"t20":..,"test":..}
    favourite_bowler_to_bat: Mapped[str | None] = mapped_column(String(200))
    favourite_shot: Mapped[str | None] = mapped_column(String(200))
    game_plan_tactic: Mapped[str | None] = mapped_column(Text)
    dismissal_types: Mapped[dict | None] = mapped_column(JSON)
    strong_areas: Mapped[dict | None] = mapped_column(JSON)
    dislike_areas: Mapped[dict | None] = mapped_column(JSON)
    boundary_areas: Mapped[dict | None] = mapped_column(JSON)
    last_year_review: Mapped[dict | None] = mapped_column(JSON)                # matches, runs/wickets, 50/100, objective met?
    this_year_objective: Mapped[str | None] = mapped_column(Text)
    life_ambition: Mapped[str | None] = mapped_column(Text)
    goal_setting_trials: Mapped[dict | None] = mapped_column(JSON)            # Trial1..Trial5

    yoyo_last_time: Mapped[str | None] = mapped_column(String(30))            # A40
    two_km_last_time: Mapped[str | None] = mapped_column(String(30))          # C40

    player: Mapped[Player] = relationship(back_populates="screenings")
    needs: Mapped[list["NeedsAnalysisItem"]] = relationship(back_populates="screening", cascade="all, delete-orphan")


class NeedsAnalysisItem(Base):
    """Workbook: Initial Screening > NEEDS ANALYSIS (G3:J30): LOW / MOD / HIGH per physical-capacity item."""
    __tablename__ = "needs_analysis_items"
    __table_args__ = (UniqueConstraint("screening_id", "category", "item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    screening_id: Mapped[int] = mapped_column(ForeignKey("screenings.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60))    # e.g. "Muscular strength", "Speed", "Energy systems"
    item: Mapped[str] = mapped_column(String(60))        # e.g. "Upper body", "Acceleration", "ATP-PC"
    level: Mapped[str] = mapped_column(String(4))        # LOW / MOD / HIGH
    screening: Mapped[Screening] = relationship(back_populates="needs")


# ───────────────────────────── seasons, calendar, plans ─────────────────────────────
class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    phases: Mapped[list["SeasonPhase"]] = relationship(back_populates="season", cascade="all, delete-orphan")


class SeasonPhase(Base):
    __tablename__ = "season_phases"
    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    phase_type: Mapped[SeasonPhaseType] = mapped_column(_enum(SeasonPhaseType))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    focus: Mapped[str | None] = mapped_column(Text)
    season: Mapped[Season] = relationship(back_populates="phases")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[EventType] = mapped_column(_enum(EventType))
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(200))
    intensity_planned: Mapped[int | None] = mapped_column(Integer)             # 1-10
    notes: Mapped[str | None] = mapped_column(Text)


class PlanItem(Base):
    """Annual / seasonal / monthly / weekly plan rows and PDP goals.

    Every plan row carries the same fields (spec: development area, goal, dates, activities,
    responsible coach, measurement, target, status, coach review). `player_id` NULL = squad-level plan.
    """
    __tablename__ = "plan_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[PlanLevel] = mapped_column(_enum(PlanLevel))
    is_pdp_goal: Mapped[bool] = mapped_column(Boolean, default=False)         # PDP sheet goals "# 1 / # 2 / # 3"
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("plan_items.id", ondelete="SET NULL"))
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id", ondelete="SET NULL"))

    development_area: Mapped[DevArea] = mapped_column(_enum(DevArea))
    goal: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    planned_activities: Mapped[str | None] = mapped_column(Text)
    responsible_coach_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    measurement_method: Mapped[str | None] = mapped_column(Text)              # PDP "MEASURE" column
    target_outcome: Mapped[str | None] = mapped_column(Text)
    status: Mapped[GoalStatus] = mapped_column(_enum(GoalStatus), default=GoalStatus.not_started)
    coach_review: Mapped[str | None] = mapped_column(Text)
    phase_type: Mapped[str | None] = mapped_column(String(20))              # pre_season / pre_competition / in_season / transition
    applies_to: Mapped[str | None] = mapped_column(String(30))              # a player role, or NULL = all players
    responsible_label: Mapped[str | None] = mapped_column(String(300))      # staff names shown on the plan
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_plan_items_player_level", "player_id", "level"),)


# ───────────────────────────── PDP rating grid ─────────────────────────────
class PdpRubricItem(Base):
    """Workbook: PDP > Individual Rating Assessment rows (Physical/Nutrition/Batting to Pace/...)
    and the 5 sub-skills in each row (Speed, Endurance, ...). Same list for every role."""
    __tablename__ = "pdp_rubric_items"
    __table_args__ = (UniqueConstraint("group_name", "skill_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_name: Mapped[str] = mapped_column(String(80))      # e.g. "Physical", "Spin Bowl", "Wk"
    skill_name: Mapped[str] = mapped_column(String(120))     # e.g. "Speed"
    sort_order: Mapped[int] = mapped_column(Integer)


class PdpRating(Base):
    """A 1-5 rating (legend: 1-2 area to improve, 3 average, 4-5 strength) on a given assessment date."""
    __tablename__ = "pdp_ratings"
    __table_args__ = (UniqueConstraint("player_id", "rubric_item_id", "rated_on"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    rubric_item_id: Mapped[int] = mapped_column(ForeignKey("pdp_rubric_items.id"))
    rated_on: Mapped[date] = mapped_column(Date)
    rating: Mapped[int] = mapped_column(Integer)             # 1..5, enforced in schemas
    rated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ───────────────────────────── role skill templates & assessments ─────────────────────────────
class SkillTemplate(Base):
    """The skill rows that differ per role (Development / Adaptability / Progress Status sheets).
    Seeded from the workbooks by scripts/seed_templates.py so the app always matches the Excel."""
    __tablename__ = "skill_templates"
    # Unique by POSITION: the workbooks repeat skill names (e.g. two "Range Hitting" blocks in the batter sheet).
    __table_args__ = (UniqueConstraint("player_role", "kind", "sort_order"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_role: Mapped[PlayerRole] = mapped_column(_enum(PlayerRole), index=True)
    kind: Mapped[TemplateKind] = mapped_column(_enum(TemplateKind))
    source_cell: Mapped[str | None] = mapped_column(String(10))  # cell in the workbook sheet; used by the Excel export
    group_name: Mapped[str] = mapped_column(String(120))     # e.g. "Core Action", "Stock Delivery"
    skill_name: Mapped[str] = mapped_column(String(160))     # e.g. "Grip and finger position"
    sort_order: Mapped[int] = mapped_column(Integer)


class SkillAssessment(Base):
    """One symbol (?, Naturally Good, ... Complete) for one skill in one period.
    Covers the Development grid, Adaptability grid and Progress Status sheet."""
    __tablename__ = "skill_assessments"
    __table_args__ = (UniqueConstraint("player_id", "skill_template_id", "period_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    skill_template_id: Mapped[int] = mapped_column(ForeignKey("skill_templates.id"))
    period_start: Mapped[date] = mapped_column(Date)          # Monday of the week (or first of month)
    status: Mapped[ProgressStatus] = mapped_column(_enum(ProgressStatus))
    completed_balls: Mapped[int | None] = mapped_column(Integer)
    coach_note: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SkillAnalysis(Base):
    """Workbook: '<Role> Skill Analysis' sheet header + analysis text + remarks."""
    __tablename__ = "skill_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    complete_date: Mapped[date | None] = mapped_column(Date)
    style: Mapped[str | None] = mapped_column(String(50))
    analysis: Mapped[str | None] = mapped_column(Text)        # "Provide ... analysis"
    remarks: Mapped[str | None] = mapped_column(Text)
    monitored_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    perfection_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    micro_plan: Mapped[list["MicroPlanRow"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    media: Mapped[list["MediaEvidence"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class MicroPlanRow(Base):
    """'Work Description and Micro Plan': Monday..Friday x (quantity & quality, remedy)."""
    __tablename__ = "micro_plan_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("skill_analyses.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    weekday: Mapped[int] = mapped_column(Integer)             # 0=Mon .. 4=Fri
    quantity_quality: Mapped[str | None] = mapped_column(Text)
    remedy: Mapped[str | None] = mapped_column(Text)
    analysis: Mapped[SkillAnalysis] = relationship(back_populates="micro_plan")


class MediaEvidence(Base):
    """Image / video evidence (Skill Analysis 'Image evidence'). File lives in object storage; DB keeps the key."""
    __tablename__ = "media_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("skill_analyses.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(10))       # image / video
    caption: Mapped[str | None] = mapped_column(String(300))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    analysis: Mapped[SkillAnalysis] = relationship(back_populates="media")


class Scenario(Base):
    """Workbook: Scenario sheet. Role-specific match situation + practice activity + T/T/M/P flags."""
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_role: Mapped[PlayerRole] = mapped_column(_enum(PlayerRole), index=True)
    title: Mapped[str] = mapped_column(String(300))           # SCENARIO / TACTIC-METHOD
    skill: Mapped[str | None] = mapped_column(String(300))
    practice_activity: Mapped[str | None] = mapped_column(Text)
    technical: Mapped[bool] = mapped_column(Boolean, default=False)
    tactical: Mapped[bool] = mapped_column(Boolean, default=False)
    mental: Mapped[bool] = mapped_column(Boolean, default=False)
    physical: Mapped[bool] = mapped_column(Boolean, default=False)


# ───────────────────────────── Fitness Report ─────────────────────────────
class FitnessTest(Base):
    """Workbook: Fitness Report row. One per player per test phase (baseline / mid / end)."""
    __tablename__ = "fitness_tests"
    __table_args__ = (UniqueConstraint("player_id", "season_id", "phase"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))   # required: one test per player/season/phase
    phase: Mapped[FitnessPhase] = mapped_column(_enum(FitnessPhase))
    test_date: Mapped[date] = mapped_column(Date)

    bodyweight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    cmj_cm: Mapped[float | None] = mapped_column(Float)
    squat_jump_cm: Mapped[float | None] = mapped_column(Float)
    sprint_5m_s: Mapped[float | None] = mapped_column(Float)
    sprint_10m_s: Mapped[float | None] = mapped_column(Float)
    sprint_20m_s: Mapped[float | None] = mapped_column(Float)
    yoyo_level: Mapped[str | None] = mapped_column(String(10))                 # "15.3" (level.shuttle)
    yoyo_distance_m: Mapped[int | None] = mapped_column(Integer)
    prone_plank_s: Mapped[float | None] = mapped_column(Float)
    side_plank_front_s: Mapped[float | None] = mapped_column(Float)
    side_plank_back_s: Mapped[float | None] = mapped_column(Float)
    calf_raises_front_leg: Mapped[int | None] = mapped_column(Integer)
    calf_raises_back_leg: Mapped[int | None] = mapped_column(Integer)
    role_specific: Mapped[dict | None] = mapped_column(JSON)                   # role-specific cricket tests
    tested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ───────────────────────────── SLC national U15 testing battery ─────────────────────────────
class TestImportBatch(Base):
    """One Excel upload of SOP test results. Kept as an audit trail (who, when, what was accepted and rejected)."""
    __tablename__ = "test_import_batches"
    __test__ = False                                            # not a pytest class
    id: Mapped[int] = mapped_column(primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    window: Mapped[FitnessPhase] = mapped_column(_enum(FitnessPhase))
    filename: Mapped[str | None] = mapped_column(String(200))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rows_ok: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)


class TestSession(Base):
    """One player's SOP testing in one season window (baseline / mid / end). The level decides which tests apply."""
    __tablename__ = "test_sessions"
    __test__ = False
    __table_args__ = (UniqueConstraint("player_id", "season_id", "window"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    window: Mapped[FitnessPhase] = mapped_column(_enum(FitnessPhase))
    level: Mapped[str] = mapped_column(String(20))                 # provincial | super_provincial
    test_date: Mapped[date | None] = mapped_column(Date)
    cleared: Mapped[bool] = mapped_column(Boolean, default=True)    # medical clearance given before testing (yes/no only, no detail)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    test_version: Mapped[str | None] = mapped_column(String(40))
    surface: Mapped[str | None] = mapped_column(String(80))
    timing_method: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(String(300))
    tested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("test_import_batches.id", ondelete="SET NULL"))
    results: Mapped[list["TestResult"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="TestResult.id")


class TestResult(Base):
    """One test inside a session: all three trials are kept, final_value is the best valid one (seconds for mm.ss tests)."""
    __tablename__ = "test_results"
    __test__ = False
    __table_args__ = (UniqueConstraint("session_id", "test_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True)
    test_key: Mapped[str] = mapped_column(String(30))
    trial_1: Mapped[float | None] = mapped_column(Float)
    trial_2: Mapped[float | None] = mapped_column(Float)
    trial_3: Mapped[float | None] = mapped_column(Float)
    final_value: Mapped[float | None] = mapped_column(Float)
    setup: Mapped[str | None] = mapped_column(String(200))         # push-up / inverted-row set-up, as the SOP asks
    session: Mapped[TestSession] = relationship(back_populates="results")


class FitnessBenchmark(Base):
    """Coach-defined benchmark / individual target for a test field. NOT adult standards (spec)."""
    __tablename__ = "fitness_benchmarks"
    id: Mapped[int] = mapped_column(primary_key=True)
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    field_name: Mapped[str] = mapped_column(String(40))       # a FitnessTest column name
    target_value: Mapped[float] = mapped_column(Float)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    set_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(300))


# ───────────────────────────── workload & wellness (engine built in Phase 3) ─────────────────────────────
class WorkloadLog(Base):
    __tablename__ = "workload_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_events.id", ondelete="SET NULL"))
    log_date: Mapped[date] = mapped_column(Date, index=True)
    session_type: Mapped[EventType] = mapped_column(_enum(EventType))
    attended: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    session_intensity: Mapped[int | None] = mapped_column(Integer)             # coach-planned 1-10
    rpe: Mapped[int | None] = mapped_column(Integer)                           # player-reported 1-10
    balls_bowled: Mapped[int | None] = mapped_column(Integer)
    overs_bowled: Mapped[float | None] = mapped_column(Float)
    spells: Mapped[list | None] = mapped_column(JSON)                          # [{"overs":4,"minutes":22}, ...]
    balls_faced: Mapped[int | None] = mapped_column(Integer)
    keeping_minutes: Mapped[int | None] = mapped_column(Integer)
    throws: Mapped[int | None] = mapped_column(Integer)
    match_participation: Mapped[str | None] = mapped_column(String(30))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WellnessLog(Base):
    """Soreness / pain / fatigue / sleep / recovery self-report. Free-text pain details stay out of
    this table (they belong to physio); only numeric flags are stored here so coaches can act on them."""
    __tablename__ = "wellness_logs"
    __table_args__ = (UniqueConstraint("player_id", "log_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    log_date: Mapped[date] = mapped_column(Date)
    soreness: Mapped[int | None] = mapped_column(Integer)                      # 1-10
    fatigue: Mapped[int | None] = mapped_column(Integer)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    recovery: Mapped[int | None] = mapped_column(Integer)
    pain_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    pain_detail: Mapped[dict | None] = mapped_column(EncryptedJSON)           # location/severity - encrypted


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rule_code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(10))                          # info / warn / stop
    message: Mapped[str] = mapped_column(Text)
    ref_date: Mapped[date | None] = mapped_column(Date)                        # the day an event-type alert is about
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # condition no longer true
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ───────────────────────────── audit ─────────────────────────────
class AuditLog(Base):
    """Who touched what. Every read/write of medical data and every login event is recorded."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(300))


# ───────────────────────────── saved individual plans and their progress ─────────────────────────────
class IndividualPlanVersion(Base):
    """A saved version of one player's individual plan (generated, then edited by a coach). The newest version is the plan in use."""
    __tablename__ = "individual_plan_versions"
    __table_args__ = (UniqueConstraint("player_id", "season_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    window: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)                  # the full plan as saved (dates as ISO text)
    edits: Mapped[list | None] = mapped_column(JSON)          # the coach's edits on top of the base, for the audit trail
    based_on: Mapped[str] = mapped_column(String(20))         # "generated" or "version N"
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlanExerciseLog(Base):
    """One exercise done in one focus session: what was done and how it went. Drives the automatic progression."""
    __tablename__ = "plan_exercise_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    plan_version_id: Mapped[int | None] = mapped_column(ForeignKey("individual_plan_versions.id", ondelete="SET NULL"))
    log_date: Mapped[date] = mapped_column(Date, index=True)
    phase: Mapped[str] = mapped_column(String(20))
    area: Mapped[str] = mapped_column(String(30))
    exercise: Mapped[str] = mapped_column(String(200))
    sets_done: Mapped[int | None] = mapped_column(Integer)
    reps_done: Mapped[int | None] = mapped_column(Integer)
    technique_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    pain: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(300))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
