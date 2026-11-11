import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..fitness_metrics import BY_FIELD, METRICS, NEUTRAL, improved, percentile, target_status
from ..models import FitnessBenchmark, FitnessPhase, FitnessTest, Player, Season, User
from ..permissions import authorize_player, authorize_squad
from ..role_kpis import ALL_KPIS, kpis_for, validate_role_specific

router = APIRouter(tags=["fitness"])
_YOYO = re.compile(r"^\d{1,2}(\.\d{1,2})?$")
LOOKUP = {**BY_FIELD, **ALL_KPIS}                 # everything that can have a target / benchmark
PHASES = ("baseline", "mid_season", "end_season")


class FitnessIn(BaseModel):
    test_date: date | None = None
    bodyweight_kg: float | None = None
    height_cm: float | None = None
    cmj_cm: float | None = None
    squat_jump_cm: float | None = None
    sprint_5m_s: float | None = None
    sprint_10m_s: float | None = None
    sprint_20m_s: float | None = None
    yoyo_level: str | None = None
    yoyo_distance_m: int | None = None
    prone_plank_s: float | None = None
    side_plank_front_s: float | None = None
    side_plank_back_s: float | None = None
    calf_raises_front_leg: int | None = None
    calf_raises_back_leg: int | None = None
    role_specific: dict | None = None             # role KPIs, see role_kpis.py

    @model_validator(mode="after")
    def _ranges(self):
        for m in METRICS:
            v = getattr(self, m.field)
            if v is not None and not m.lo <= v <= m.hi:
                raise ValueError(f"{m.label} {v} {m.unit} is outside the plausible range {m.lo}-{m.hi} {m.unit} - check the entry")
        if self.yoyo_level is not None and not _YOYO.match(self.yoyo_level):
            raise ValueError("Yo-Yo level must look like 15.3 (level.shuttle)")
        s5, s10, s20 = self.sprint_5m_s, self.sprint_10m_s, self.sprint_20m_s
        pairs = [(a, b) for a, b in ((s5, s10), (s10, s20), (s5, s20)) if a is not None and b is not None]
        if any(a >= b for a, b in pairs):
            raise ValueError("Sprint times must increase with distance (5 m < 10 m < 20 m)")
        if self.role_specific is not None and len(str(self.role_specific)) > 5000:
            raise ValueError("role_specific is too large")
        return self


