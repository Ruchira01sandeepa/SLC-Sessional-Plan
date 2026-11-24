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
    # heart rate and external load (all optional; McGawley workshop: measure internal AND external load)
    hr_avg: int | None = Field(default=None, ge=40, le=230)
    zone_minutes: list[float] | None = Field(default=None, max_length=5)      # 50-60, 60-70, 70-80, 80-90, 90-100% HRmax
    hit_minutes: float | None = Field(default=None, ge=0, le=480)
    sprint_m: int | None = Field(default=None, ge=0, le=20000)
    volume_load_kg: float | None = Field(default=None, ge=0, le=200000)
    foot_contacts: int | None = Field(default=None, ge=0, le=3000)
    sprint_times: list[float] | None = Field(default=None, max_length=40)
    event_id: int | None = None

    @model_validator(mode="after")
    def _consistent(self):
        measures = (self.duration_min, self.session_intensity, self.rpe, self.balls_bowled, self.overs_bowled, self.spells,
                    self.balls_faced, self.keeping_minutes, self.throws, self.hr_avg, self.zone_minutes, self.hit_minutes, self.sprint_m,
                    self.volume_load_kg, self.foot_contacts, self.sprint_times)
        if self.zone_minutes is not None and any(m is None or m < 0 or m > 480 for m in self.zone_minutes):
            raise ValueError("Heart-rate zone minutes are 0 to 480 each (five zones: 50-60, 60-70, 70-80, 80-90, 90-100% HRmax)")
        if self.sprint_times is not None and any(t is None or not 1 <= t <= 120 for t in self.sprint_times):
            raise ValueError("Sprint times are seconds, 1 to 120 each")
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
    # heart rate and external load (all optional; McGawley workshop: measure internal AND external load)
    hr_avg: int | None = Field(default=None, ge=40, le=230)
    zone_minutes: list[float] | None = Field(default=None, max_length=5)      # 50-60, 60-70, 70-80, 80-90, 90-100% HRmax
    hit_minutes: float | None = Field(default=None, ge=0, le=480)
    sprint_m: int | None = Field(default=None, ge=0, le=20000)
    volume_load_kg: float | None = Field(default=None, ge=0, le=200000)
    foot_contacts: int | None = Field(default=None, ge=0, le=3000)
    sprint_times: list[float] | None = Field(default=None, max_length=40)


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
    hr_avg: int | None = None
    zone_minutes: list | None = None
    hit_minutes: float | None = None
    sprint_m: int | None = None
    volume_load_kg: float | None = None
    foot_contacts: int | None = None
    sprint_times: list | None = None
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
    # batting and keeping in the same 7 days, plus the longest spell (for the fast-bowler limit check)
    bat: dict[int, dict] = {p.id: {"balls": 0, "days": set(), "keep": 0, "spell": 0.0} for p in players}
    if players:
        for r in db.scalars(select(WorkloadLog).where(WorkloadLog.player_id.in_(list(bat)), WorkloadLog.attended.is_(True),
                                                      WorkloadLog.log_date > day - timedelta(days=7), WorkloadLog.log_date <= day)):
            b = bat[r.player_id]
            if r.balls_faced:
                b["balls"] += r.balls_faced
                b["days"].add(r.log_date)
            b["keep"] += r.keeping_minutes or 0
            for sp in r.spells or []:
                o = sp.get("overs") if isinstance(sp, dict) else None
                if o:
                    b["spell"] = max(b["spell"], float(o))
    for p in players:
        alerts, s = evals[p.id]
        bw, b = s["bowling"], bat[p.id]
        out.append({"player_id": p.id, "name": p.full_name, "role": p.role.value, "availability": p.availability.value,
                    "acute_load_7d": s["acute_load_7d"], "acwr": s["acwr"], "acwr_status": s["acwr_status"],
                    "vs_last_week_pct": s["vs_last_week_pct"], "overs_7d": bw["overs_7d"],
                    "bowling_days_7d": len(bw["days_bowled_7d"]),
                    "max_day_overs_7d": max(bw["overs_by_day"].values(), default=0), "max_spell_7d": b["spell"] or None,
                    "bowling_limits": bw["limits"],
                    "balls_faced_7d": b["balls"], "batting_days_7d": len(b["days"]), "keeping_minutes_7d": b["keep"],
                    "history_days": s["history_days"], "worst_severity": s["alerts_worst"], "alert_count": len(alerts)})
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


# ───────────── earlier workload: weeks before the app was used, entered as one summary per player and week ─────────────
from .. import earlier_workload as ew  # noqa: E402


