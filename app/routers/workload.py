from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import workload_rules as wr
from ..db import get_db
from ..deps import audit, current_user, require
from ..models import Alert, CalendarEvent, EventType, Player, User, WellnessLog, WorkloadLog
from ..permissions import authorize_player, authorize_squad, role_allows
from ..workload_service import current_phase, evaluate_player, evaluate_players, sync_alerts, to_log, today_lk
from ..age_groups import PROFILES as AGE_PROFILES, profile as age_profile

router = APIRouter(tags=["workload"])


# ───────────── schemas ─────────────
class SpellIn(BaseModel):
    overs: float = Field(gt=0, le=20)
    minutes: int | None = Field(default=None, ge=1, le=120)


class WorkloadIn(BaseModel):
    log_date: date
    session_type: EventType = EventType.training
    attended: bool = True
    duration_min: int | None = Field(default=None, ge=1, le=480)
    session_intensity: int | None = Field(default=None, ge=1, le=10)
    rpe: int | None = Field(default=None, ge=1, le=10)
    balls_bowled: int | None = Field(default=None, ge=0, le=300)
    overs_bowled: float | None = Field(default=None, ge=0, le=50)
    spells: list[SpellIn] | None = Field(default=None, max_length=20)
    balls_faced: int | None = Field(default=None, ge=0, le=600)
    keeping_minutes: int | None = Field(default=None, ge=0, le=480)
    throws: int | None = Field(default=None, ge=0, le=300)
    match_participation: str | None = Field(default=None, max_length=30)
    event_id: int | None = None

    @model_validator(mode="after")
    def _consistent(self):
        measures = (self.duration_min, self.session_intensity, self.rpe, self.balls_bowled, self.overs_bowled, self.spells,
                    self.balls_faced, self.keeping_minutes, self.throws)
        if not self.attended and any(m not in (None, [], 0) for m in measures):
            raise ValueError("A session the player did not attend cannot have load or bowling figures")
        balls = None
        if self.overs_bowled is not None:
            try:
                balls = wr.overs_to_balls(self.overs_bowled)
            except ValueError as e:
                raise ValueError(str(e))
        if balls is not None and self.balls_bowled is not None and balls != self.balls_bowled:
            raise ValueError(f"{self.overs_bowled:g} overs is {balls} balls, but balls bowled says {self.balls_bowled}")
        total = balls if balls is not None else self.balls_bowled
        if self.spells:
            try:
                spell_balls = sum(wr.overs_to_balls(s.overs) for s in self.spells)
            except ValueError as e:
                raise ValueError(str(e))
            if total is not None and spell_balls > total:
                raise ValueError("The spells add up to more than the overs bowled")
        if total is not None:                                   # store both forms so reports never disagree
            self.balls_bowled, self.overs_bowled = total, wr.balls_to_overs(total)
        return self


class WorkloadPatch(BaseModel):
    """Same fields, all optional. The merged record is validated again as a whole."""
    model_config = ConfigDict(extra="forbid")
    log_date: date | None = None
    session_type: EventType | None = None
    attended: bool | None = None
    duration_min: int | None = Field(default=None, ge=1, le=480)
    session_intensity: int | None = Field(default=None, ge=1, le=10)
    rpe: int | None = Field(default=None, ge=1, le=10)
    balls_bowled: int | None = Field(default=None, ge=0, le=300)
    overs_bowled: float | None = Field(default=None, ge=0, le=50)
    spells: list[SpellIn] | None = Field(default=None, max_length=20)
    balls_faced: int | None = Field(default=None, ge=0, le=600)
    keeping_minutes: int | None = Field(default=None, ge=0, le=480)
    throws: int | None = Field(default=None, ge=0, le=300)
    match_participation: str | None = Field(default=None, max_length=30)


class WorkloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    player_id: int
    event_id: int | None
    log_date: date
    session_type: EventType
    attended: bool
    duration_min: int | None
    session_intensity: int | None
    rpe: int | None
    balls_bowled: int | None
    overs_bowled: float | None
    spells: list | None
    balls_faced: int | None
    keeping_minutes: int | None
    throws: int | None
    match_participation: str | None
    load: float | None = None
    load_basis: str | None = None


