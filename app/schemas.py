from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import (Availability, Gender, MaturityStatus, PlayerRole, TemplateKind, UserRole)
from .age_groups import CODES as AGE_CODES, PROFILES as AGE_PROFILES
from .security import validate_password_strength


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v):
        validate_password_strength(v)
        return v


# Roles a person may ASK for. Administrator access is never self-service: an admin grants it on approval if needed.
SIGNUP_ROLES = (UserRole.coach, UserRole.sc_coach, UserRole.physio, UserRole.player)


class SignupIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(max_length=200)
    role: UserRole
    note: str | None = Field(default=None, max_length=300)

    @field_validator("full_name", "note")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("role")
    @classmethod
    def _requestable(cls, v):
        if v not in SIGNUP_ROLES:
            raise ValueError("Choose coach, S&C coach, physiotherapist or player")
        return v

    @field_validator("password")
    @classmethod
    def _strong(cls, v):
        validate_password_strength(v)
        return v


class AuthConfigOut(BaseModel):
    signup_enabled: bool
    signup_roles: list[UserRole]
    enabled_roles: list[UserRole]


class SignupRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    signup_note: str | None
    created_at: datetime
    role_can_sign_in: bool = True


class ApproveIn(BaseModel):
    role: UserRole | None = None          # None = keep the role the person asked for


# ---------- users / squads ----------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    language: str = Field(default="en", pattern="^(en|si|ta)$")
    temp_password: str

    @field_validator("temp_password")
    @classmethod
    def _strong(cls, v):
        validate_password_strength(v)
        return v


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    language: str | None = Field(default=None, pattern="^(en|si|ta)$")
    is_active: bool | None = None


class UserOut(ORM):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    language: str
    is_active: bool
    approval_status: str = "approved"

    @field_validator("approval_status", mode="before")
    @classmethod
    def _plain(cls, v):
        return getattr(v, "value", v)


class SquadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    province: str = Field(min_length=1, max_length=100)
    age_group: str = "U15"

    @field_validator("age_group")
    @classmethod
    def _known_age_group(cls, v: str):
        v = v.strip().upper()
        if v not in AGE_CODES:
            raise ValueError(f"age_group must be one of: {', '.join(AGE_CODES)}")
        return v


class SquadOut(ORM):
    id: int
    name: str
    province: str
    age_group: str


class StaffAssign(BaseModel):
    user_ids: list[int]


# ---------- players ----------
class PlayerCreate(BaseModel):
    squad_id: int
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date
    gender: Gender
    role: PlayerRole
    squad_no: int | None = None
    maturity_status: MaturityStatus = MaturityStatus.unknown
    vegetarian: bool | None = None
    other_sports: str | None = None
    category: list[str] | None = None
    school_or_club: str | None = None
    batting_hand: str | None = None
    bowling_arm: str | None = None
    front_side: str | None = None
    style: str | None = None
    guardian_name: str | None = None
    guardian_contact: str | None = None

    @field_validator("date_of_birth")
    @classmethod
    def _plausible_dob(cls, v: date):
        # Broad sanity check here (any supported age group); the exact range for the squad's age group is checked when the
        # squad is known (routers/players.py, age_groups.check_dob).
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        lo, hi = min(p.min_age for p in AGE_PROFILES.values()), max(p.max_age for p in AGE_PROFILES.values())
        if not lo <= age <= hi:
            raise ValueError(f"Date of birth is outside the plausible junior range ({lo}-{hi} years)")
        return v


class PlayerUpdate(BaseModel):
    full_name: str | None = None
    squad_id: int | None = None
    squad_no: int | None = None
    maturity_status: MaturityStatus | None = None
    role: PlayerRole | None = None
    vegetarian: bool | None = None
    other_sports: str | None = None
    category: list[str] | None = None
    school_or_club: str | None = None
    batting_hand: str | None = None
    bowling_arm: str | None = None
    front_side: str | None = None
    style: str | None = None
    guardian_name: str | None = None
    guardian_contact: str | None = None
    is_active: bool | None = None


class PlayerOut(ORM):
    """What players/coaches see. Medical DETAIL is never part of this model."""
    id: int
    squad_id: int
    squad_no: int | None
    full_name: str
    date_of_birth: date
    age: int
    gender: Gender
    maturity_status: MaturityStatus
    role: PlayerRole
    vegetarian: bool | None
    other_sports: str | None
    category: list[str] | None
    school_or_club: str | None
    batting_hand: str | None
    bowling_arm: str | None
    front_side: str | None
    style: str | None
    guardian_name: str | None
    guardian_contact: str | None
    is_active: bool
    availability: Availability
    availability_note: str | None


class AvailabilityIn(BaseModel):
    availability: Availability
    availability_note: str | None = Field(default=None, max_length=300)


class LinkUserIn(BaseModel):
    user_id: int | None


# ---------- medical (physio only) ----------
class InjuryHistory(BaseModel):
    has_history: bool | None = None
    notes: str | None = None
    first_injury_age: int | None = Field(default=None, ge=0, le=20)
    times_out_of_play: int | None = Field(default=None, ge=0)


class MedicalReports(BaseModel):
    ultrasound: str | None = None
    mri: str | None = None
    operations: str | None = None


class InjuredBodyParts(BaseModel):
    upper: str | None = None
    lower: str | None = None
    core: str | None = None
    other: str | None = None


class MedicalIn(BaseModel):
    current_health: str | None = None
    injury_history: InjuryHistory | None = None
    reports: MedicalReports | None = None
    injured_body_parts: InjuredBodyParts | None = None


class MedicalOut(BaseModel):
    player_id: int
    current_health: str | None = None
    injury_history: InjuryHistory | None = None
    reports: MedicalReports | None = None
    injured_body_parts: InjuredBodyParts | None = None
    updated_at: datetime | None = None


# ---------- reference data ----------
class SkillTemplateOut(ORM):
    id: int
    player_role: PlayerRole
    kind: TemplateKind
    group_name: str
    skill_name: str
    sort_order: int
    source_cell: str | None


class RubricOut(ORM):
    id: int
    group_name: str
    skill_name: str
    sort_order: int


class ScenarioOut(ORM):
    id: int
    player_role: PlayerRole
    title: str
    skill: str | None
    practice_activity: str | None
    technical: bool
    tactical: bool
    mental: bool
    physical: bool
