"""Initial Screening: schemas + the NEEDS ANALYSIS grid exactly as laid out in the workbook (G3:J30)."""
import json
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NEEDS_GRID: dict[str, list[str]] = {
    "Muscular strength": ["Upper body", "Lower", "Core"],
    "Muscular power": ["Upper body", "Lower body", "Core"],
    "Reactive strength": ["Lower body"],
    "Speed": ["Acceleration", "Maximum", "Repeat sprint ability"],
    "Energy systems": ["ATP-PC", "Anaerobic glycolysis", "Oxidative metabolism"],
}
LEVELS = ("LOW", "MOD", "HIGH")


class NeedIn(BaseModel):
    category: str
    item: str
    level: str

    @model_validator(mode="after")
    def _in_grid(self):
        if self.item not in NEEDS_GRID.get(self.category, []):
            raise ValueError(f"'{self.category} / {self.item}' is not an item of the needs-analysis grid")
        if self.level not in LEVELS:
            raise ValueError("level must be LOW, MOD or HIGH")
        return self


def _small(v):
    if v is not None and len(json.dumps(v)) > 10_000:
        raise ValueError("Value too large")
    return v


class ScreeningBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    years_playing_band: str | None = Field(default=None, max_length=30)
    start_age: int | None = Field(default=None, ge=3, le=16)
    achievement_levels: dict[str, Any] | None = None
    format_played_pct: dict[str, int] | None = None
    favourite_bowler_to_bat: str | None = Field(default=None, max_length=200)
    favourite_shot: str | None = Field(default=None, max_length=200)
    game_plan_tactic: str | None = None
    dismissal_types: dict[str, Any] | None = None
    strong_areas: dict[str, Any] | None = None
    dislike_areas: dict[str, Any] | None = None
    boundary_areas: dict[str, Any] | None = None
    last_year_review: dict[str, Any] | None = None
    this_year_objective: str | None = None
    life_ambition: str | None = None
    goal_setting_trials: dict[str, Any] | None = None
    yoyo_last_time: str | None = Field(default=None, max_length=30)
    two_km_last_time: str | None = Field(default=None, max_length=30)

    @field_validator("achievement_levels", "dismissal_types", "strong_areas", "dislike_areas", "boundary_areas",
                     "last_year_review", "goal_setting_trials")
    @classmethod
    def _cap(cls, v):
        return _small(v)

    @field_validator("format_played_pct")
    @classmethod
    def _pct(cls, v):
        if v is not None:
            if any(not 0 <= x <= 100 for x in v.values()) or sum(v.values()) > 100:
                raise ValueError("Format percentages must each be 0-100 and total at most 100")
        return v


class ScreeningIn(ScreeningBase):
    screening_date: date
    needs: list[NeedIn] = []

    @field_validator("needs")
    @classmethod
    def _no_dupes(cls, v):
        keys = [(n.category, n.item) for n in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate needs-analysis item")
        return v


class ScreeningUpdate(ScreeningBase):
    screening_date: date | None = None
    needs: list[NeedIn] | None = None


class NeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    category: str
    item: str
    level: str


class ScreeningOut(ScreeningBase):
    id: int
    player_id: int
    screening_date: date
    needs: list[NeedOut]