class WellnessIn(BaseModel):
    log_date: date
    soreness: int | None = Field(default=None, ge=1, le=10)        # 10 = worst
    fatigue: int | None = Field(default=None, ge=1, le=10)         # 10 = worst
    sleep_quality: int | None = Field(default=None, ge=1, le=10)   # 10 = best
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    recovery: int | None = Field(default=None, ge=1, le=10)        # 10 = best
    pain_flag: bool = False


class WellnessOut(WellnessIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LimitsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_spell_overs: int | None = Field(default=None, ge=1, le=20)
    max_match_day_overs: int | None = Field(default=None, ge=1, le=30)
    max_bowling_days_week: int | None = Field(default=None, ge=1, le=7)


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    player_id: int
    player_name: str | None = None
    created_at: datetime
    rule_code: str
    severity: str
    message: str
    ref_date: date | None
    resolved_at: datetime | None
    acknowledged_by: int | None
    acknowledged_at: datetime | None


def _out(r: WorkloadLog) -> WorkloadOut:
    o = WorkloadOut.model_validate(r)
    o.load, o.load_basis = wr.session_load(to_log(r))
    return o


def _player(db: Session, user: User, pid: int, action: str) -> Player:
    return authorize_player(db, user, db.get(Player, pid), action)


def _check_event(db: Session, player: Player, event_id: int | None) -> None:
    if event_id is not None:
        ev = db.get(CalendarEvent, event_id)
        if ev is None or ev.squad_id != player.squad_id:
            raise HTTPException(422, "That calendar event does not belong to this player's squad")


def _alert_out(a: Alert, name: str | None = None) -> AlertOut:
    o = AlertOut.model_validate(a)
    o.player_name = name
    return o


def _can_see_alerts(user: User) -> bool:
    return role_allows(user, "alerts.read")


# ───────────── rules (for the screen and for audit) ─────────────
@router.get("/workload/rules")
def rules(age_group: str = "U15", user: User = Depends(current_user)):
    prof = age_profile(age_group)
    return {
        "age_group": prof.code,
        "fast_bowler_defaults": dict(prof.fast_limits),
        "fast_bowler_defaults_by_age_group": {c: dict(p.fast_limits) for c, p in AGE_PROFILES.items()},
        "thresholds": {"acwr_warn": wr.ACWR_WARN, "acwr_info": wr.ACWR_INFO, "acwr_min_history_days": wr.ACWR_MIN_HISTORY_DAYS,
                       "week_rise_warn_pct": int(wr.WEEK_RISE_WARN * 100), "monotony_info": wr.MONOTONY_INFO,
                       "wellness_high": wr.WELLNESS_HIGH, "sleep_low_hours": wr.SLEEP_LOW_HOURS},
        "notes": [
            *prof.notes,
            "Spin bowlers, all-rounders, batters and keepers have no automatic bowling limits. A coach can set limits for a player.",
            "Load is RPE x minutes. The ratio and week-on-week thresholds are rules of thumb, not proven safe or unsafe cut-offs for children.",
            "Alerts start a conversation with the coach and physiotherapist. They are not a diagnosis.",
        ],
    }


# ───────────── session logs ─────────────
@router.post("/players/{player_id}/workload", status_code=201)
def add_log(player_id: int, body: WorkloadIn, db: Session = Depends(get_db), user: User = Depends(require("workload.write"))):
    player = _player(db, user, player_id, "workload.write")
    if body.log_date > today_lk():
        raise HTTPException(422, "A session log cannot be dated in the future")
    _check_event(db, player, body.event_id)
    row = WorkloadLog(player_id=player.id, recorded_by=user.id,
                      **{**body.model_dump(exclude={"spells"}), "spells": [s.model_dump(exclude_none=True) for s in body.spells] if body.spells else None})
    db.add(row)
    db.flush()
    audit(db, user, "workload.created", "workload_log", row.id)
    alerts = sync_alerts(db, player)
    db.commit()
    return {"log": _out(row), "open_alerts": [_alert_out(a) for a in alerts] if _can_see_alerts(user) else None}


@router.get("/players/{player_id}/workload", response_model=list[WorkloadOut])
def list_logs(player_id: int, date_from: date | None = None, date_to: date | None = None,
              db: Session = Depends(get_db), user: User = Depends(require("workload.read"))):
    player = _player(db, user, player_id, "workload.read")
    end = date_to or today_lk()
    start = date_from or end - timedelta(days=27)
    rows = db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == player.id, WorkloadLog.log_date >= start, WorkloadLog.log_date <= end)
                      .order_by(WorkloadLog.log_date.desc(), WorkloadLog.id.desc())).all()
    return [_out(r) for r in rows]


