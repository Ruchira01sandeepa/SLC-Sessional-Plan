"""PDP development ratings (workbook: PDP > Individual Rating Assessment). The coach rates each skill 1-5
(1-2 area to improve, 3 average, 4-5 strength). The latest ratings feed the player's individual plan."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..models import PdpRating, PdpRubricItem, Player, ProgressStatus, SkillAssessment, SkillTemplate, TemplateKind, User
from ..role_skills import KIND_LABEL_SHEET, STATUS_LABEL
from ..permissions import authorize_player
from ..player_profile import PDP_EXCLUDED, PDP_GROUPS
from ..workload_service import today_lk

router = APIRouter(tags=["development ratings"])
LEGEND = {1: "Area to improve", 2: "Area to improve", 3: "Average", 4: "Strength", 5: "Strength"}


class RatingsIn(BaseModel):
    rated_on: date | None = None
    ratings: dict[int, int | None] = Field(default_factory=dict)        # rubric item id -> 1..5 (None clears it for that date)

    @field_validator("ratings")
    @classmethod
    def _range(cls, v):
        if len(v) > 200:
            raise ValueError("Too many ratings")
        if any(r is not None and not 1 <= r <= 5 for r in v.values()):
            raise ValueError("Ratings are 1 to 5")
        return v


def _items(db: Session, role: str) -> list[PdpRubricItem]:
    groups = PDP_GROUPS.get(role, [])
    rows = db.scalars(select(PdpRubricItem).where(PdpRubricItem.group_name.in_(groups)).order_by(PdpRubricItem.sort_order)).all()
    order = {g: i for i, g in enumerate(groups)}
    return sorted((r for r in rows if (r.group_name, r.skill_name) not in PDP_EXCLUDED), key=lambda r: (order[r.group_name], r.sort_order))


def _out(db: Session, p: Player) -> dict:
    items = _items(db, p.role.value)
    latest: dict[int, PdpRating] = {}
    for r in db.scalars(select(PdpRating).where(PdpRating.player_id == p.id).order_by(PdpRating.rated_on)):
        latest[r.rubric_item_id] = r
    groups: dict[str, list] = {}
    for it in items:
        r = latest.get(it.id)
        groups.setdefault(it.group_name, []).append({"id": it.id, "skill": it.skill_name, "rating": r.rating if r else None,
                                                      "rated_on": r.rated_on.isoformat() if r else None})
    dates = sorted({r.rated_on for r in latest.values()})
    return {"player_id": p.id, "role": p.role.value, "legend": LEGEND, "last_rated_on": dates[-1].isoformat() if dates else None,
            "groups": [{"group": g, "items": v} for g, v in groups.items()]}


@router.get("/players/{player_id}/pdp")
def get_ratings(player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    return _out(db, p)


@router.put("/players/{player_id}/pdp")
def save_ratings(player_id: int, body: RatingsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    day = body.rated_on or today_lk()
    if day > today_lk():
        raise HTTPException(422, "A rating cannot be dated in the future")
    allowed = {it.id for it in _items(db, p.role.value)}
    bad = [k for k in body.ratings if k not in allowed]
    if bad:
        raise HTTPException(422, "These items are not rated for this player's role: " + ", ".join(map(str, bad)))
    for item_id, rating in body.ratings.items():
        db.execute(delete(PdpRating).where(PdpRating.player_id == p.id, PdpRating.rubric_item_id == item_id, PdpRating.rated_on == day))
        if rating is not None:
            db.add(PdpRating(player_id=p.id, rubric_item_id=item_id, rated_on=day, rating=rating, rated_by=user.id))
    audit(db, user, "pdp.rated", "player", p.id, f"{sum(1 for r in body.ratings.values() if r is not None)} ratings on {day.isoformat()}")
    db.commit()
    return _out(db, p)


# ───────────── role skill grids (Development / Adaptability / Progress Status sheets) ─────────────
class RoleSkillItem(BaseModel):
    template_id: int
    status: ProgressStatus | None = None                 # None clears the entry for that date
    coach_note: str | None = Field(default=None, max_length=500)
    completed_balls: int | None = Field(default=None, ge=0, le=100000)


class RoleSkillsIn(BaseModel):
    period_start: date | None = None
    items: list[RoleSkillItem] = Field(default_factory=list, max_length=200)


def _role_templates(db: Session, p: Player, kind: TemplateKind | None = None) -> list[SkillTemplate]:
    q = select(SkillTemplate).where(SkillTemplate.player_role == p.role)
    if kind:
        q = q.where(SkillTemplate.kind == kind)
    return list(db.scalars(q.order_by(SkillTemplate.kind, SkillTemplate.sort_order)))


def latest_role_skills(db: Session, p: Player) -> dict[int, SkillAssessment]:
    latest: dict[int, SkillAssessment] = {}
    for a in db.scalars(select(SkillAssessment).where(SkillAssessment.player_id == p.id).order_by(SkillAssessment.period_start, SkillAssessment.id)):
        latest[a.skill_template_id] = a
    return latest


def _role_out(db: Session, p: Player, kind: TemplateKind) -> dict:
    tpls = _role_templates(db, p)
    kinds = [k for k in TemplateKind if any(t.kind == k for t in tpls)]
    latest = latest_role_skills(db, p)
    groups: dict[str, list] = {}
    for t in (x for x in tpls if x.kind == kind):
        a = latest.get(t.id)
        groups.setdefault(t.group_name, []).append({"id": t.id, "skill": t.skill_name, "status": a.status.value if a else None,
                                                    "period_start": a.period_start.isoformat() if a else None,
                                                    "coach_note": a.coach_note if a else None, "completed_balls": a.completed_balls if a else None})
    dates = sorted({a.period_start for a in latest.values()})
    return {"player_id": p.id, "role": p.role.value, "kind": kind.value, "kinds": [{"kind": k.value, "label": KIND_LABEL_SHEET[k.value]} for k in kinds],
            "legend": STATUS_LABEL, "last_assessed": dates[-1].isoformat() if dates else None,
            "groups": [{"group": g, "items": v} for g, v in groups.items()]}


@router.get("/players/{player_id}/role-skills")
def get_role_skills(player_id: int, kind: TemplateKind = TemplateKind.development, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "testing.read")
    return _role_out(db, p, kind)


@router.put("/players/{player_id}/role-skills")
def save_role_skills(player_id: int, body: RoleSkillsIn, kind: TemplateKind = TemplateKind.development, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    day = body.period_start or today_lk()
    if day > today_lk():
        raise HTTPException(422, "An assessment cannot be dated in the future")
    allowed = {t.id for t in _role_templates(db, p)}
    bad = [i.template_id for i in body.items if i.template_id not in allowed]
    if bad:
        raise HTTPException(422, "These skills are not part of this player's role: " + ", ".join(map(str, bad)))
    for i in body.items:
        db.execute(delete(SkillAssessment).where(SkillAssessment.player_id == p.id, SkillAssessment.skill_template_id == i.template_id,
                                                 SkillAssessment.period_start == day))
        if i.status is not None:
            db.add(SkillAssessment(player_id=p.id, skill_template_id=i.template_id, period_start=day, status=i.status,
                                   coach_note=(i.coach_note or "").strip() or None, completed_balls=i.completed_balls, assessed_by=user.id))
    audit(db, user, "role_skills.assessed", "player", p.id, f"{len(body.items)} skills on {day.isoformat()}")
    db.commit()
    return _role_out(db, p, kind)