class EarlierRow(BaseModel):
    player_id: int
    sessions: int = Field(ge=0, le=7)
    minutes: int | None = Field(default=None, ge=10, le=300)
    rpe: int | None = Field(default=None, ge=1, le=10)
    overs: float | None = Field(default=None, ge=0, le=100)
    bowling_days: int | None = Field(default=None, ge=0, le=7)


class EarlierWeek(BaseModel):
    week_start: date
    rows: list[EarlierRow] = Field(max_length=100)


def _week_bounds(week_start: date) -> tuple[date, date]:
    today = today_lk()
    end = week_start + timedelta(days=6)
    if end >= today:
        raise HTTPException(422, "Earlier workload is for weeks that are already over. Log this week's sessions in the workload log.")
    if week_start < today - timedelta(weeks=ew.MAX_WEEKS_BACK):
        raise HTTPException(422, f"Earlier workload goes back at most {ew.MAX_WEEKS_BACK} weeks")
    return week_start, end


def _week_logs(db: Session, ids: list[int], start: date, end: date) -> dict[int, list[WorkloadLog]]:
    out: dict[int, list[WorkloadLog]] = {i: [] for i in ids}
    for r in db.scalars(select(WorkloadLog).where(WorkloadLog.player_id.in_(ids or [-1]), WorkloadLog.log_date >= start, WorkloadLog.log_date <= end)):
        out[r.player_id].append(r)
    return out


def _is_coach_log(r: WorkloadLog) -> bool:
    """A log a person entered (not the earlier-week spread, not the automatic test-day load)."""
    return r.match_participation not in (ew.MARK, "test_battery")


@router.get("/squads/{squad_id}/workload/earlier")
def get_earlier(squad_id: int, week_start: date, db: Session = Depends(get_db), user: User = Depends(require("workload.limits"))):
    """One week of earlier workload for every player: what was entered, and whether the week already has logged sessions."""
    authorize_squad(db, user, squad_id, "workload.limits")
    start, end = _week_bounds(week_start)
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active.is_(True)).order_by(Player.squad_no, Player.full_name)))
    logs = _week_logs(db, [p.id for p in players], start, end)
    rows = []
    for p in players:
        mine = [r for r in logs[p.id] if r.match_participation == ew.MARK]
        rows.append({"player_id": p.id, "name": p.full_name, "role": p.role.value, "squad_no": p.squad_no,
                     "bowls": p.role.value in ("fast_bowler", "spin_bowler", "all_rounder"),
                     "entry": ew.summarise([{"duration_min": r.duration_min, "rpe": r.rpe, "balls_bowled": r.balls_bowled} for r in mine]),
                     "logged_sessions": sum(1 for r in logs[p.id] if _is_coach_log(r)),
                     "other_days": sorted({r.log_date.isoformat() for r in logs[p.id] if r.match_participation != ew.MARK})})
    return {"week_start": start, "week_end": end, "players": rows}


@router.put("/squads/{squad_id}/workload/earlier")
def put_earlier(squad_id: int, body: EarlierWeek, db: Session = Depends(get_db), user: User = Depends(require("workload.limits"))):
    """Save one week: each row replaces that player's earlier-week logs for the week (sessions 0 clears it). A week in which
    a coach already logged sessions is refused for that player, so real logs are never doubled or overwritten."""
    authorize_squad(db, user, squad_id, "workload.limits")
    start, end = _week_bounds(body.week_start)
    players = {p.id: p for p in db.scalars(select(Player).where(Player.squad_id == squad_id, Player.id.in_([r.player_id for r in body.rows] or [-1])))}
    logs = _week_logs(db, list(players), start, end)
    errors, saved, cleared = [], 0, 0
    plans = {}
    for r in body.rows:
        p = players.get(r.player_id)
        if p is None:
            errors.append({"player_id": r.player_id, "message": "Not a player of this squad"})
            continue
        if r.sessions and any(_is_coach_log(x) for x in logs[p.id]):
            errors.append({"player_id": p.id, "message": f"{p.full_name} already has sessions logged in this week: use the workload log instead"})
            continue
        if r.overs and p.role.value not in ("fast_bowler", "spin_bowler", "all_rounder"):
            errors.append({"player_id": p.id, "message": f"{p.full_name} does not bowl: leave overs empty"})
            continue
        try:
            avoid = {x.log_date for x in logs[p.id] if x.match_participation != ew.MARK}
            plans[p.id] = ew.spread_week(start, sessions=r.sessions, minutes=r.minutes or 0, rpe=r.rpe or 0, overs=r.overs,
                                         bowling_days=r.bowling_days, avoid=avoid) if r.sessions else []
        except ValueError as e:
            errors.append({"player_id": p.id, "message": f"{p.full_name}: {e}"})
    if errors:
        raise HTTPException(422, {"message": "Nothing was saved. Fix these rows and save again.", "errors": errors})
    for pid, new in plans.items():
        for x in logs[pid]:
            if x.match_participation == ew.MARK:
                db.delete(x)
        for n in new:
            db.add(WorkloadLog(player_id=pid, session_type=EventType.training, attended=True, recorded_by=user.id, match_participation=ew.MARK, **n))
        saved += bool(new)
        cleared += not new
    db.flush()
    for pid in plans:
        sync_alerts(db, players[pid])
    audit(db, user, "workload.earlier_saved", "squad", squad_id, f"week {start}: {saved} saved, {cleared} cleared")
    db.commit()
    return {"week_start": start, "saved": saved, "cleared": cleared}