@router.patch("/workload/{log_id}")
def edit_log(log_id: int, body: WorkloadPatch, db: Session = Depends(get_db), user: User = Depends(require("workload.write"))):
    row = db.get(WorkloadLog, log_id)
    player = _player(db, user, row.player_id, "workload.write") if row else _player(db, user, -1, "workload.write")
    merged = {k: getattr(row, k) for k in WorkloadIn.model_fields if k != "event_id" and hasattr(row, k)}
    merged["spells"] = row.spells
    merged.update(body.model_dump(exclude_unset=True))
    if "overs_bowled" in body.model_fields_set and "balls_bowled" not in body.model_fields_set:
        merged["balls_bowled"] = None                      # the new overs figure wins over the stored balls figure
    if "balls_bowled" in body.model_fields_set and "overs_bowled" not in body.model_fields_set:
        merged["overs_bowled"] = None
    try:
        v = WorkloadIn(**merged)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if v.log_date > today_lk():
        raise HTTPException(422, "A session log cannot be dated in the future")
    for k, val in v.model_dump(exclude={"event_id", "spells"}).items():
        setattr(row, k, val)
    row.spells = [s.model_dump(exclude_none=True) for s in v.spells] if v.spells else None
    audit(db, user, "workload.updated", "workload_log", row.id)
    alerts = sync_alerts(db, player)
    db.commit()
    return {"log": _out(row), "open_alerts": [_alert_out(a) for a in alerts] if _can_see_alerts(user) else None}


@router.delete("/workload/{log_id}", status_code=204)
def delete_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(require("workload.write"))):
    row = db.get(WorkloadLog, log_id)
    player = _player(db, user, row.player_id if row else -1, "workload.write")
    audit(db, user, "workload.deleted", "workload_log", row.id)
    db.delete(row)
    db.flush()
    sync_alerts(db, player)
    db.commit()


# ───────────── summary, check, limits ─────────────
@router.get("/players/{player_id}/workload/summary")
def summary(player_id: int, as_of: date | None = None, db: Session = Depends(get_db), user: User = Depends(require("workload.read"))):
    player = _player(db, user, player_id, "workload.read")
    day = as_of or today_lk()
    alerts, s = evaluate_player(db, player, day)
    phase = current_phase(db, player, day)
    see = _can_see_alerts(user)
    return {"player_id": player.id, "role": player.role.value, "availability": player.availability.value, "season_phase": phase,
            "summary": s,
            "alerts": [a.__dict__ | {"ref_date": a.ref_date} for a in alerts] if see else None,
            "guidance": wr.overload_guidance(s, alerts, phase) if see else None}


