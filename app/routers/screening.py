from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user
from ..models import NeedsAnalysisItem, Player, Screening, User
from ..permissions import authorize_player
from ..screening_schema import NEEDS_GRID, ScreeningIn, ScreeningOut, ScreeningUpdate

router = APIRouter(tags=["screening"])


@router.get("/meta/needs-grid")
def needs_grid(_: User = Depends(current_user)):
    return NEEDS_GRID


def _own(db, screening_id) -> Screening:
    s = db.get(Screening, screening_id)
    if s is None:
        raise HTTPException(404, "Screening not found")
    return s


@router.get("/players/{player_id}/screenings", response_model=list[ScreeningOut])
def list_screenings(player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "player.read")
    return db.scalars(select(Screening).where(Screening.player_id == p.id).order_by(Screening.screening_date.desc())).all()


@router.post("/players/{player_id}/screenings", response_model=ScreeningOut, status_code=201)
def create_screening(player_id: int, body: ScreeningIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = authorize_player(db, user, db.get(Player, player_id), "plan.write")
    data = body.model_dump(exclude={"needs"})
    s = Screening(player_id=p.id, recorded_by=user.id, **data)
    s.needs = [NeedsAnalysisItem(**n.model_dump()) for n in body.needs]
    db.add(s)
    db.flush()
    audit(db, user, "screening.created", "screening", s.id)
    db.commit()
    return s


@router.patch("/screenings/{screening_id}", response_model=ScreeningOut)
def update_screening(screening_id: int, body: ScreeningUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _own(db, screening_id)
    authorize_player(db, user, db.get(Player, s.player_id), "plan.write")   # also hides other squads (404)
    data = body.model_dump(exclude_unset=True, exclude={"needs"})
    for k, v in data.items():
        setattr(s, k, v)
    if body.needs is not None:                       # a supplied list replaces the whole grid
        s.needs = [NeedsAnalysisItem(**n.model_dump()) for n in body.needs]
    audit(db, user, "screening.updated", "screening", s.id, ",".join(data))
    db.commit()
    return s