# ───────────── the weekly workload report (McGawley workshop: sRPE, monotony, strain, change, ACWR, TRIMP, external load) ─────────────
class HeartRateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hr_max: int | None = Field(default=None, ge=150, le=230)
    hr_rest: int | None = Field(default=None, ge=30, le=110)


@router.put("/players/{player_id}/heart-rate")
def set_heart_rate(player_id: int, body: HeartRateIn, db: Session = Depends(get_db), user: User = Depends(require("workload.limits"))):
    """The player's measured maximum and resting heart rate (for Edwards and Banister TRIMP)."""
    player = _player(db, user, player_id, "workload.limits")
    if body.hr_max and body.hr_rest and body.hr_rest >= body.hr_max:
        raise HTTPException(422, "The resting heart rate must be below the maximum")
    player.hr_max, player.hr_rest = body.hr_max, body.hr_rest
    audit(db, user, "player.heart_rate_set", "player", player.id)
    db.commit()
    return {"hr_max": player.hr_max, "hr_rest": player.hr_rest}


def _session_dicts(rows) -> list[dict]:
    return [{"date": r.log_date, "type": r.session_type.value, "attended": r.attended, "minutes": r.duration_min, "rpe": r.rpe,
             "intensity": r.session_intensity, "hr_avg": r.hr_avg, "zone_minutes": r.zone_minutes, "hit_minutes": r.hit_minutes,
             "sprint_m": r.sprint_m, "volume_load_kg": r.volume_load_kg, "foot_contacts": r.foot_contacts, "sprint_times": r.sprint_times,
             "overs": r.overs_bowled, "id": r.id} for r in rows]


def _player_week(db: Session, p: Player, monday: date) -> dict:
    from ..workload_calc import estimated_hr_max, week_report
    rows = list(db.scalars(select(WorkloadLog).where(WorkloadLog.player_id == p.id, WorkloadLog.log_date <= monday + timedelta(days=6))
                           .order_by(WorkloadLog.log_date, WorkloadLog.id)))
    hist = _session_dicts(rows)
    week = [x for x in hist if monday <= x["date"] <= monday + timedelta(days=6)]
    well = [{"date": w.log_date, "soreness": w.soreness, "fatigue": w.fatigue, "sleep_hours": w.sleep_hours}
            for w in db.scalars(select(WellnessLog).where(WellnessLog.player_id == p.id, WellnessLog.log_date >= monday,
                                                          WellnessLog.log_date <= monday + timedelta(days=6)))]
    age = (monday - p.date_of_birth).days / 365.25 if p.date_of_birth else None
    hr_max = p.hr_max or estimated_hr_max(age)
    rep = week_report(week, monday, history=hist, wellness=well, hr_rest=p.hr_rest, hr_max=hr_max, sex=p.gender.value)
    rep["player"] = {"id": p.id, "name": p.full_name, "role": p.role.value, "squad_no": p.squad_no, "hr_max": p.hr_max, "hr_rest": p.hr_rest,
                     "hr_max_used": hr_max, "hr_max_estimated": not p.hr_max and hr_max is not None}
    return rep


def _monday(d: date | None) -> date:
    d = d or today_lk()
    return d - timedelta(days=d.weekday())


def _planned_pct(db: Session, user: User, squad_id: int, monday: date) -> float | None:
    """The annual plan's planned load % for the week (the season that holds the week), for 'measured vs planned'."""
    from ..models import Season
    from .plans import _grid
    season = db.scalar(select(Season).where(Season.squad_id == squad_id, Season.start_date <= monday + timedelta(days=6))
                       .order_by(Season.start_date.desc()).limit(1))
    if season is None:
        return None
    try:
        g = _grid(db, user, squad_id, season.id)
    except HTTPException:
        return None
    w = (monday + timedelta(days=2) - g["week_starts"][0]).days // 7
    return round(g["percentage"][w] * 100) if 0 <= w < g["weeks"] else None


