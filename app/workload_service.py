"""Database side of the workload engine: load a player's logs, run the pure rules, keep the alerts table in step."""
from datetime import date, datetime, timedelta, timezone

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import workload_rules as wr
from .models import Alert, Player, Season, SeasonPhase, WellnessLog, WorkloadLog

LK = timezone(timedelta(hours=5, minutes=30))            # Sri Lanka: fixed offset, no daylight saving


def today_lk() -> date:
    return datetime.now(LK).date()


def to_log(r: WorkloadLog) -> wr.Log:
    return wr.Log(date=r.log_date, session_type=r.session_type.value, attended=r.attended, duration_min=r.duration_min,
                  rpe=r.rpe, intensity=r.session_intensity, balls_bowled=r.balls_bowled, overs_bowled=r.overs_bowled, spells=r.spells)


def inputs(db: Session, player: Player, as_of: date):
    start = as_of - timedelta(days=wr.HISTORY_DAYS * 2 + 7)
    logs = [to_log(r) for r in db.scalars(select(WorkloadLog).where(
        WorkloadLog.player_id == player.id, WorkloadLog.log_date >= start, WorkloadLog.log_date <= as_of))]
    # all-time first log date, so "history_days" is not capped by the window
    first = db.scalar(select(WorkloadLog.log_date).where(WorkloadLog.player_id == player.id, WorkloadLog.log_date <= as_of).order_by(WorkloadLog.log_date).limit(1))
    well = [wr.Wellness(date=w.log_date, soreness=w.soreness, fatigue=w.fatigue, sleep_hours=w.sleep_hours, pain_flag=w.pain_flag)
            for w in db.scalars(select(WellnessLog).where(WellnessLog.player_id == player.id, WellnessLog.log_date >= as_of - timedelta(days=10), WellnessLog.log_date <= as_of))]
    return logs, first, well


def evaluate_players(db: Session, players: list[Player], as_of: date) -> dict[int, tuple]:
    """Same result as evaluate_player() for many players, with three queries in total instead of three per player."""
    ids = [p.id for p in players]
    if not ids:
        return {}
    start = as_of - timedelta(days=wr.HISTORY_DAYS * 2 + 7)
    logs: dict[int, list] = defaultdict(list)
    for r in db.scalars(select(WorkloadLog).where(WorkloadLog.player_id.in_(ids), WorkloadLog.log_date >= start, WorkloadLog.log_date <= as_of)
                        .order_by(WorkloadLog.id)):
        logs[r.player_id].append(to_log(r))
    first = dict(db.execute(select(WorkloadLog.player_id, func.min(WorkloadLog.log_date)).where(
        WorkloadLog.player_id.in_(ids), WorkloadLog.log_date <= as_of).group_by(WorkloadLog.player_id)).all())
    well: dict[int, list] = defaultdict(list)
    for w in db.scalars(select(WellnessLog).where(WellnessLog.player_id.in_(ids), WellnessLog.log_date >= as_of - timedelta(days=10),
                                                  WellnessLog.log_date <= as_of).order_by(WellnessLog.id)):
        well[w.player_id].append(wr.Wellness(date=w.log_date, soreness=w.soreness, fatigue=w.fatigue, sleep_hours=w.sleep_hours, pain_flag=w.pain_flag))
    out = {}
    for p in players:
        lg, f = logs[p.id], first.get(p.id)
        if f and not any(x.date == f for x in lg):
            lg.append(wr.Log(date=f, attended=False))
        out[p.id] = wr.evaluate(lg, well[p.id], p.availability.value, p.role.value, p.workload_limits, as_of,
                                p.squad.age_group if p.squad else None)
    return out


def evaluate_player(db: Session, player: Player, as_of: date, extra: wr.Log | None = None):
    logs, first, well = inputs(db, player, as_of)
    if extra:
        logs.append(extra)
    if first and not any(lg.date == first for lg in logs):      # keep the true first date visible to the engine
        logs.append(wr.Log(date=first, attended=False))          # zero-load marker: not attended, no load, no bowling
    return wr.evaluate(logs, well, player.availability.value, player.role.value, player.workload_limits, as_of,
                       player.squad.age_group if player.squad else None)


def current_phase(db: Session, player: Player, as_of: date) -> str | None:
    p = db.scalar(select(SeasonPhase.phase_type).join(Season, Season.id == SeasonPhase.season_id).where(
        Season.squad_id == player.squad_id, SeasonPhase.start_date <= as_of, SeasonPhase.end_date >= as_of).limit(1))
    return p.value if p is not None else None


def sync_alerts(db: Session, player: Player, as_of: date | None = None) -> list[Alert]:
    """Make the open alerts match what the rules say today. Keeps acknowledgements; resolves cleared conditions."""
    as_of = as_of or today_lk()
    computed, _ = evaluate_player(db, player, as_of)
    open_rows = list(db.scalars(select(Alert).where(Alert.player_id == player.id, Alert.resolved_at.is_(None))))
    by_key = {(a.rule_code, a.ref_date): a for a in open_rows}
    keep = set()
    for c in computed:
        k = (c.rule_code, c.ref_date)
        keep.add(k)
        row = by_key.get(k)
        if row is None:
            db.add(Alert(player_id=player.id, rule_code=c.rule_code, severity=c.severity, message=c.message, ref_date=c.ref_date))
        else:
            if row.severity != c.severity:                       # got worse or better: needs a fresh look
                row.acknowledged_by = row.acknowledged_at = None
            row.severity, row.message = c.severity, c.message
    now = datetime.now(timezone.utc)
    for k, row in by_key.items():
        if k not in keep:
            row.resolved_at = now
    db.flush()
    return list(db.scalars(select(Alert).where(Alert.player_id == player.id, Alert.resolved_at.is_(None)).order_by(Alert.created_at.desc())))