@router.post("/players/{player_id}/workload/check")
def check_planned(player_id: int, body: WorkloadIn, db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    """Planning aid: what new alerts would this session cause? Nothing is saved."""
    player = _player(db, user, player_id, "alerts.read")
    if body.log_date > today_lk() + timedelta(days=14):
        raise HTTPException(422, "Plan checks look at most 14 days ahead")
    day = max(body.log_date, today_lk())
    before, _ = evaluate_player(db, player, day)
    planned = wr.Log(date=body.log_date, session_type=body.session_type.value, attended=body.attended, duration_min=body.duration_min,
                     rpe=body.rpe, intensity=body.session_intensity, balls_bowled=body.balls_bowled, overs_bowled=body.overs_bowled,
                     spells=[s.model_dump(exclude_none=True) for s in body.spells] if body.spells else None)
    after, _ = evaluate_player(db, player, day, extra=planned)
    seen = {(a.rule_code, a.ref_date) for a in before}
    new = [a for a in after if (a.rule_code, a.ref_date) not in seen]
    return {"ok": not new, "new_alerts": [a.__dict__ for a in new]}


@router.put("/players/{player_id}/workload-limits")
def set_limits(player_id: int, body: LimitsIn, db: Session = Depends(get_db), user: User = Depends(require("workload.limits"))):
    player = _player(db, user, player_id, "workload.limits")
    limits = {k: v for k, v in body.model_dump().items() if v}
    if limits.get("max_spell_overs") and limits.get("max_match_day_overs") and limits["max_spell_overs"] > limits["max_match_day_overs"]:
        raise HTTPException(422, "The spell limit cannot be above the daily limit")
    player.workload_limits = limits or None
    audit(db, user, "workload.limits_set", "player", player.id, ", ".join(f"{k}={v}" for k, v in limits.items()))
    sync_alerts(db, player)
    db.commit()
    return {"custom": player.workload_limits, "effective": wr.effective_limits(player.role.value, player.workload_limits, player.squad.age_group)}


# ───────────── wellness ─────────────
@router.post("/players/{player_id}/wellness", response_model=WellnessOut)
def save_wellness(player_id: int, body: WellnessIn, db: Session = Depends(get_db), user: User = Depends(require("wellness.write"))):
    """One record per player per day (saving again replaces it). Pain detail is deliberately not collected here."""
    player = _player(db, user, player_id, "wellness.write")
    if body.log_date > today_lk():
        raise HTTPException(422, "A wellness record cannot be dated in the future")
    row = db.scalar(select(WellnessLog).where(WellnessLog.player_id == player.id, WellnessLog.log_date == body.log_date))
    if row is None:
        row = WellnessLog(player_id=player.id, log_date=body.log_date)
        db.add(row)
    for k, v in body.model_dump(exclude={"log_date"}).items():
        setattr(row, k, v)
    db.flush()
    audit(db, user, "wellness.saved", "wellness_log", row.id)
    sync_alerts(db, player)
    db.commit()
    return row


@router.get("/players/{player_id}/wellness", response_model=list[WellnessOut])
def list_wellness(player_id: int, db: Session = Depends(get_db), user: User = Depends(require("workload.read"))):
    player = _player(db, user, player_id, "workload.read")
    return db.scalars(select(WellnessLog).where(WellnessLog.player_id == player.id, WellnessLog.log_date >= today_lk() - timedelta(days=27))
                      .order_by(WellnessLog.log_date.desc())).all()


# ───────────── squad overview and alerts ─────────────
@router.get("/squads/{squad_id}/workload/overview")
def overview(squad_id: int, as_of: date | None = None, db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    authorize_squad(db, user, squad_id, "alerts.read")
    day = as_of or today_lk()
    out = []
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active.is_(True)).order_by(Player.full_name)))
    evals = evaluate_players(db, players, day)
    for p in players:
        alerts, s = evals[p.id]
        out.append({"player_id": p.id, "name": p.full_name, "role": p.role.value, "availability": p.availability.value,
                    "acute_load_7d": s["acute_load_7d"], "acwr": s["acwr"], "acwr_status": s["acwr_status"],
                    "vs_last_week_pct": s["vs_last_week_pct"], "overs_7d": s["bowling"]["overs_7d"],
                    "bowling_days_7d": len(s["bowling"]["days_bowled_7d"]), "history_days": s["history_days"],
                    "worst_severity": s["alerts_worst"], "alert_count": len(alerts)})
    return out


@router.get("/squads/{squad_id}/alerts", response_model=list[AlertOut])
def squad_alerts(squad_id: int, include_resolved: bool = False, db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    authorize_squad(db, user, squad_id, "alerts.read")
    q = (select(Alert, Player.full_name).join(Player, Player.id == Alert.player_id).where(Player.squad_id == squad_id)
         .order_by(Alert.created_at.desc()).limit(500))
    if not include_resolved:
        q = q.where(Alert.resolved_at.is_(None))
    return [_alert_out(a, n) for a, n in db.execute(q)]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(alert_id: int, db: Session = Depends(get_db), user: User = Depends(require("alerts.ack"))):
    from datetime import datetime, timezone
    a = db.get(Alert, alert_id)
    player = _player(db, user, a.player_id if a else -1, "alerts.ack")
    a.acknowledged_by, a.acknowledged_at = user.id, datetime.now(timezone.utc)
    audit(db, user, "alert.acknowledged", "alert", a.id, a.rule_code)
    db.commit()
    return _alert_out(a, player.full_name)
