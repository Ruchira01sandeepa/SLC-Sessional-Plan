from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..models import CalendarEvent, EventType, Season, SeasonPhase, SeasonPhaseType, User
from ..permissions import authorize_squad
from ..season_phases import suggest_phases

router = APIRouter(tags=["calendar"])


def _utc(dt: datetime) -> datetime:
    """Store everything in UTC. A naive datetime is taken as UTC (the UI always sends an offset)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# ───────────── schemas ─────────────
class PhaseIn(BaseModel):
    phase_type: SeasonPhaseType
    start_date: date
    end_date: date
    focus: str | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.end_date < self.start_date:
            raise ValueError("Phase end is before its start")
        return self


class PhaseOut(PhaseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


def check_phases(season_start: date, season_end: date, phases) -> None:
    """Phases must lie inside the season, must not overlap, and each phase type may appear once."""
    ph = sorted(phases, key=lambda p: p.start_date)
    for p in ph:
        if p.start_date < season_start or p.end_date > season_end:
            raise ValueError(f"Phase {p.phase_type.value} lies outside the season")
    for a, b in zip(ph, ph[1:]):
        if b.start_date <= a.end_date:
            raise ValueError(f"Phases {a.phase_type.value} and {b.phase_type.value} overlap")
    types = [p.phase_type for p in ph]
    if len(types) != len(set(types)):
        raise ValueError("Each phase type can be used once per season")


class SeasonIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    phases: list[PhaseIn] = []

    @model_validator(mode="after")
    def _valid(self):
        if self.end_date <= self.start_date:
            raise ValueError("Season end must be after its start")
        check_phases(self.start_date, self.end_date, self.phases)
        return self


class SeasonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    squad_id: int
    name: str
    start_date: date
    end_date: date
    phases: list[PhaseOut]


class EventIn(BaseModel):
    event_type: EventType
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime | None = None
    venue: str | None = Field(default=None, max_length=200)
    intensity_planned: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _tz(cls, v):
        return _utc(v) if v else v

    @model_validator(mode="after")
    def _order(self):
        if self.end_at and self.end_at <= self.start_at:
            raise ValueError("Event end must be after its start")
        return self


class EventUpdate(BaseModel):
    event_type: EventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    venue: str | None = None
    intensity_planned: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _tz(cls, v):
        return _utc(v) if v else v


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    squad_id: int
    event_type: EventType
    title: str
    start_at: datetime
    end_at: datetime | None
    venue: str | None
    intensity_planned: int | None
    notes: str | None


# ───────────── seasons ─────────────
@router.get("/squads/{squad_id}/seasons", response_model=list[SeasonOut])
def list_seasons(squad_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "calendar.read")
    return db.scalars(select(Season).where(Season.squad_id == squad_id).order_by(Season.start_date.desc())).all()


@router.post("/squads/{squad_id}/seasons", response_model=SeasonOut, status_code=201)
def create_season(squad_id: int, body: SeasonIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "calendar.write")
    for s in db.scalars(select(Season).where(Season.squad_id == squad_id)):
        if body.start_date <= s.end_date and body.end_date >= s.start_date:
            raise HTTPException(409, f"Overlaps the existing season '{s.name}'")
    season = Season(squad_id=squad_id, name=body.name, start_date=body.start_date, end_date=body.end_date)
    season.phases = [SeasonPhase(**p.model_dump()) for p in body.phases]
    db.add(season)
    db.flush()
    audit(db, user, "season.created", "season", season.id)
    db.commit()
    return season


@router.get("/season-phase-suggestion", response_model=list[PhaseIn])
def phase_suggestion(start_date: date, end_date: date, _: User = Depends(current_user)):
    """A default split into pre-season / pre-competition / in-season / transition. A starting point only."""
    try:
        return suggest_phases(start_date, end_date)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/seasons/{season_id}/phases", response_model=SeasonOut)
def set_phases(season_id: int, body: list[PhaseIn], db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Replace the phases of a season."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    authorize_squad(db, user, season.squad_id, "calendar.write")
    try:
        check_phases(season.start_date, season.end_date, body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    season.phases = [SeasonPhase(**p.model_dump()) for p in body]
    audit(db, user, "season.phases_set", "season", season.id, ",".join(p.phase_type.value for p in body))
    db.commit()
    return season


# ───────────── events ─────────────
@router.get("/squads/{squad_id}/events", response_model=list[EventOut])
def list_events(squad_id: int, start: datetime | None = Query(None, alias="from"), to: datetime | None = None,
                event_type: EventType | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "calendar.read")
    q = select(CalendarEvent).where(CalendarEvent.squad_id == squad_id).order_by(CalendarEvent.start_at)
    if start:
        q = q.where(CalendarEvent.start_at >= _utc(start))
    if to:
        q = q.where(CalendarEvent.start_at < _utc(to))
    if event_type:
        q = q.where(CalendarEvent.event_type == event_type)
    return db.scalars(q.limit(1000)).all()


@router.post("/squads/{squad_id}/events", response_model=EventOut, status_code=201)
def create_event(squad_id: int, body: EventIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "calendar.write")
    ev = CalendarEvent(squad_id=squad_id, **body.model_dump())
    db.add(ev)
    db.flush()
    audit(db, user, "event.created", "event", ev.id, ev.event_type.value)
    db.commit()
    return ev


def _event(db, user, event_id) -> CalendarEvent:
    ev = db.get(CalendarEvent, event_id)
    if ev is None:
        raise HTTPException(404, "Event not found")
    authorize_squad(db, user, ev.squad_id, "calendar.write")      # 404 if outside the user's squads
    return ev


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ev = _event(db, user, event_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ev, k, v)
    s, e = ev.start_at, ev.end_at
    if e is not None and (e.replace(tzinfo=None) <= s.replace(tzinfo=None)):
        raise HTTPException(422, "Event end must be after its start")
    audit(db, user, "event.updated", "event", ev.id)
    db.commit()
    return ev


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ev = _event(db, user, event_id)
    audit(db, user, "event.deleted", "event", ev.id, ev.title)
    db.delete(ev)
    db.commit()