class FitnessOut(FitnessIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    player_id: int
    season_id: int
    phase: FitnessPhase
    test_date: date


def _season_for(db, player: Player, season_id: int) -> Season:
    s = db.get(Season, season_id)
    if s is None or s.squad_id != player.squad_id:
        raise HTTPException(404, "Season not found for this player's squad")
    return s


@router.put("/players/{player_id}/fitness/{season_id}/{phase}", response_model=FitnessOut)
def upsert_fitness(player_id: int, season_id: int, phase: FitnessPhase, body: FitnessIn,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Create or update one test phase. Only fields that are sent change; send null to clear a value.
    `role_specific` is merged measure by measure (a null measure clears it; a null `role_specific` clears all)."""
    p = authorize_player(db, user, db.get(Player, player_id), "fitness.write")
    season = _season_for(db, p, season_id)
    t = db.scalar(select(FitnessTest).where(FitnessTest.player_id == p.id, FitnessTest.season_id == season_id,
                                            FitnessTest.phase == phase))
    data = body.model_dump(exclude_unset=True)
    rs_new, clear_rs = {}, False
    if "role_specific" in data:
        raw = data.pop("role_specific")
        if raw is None:
            clear_rs = True
        else:
            try:
                rs_new = validate_role_specific(p.role, raw)
            except ValueError as e:
                raise HTTPException(422, str(e))
    if t is None:
        has_result = any(data.get(k) is not None for k in [m.field for m in METRICS] + ["yoyo_level"]) \
            or any(v is not None for v in rs_new.values())
        if not has_result:
            raise HTTPException(422, "Enter at least one result")
        if data.get("test_date") is None:
            raise HTTPException(422, "test_date is required for a new test")
        t = FitnessTest(player_id=p.id, season_id=season_id, phase=phase, test_date=data["test_date"])
        db.add(t)
    if data.get("test_date") is not None and not season.start_date <= data["test_date"] <= season.end_date:
        raise HTTPException(422, f"test_date is outside the season ({season.start_date} to {season.end_date})")
    for k, v in data.items():
        if k == "test_date" and v is None:
            continue
        setattr(t, k, v)
    if clear_rs:
        t.role_specific = None
    elif rs_new:
        merged = {k: v for k, v in {**(t.role_specific or {}), **rs_new}.items() if v is not None}
        t.role_specific = merged or None
    t.tested_by = user.id
    db.flush()
    audit(db, user, "fitness.saved", "fitness_test", t.id, f"{phase.value}:{','.join(list(data) + (['role_specific'] if rs_new or clear_rs else []))}")
    db.commit()
    return t


@router.get("/players/{player_id}/fitness", response_model=list[FitnessOut])
def list_fitness(player_id: int, season_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "fitness.read")
    q = select(FitnessTest).where(FitnessTest.player_id == p.id).order_by(FitnessTest.test_date)
    if season_id:
        q = q.where(FitnessTest.season_id == season_id)
    return db.scalars(q).all()


# ───────────── benchmarks / targets ─────────────
class TargetIn(BaseModel):
    field_name: str
    target_value: float
    note: str | None = Field(default=None, max_length=300)

    @field_validator("field_name")
    @classmethod
    def _known(cls, v):
        if v not in LOOKUP or v in NEUTRAL:
            raise ValueError("Unknown or non-targetable field")
        return v


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    squad_id: int | None
    player_id: int | None
    field_name: str
    target_value: float
    higher_is_better: bool
    note: str | None


def _put_target(db, user, body: TargetIn, *, squad_id=None, player_id=None) -> FitnessBenchmark:
    m = LOOKUP[body.field_name]
    if not m.lo <= body.target_value <= m.hi:
        raise HTTPException(422, f"Target is outside the plausible range {m.lo}-{m.hi} {m.unit}")
    b = db.scalar(select(FitnessBenchmark).where(FitnessBenchmark.field_name == body.field_name,
                  FitnessBenchmark.squad_id == squad_id, FitnessBenchmark.player_id == player_id)) if (squad_id or player_id) else None
    if b is None:
        b = FitnessBenchmark(squad_id=squad_id, player_id=player_id, field_name=body.field_name)
        db.add(b)
    b.target_value, b.note, b.higher_is_better, b.is_provisional, b.set_by = body.target_value, body.note, m.higher_is_better, True, user.id
    db.flush()
    audit(db, user, "fitness.target_set", "player" if player_id else "squad", player_id or squad_id, body.field_name)
    db.commit()
    return b


@router.put("/squads/{squad_id}/fitness-benchmarks", response_model=TargetOut)
def set_squad_benchmark(squad_id: int, body: TargetIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize_squad(db, user, squad_id, "fitness.write")
    return _put_target(db, user, body, squad_id=squad_id)


@router.put("/players/{player_id}/fitness-targets", response_model=TargetOut)
def set_player_target(player_id: int, body: TargetIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "fitness.write")
    if body.field_name in ALL_KPIS and body.field_name not in {m.field for m in kpis_for(p.role)}:
        raise HTTPException(422, "That measure does not apply to this player's role")
    return _put_target(db, user, body, squad_id=None, player_id=p.id)


# ───────────── progress report ─────────────
def _row(m, vals: dict, peers_by_phase: dict, own_t: dict, squad_t: dict) -> dict:
    """One metric: baseline / mid / end, the latest value, change from baseline, squad percentile, targets."""
    phase = next((ph for ph in reversed(PHASES) if vals.get(ph) is not None), None)
    cur = vals.get(phase) if phase else None
    base = vals.get("baseline")
    peers = peers_by_phase.get(phase, []) if phase else []
    change = None if base is None or cur is None else round(cur - base, 2)
    return {
        "field": m.field, "label": m.label, "unit": m.unit, "higher_is_better": None if m.field in NEUTRAL else m.higher_is_better,
        "baseline": base, "mid_season": vals.get("mid_season"), "end_season": vals.get("end_season"),
        "current": cur, "current_phase": phase,
        "change_from_baseline": change,
        "change_pct": None if change is None or not base else round(100 * change / base, 1),
        "improved": improved(m, base, cur),
        "squad_percentile": percentile(m, cur, peers), "squad_n": len(peers),
        "individual_target": own_t.get(m.field), "coach_benchmark": squad_t.get(m.field),
        "individual_target_status": target_status(m, cur, own_t.get(m.field)),
        "coach_benchmark_status": target_status(m, cur, squad_t.get(m.field)),
    }


@router.get("/players/{player_id}/fitness/progress")
def progress(player_id: int, season_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Baseline, mid, end, current, change from baseline, squad percentile, individual target, coach benchmark.
    `metrics` = the fitness tests; `role_metrics` = this player's role-specific measures."""
    p = authorize_player(db, user, db.get(Player, player_id), "fitness.read")
    _season_for(db, p, season_id)
    mine = {t.phase.value: t for t in db.scalars(select(FitnessTest).where(FitnessTest.player_id == p.id, FitnessTest.season_id == season_id))}
    squad_rows = db.execute(select(FitnessTest, Player.role).join(Player, Player.id == FitnessTest.player_id)
                            .where(Player.squad_id == p.squad_id, Player.is_active, FitnessTest.season_id == season_id)).all()
    marks = db.scalars(select(FitnessBenchmark).where((FitnessBenchmark.player_id == p.id) | (FitnessBenchmark.squad_id == p.squad_id))).all()
    own_t = {b.field_name: b.target_value for b in marks if b.player_id == p.id}
    squad_t = {b.field_name: b.target_value for b in marks if b.squad_id == p.squad_id and b.player_id is None}

    rows = []
    for m in METRICS:
        vals = {ph: getattr(t, m.field) for ph, t in mine.items()}
        peers: dict = {}
        for t, _role in squad_rows:
            v = getattr(t, m.field)
            if v is not None:
                peers.setdefault(t.phase.value, []).append(v)
        rows.append(_row(m, vals, peers, own_t, squad_t))

    role_rows = []
    for m in kpis_for(p.role):
        vals = {ph: (t.role_specific or {}).get(m.field) for ph, t in mine.items()}
        peers = {}
        for t, role in squad_rows:
            v = (t.role_specific or {}).get(m.field)
            if v is not None and role == p.role:             # compare like with like: same role only
                peers.setdefault(t.phase.value, []).append(v)
        role_rows.append(_row(m, vals, peers, own_t, squad_t))
    return {"player_id": p.id, "season_id": season_id, "role": p.role.value,
            "note": "Compared only with the player's own baseline, their targets and squad peers. "
                    "Targets are provisional; no adult or international standards are applied.",
            "metrics": rows, "role_metrics": role_rows}


@router.get("/squads/{squad_id}/fitness")
def squad_table(squad_id: int, season_id: int, phase: FitnessPhase, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The Fitness Report sheet: one row per player for a season and test phase."""
    authorize_squad(db, user, squad_id, "fitness.read")
    if user.role.value == "player":
        raise HTTPException(403, "Players see their own results, not the squad table")
    rows = db.execute(select(Player, FitnessTest).outerjoin(
        FitnessTest, (FitnessTest.player_id == Player.id) & (FitnessTest.season_id == season_id) & (FitnessTest.phase == phase))
        .where(Player.squad_id == squad_id, Player.is_active).order_by(Player.full_name)).all()
    out = []
    for pl, t in rows:
        out.append({"player_id": pl.id, "name": pl.full_name, "role": pl.role.value, "batting_hand": pl.batting_hand,
                    "bowling_arm": pl.bowling_arm, "front_side": pl.front_side,
                    "test_date": t.test_date if t else None, "yoyo_level": t.yoyo_level if t else None,
                    **{m.field: getattr(t, m.field) if t else None for m in METRICS}})
    return out
