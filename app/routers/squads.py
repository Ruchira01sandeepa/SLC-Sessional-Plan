from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Player, Squad, User, UserRole
from ..permissions import squad_ids
from ..schemas import SquadOut

router = APIRouter(prefix="/squads", tags=["squads"])


@router.get("", response_model=list[SquadOut])
def my_squads(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The squads this user may see: all (admin), assigned (staff), own squad (player)."""
    q = select(Squad).order_by(Squad.name)
    if user.role == UserRole.player:
        q = q.where(Squad.id.in_(select(Player.squad_id).where(Player.user_id == user.id)))
    elif user.role != UserRole.admin:
        q = q.where(Squad.id.in_(squad_ids(db, user) or {-1}))
    return db.scalars(q).all()