def _jsonable(rep: dict) -> dict:
    out = dict(rep)
    out["monday"], out["sunday"] = rep["monday"].isoformat(), rep["sunday"].isoformat()
    out["days"] = [{**d, "date": d["date"].isoformat(), "sessions": [{**x, "date": x["date"].isoformat()} for x in d["sessions"]]} for d in rep["days"]]
    return out


@router.get("/players/{player_id}/workload/week")
def player_week(player_id: int, week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(require("workload.read"))):
    """One player's week, Monday to Sunday, as in the workshop's example week: each day's sessions (minutes, RPE, load), the
    weekly load, mean and SD of the daily load, monotony, strain, change on last week, ACWR, weekly load %, TRIMP and external load."""
    p = _player(db, user, player_id, "workload.read")
    return _jsonable(_player_week(db, p, _monday(week_start)))


def _squad_week(db: Session, user: User, squad_id: int, week_start: date | None):
    authorize_squad(db, user, squad_id, "alerts.read")
    monday = _monday(week_start)
    players = list(db.scalars(select(Player).where(Player.squad_id == squad_id, Player.is_active.is_(True))
                              .order_by(Player.squad_no.is_(None), Player.squad_no, Player.full_name)))
    return monday, [_player_week(db, p, monday) for p in players], _planned_pct(db, user, squad_id, monday)


@router.get("/squads/{squad_id}/workload/week")
def squad_week(squad_id: int, week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    monday, reps, planned = _squad_week(db, user, squad_id, week_start)
    keys = ("sessions", "total", "mean_daily", "sd_daily", "monotony", "strain", "previous_week", "change_pct", "acwr", "acwr_band",
            "load_pct", "edwards_trimp", "banister_trimp", "hit_minutes", "sprint_m", "volume_load_kg", "foot_contacts", "sdec", "flags")
    return {"monday": monday.isoformat(), "planned_pct": planned,
            "players": [{"player_id": r["player"]["id"], "name": r["player"]["name"], "role": r["player"]["role"],
                         **{k: r[k] for k in keys}, "wellness": r["wellness"]} for r in reps]}


@router.get("/squads/{squad_id}/workload/report.xlsx")
def squad_week_report(squad_id: int, week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    """The weekly workload report in Excel: the squad week, each player's week (Mon-Sun table with formulas), the 8-week trend,
    the test change (pre -> post, % change and effect size), the formulas and the process."""
    import re
    from fastapi.responses import Response
    from ..models import Squad
    from ..workload_excel import build_workload_workbook
    monday, reps, planned = _squad_week(db, user, squad_id, week_start)
    squad = db.get(Squad, squad_id)
    trend = {r["player"]["id"]: [_player_week(db, db.get(Player, r["player"]["id"]), monday - timedelta(days=7 * k))["total"]
                                 for k in range(7, -1, -1)] for r in reps}
    tests = _test_change(db, squad_id)
    audit(db, user, "workload.report_exported", "squad", squad_id)
    db.commit()
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"Workload-report-{squad.name}-week-of-{monday.isoformat()}").strip("-")
    return Response(build_workload_workbook(squad.name, monday, reps, planned, trend, tests),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


def _test_change(db: Session, squad_id: int) -> dict:
    """The same tests, first window -> latest window of the latest season with results: % change and effect size per test."""
    from ..models import Season
    from ..test_battery import BY_KEY, WINDOW_LABEL
    from ..workload_calc import test_change
    from .testing import _finals, _windows_for
    for season in db.scalars(select(Season).where(Season.squad_id == squad_id).order_by(Season.start_date.desc())):
        wins = _windows_for(db, squad_id, season.id)
        if not wins:
            continue
        order = list(wins)
        pre_w, post_w = order[0], order[-1]
        pre = {pid: _finals(s) for pid, s in wins[pre_w][1].items()}
        post = {pid: _finals(s) for pid, s in wins[post_w][1].items()}
        rows = []
        for key, t in BY_KEY.items():
            a = {pid: f[key] for pid, f in pre.items() if f.get(key) is not None}
            b = {pid: f[key] for pid, f in post.items() if f.get(key) is not None}
            if a:
                rows.append({"test": t.label, "unit": t.unit, "lower_is_better": not t.higher_is_better,
                             **(test_change(a, b, not t.higher_is_better) if post_w != pre_w else {"n": 0, "pre_mean": sum(a.values()) / len(a)})})
        return {"season": season.name, "pre": WINDOW_LABEL[pre_w], "post": WINDOW_LABEL[post_w] if post_w != pre_w else None, "rows": rows}
    return {"season": None, "pre": None, "post": None, "rows": []}
