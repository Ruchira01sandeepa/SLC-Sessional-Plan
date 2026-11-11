from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user, require
from ..models import Player, PlayerMedical, Squad, User, UserRole
from ..permissions import authorize_player, role_allows, squad_ids
from ..schemas import (AvailabilityIn, LinkUserIn, MedicalIn, MedicalOut, PlayerCreate, PlayerOut, PlayerUpdate)
from ..age_groups import check_dob

router = APIRouter(prefix="/players", tags=["players"])


def _get(db: Session, player_id: int) -> Player | None:
    return db.get(Player, player_id)


@router.get("", response_model=list[PlayerOut])
def list_players(squad_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require("player.read"))):
    """Only players the caller may see: self (player), assigned squads (staff), everyone (admin)."""
    q = select(Player).order_by(Player.full_name)
    if user.role == UserRole.player:
        q = q.where(Player.user_id == user.id)
    elif user.role != UserRole.admin:
        q = q.where(Player.squad_id.in_(squad_ids(db, user) or {-1}))
    if squad_id is not None:
        q = q.where(Player.squad_id == squad_id)
    return db.scalars(q).all()


def _check_age(squad: Squad, dob) -> None:
    """The date of birth must fit the squad's age group (U15: 8-16, U17: 12-18; see app/age_groups.py)."""
    try:
        check_dob(squad.age_group, dob, date.today())
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("", response_model=PlayerOut, status_code=201)
def create_player(body: PlayerCreate, db: Session = Depends(get_db), user: User = Depends(require("player.create"))):
    if db.get(Squad, body.squad_id) is None:
        raise HTTPException(404, "Squad not found")
    if user.role != UserRole.admin and body.squad_id not in squad_ids(db, user):
        raise HTTPException(403, "You are not assigned to this squad")
    _check_age(db.get(Squad, body.squad_id), body.date_of_birth)
    player = Player(**body.model_dump())
    db.add(player)
    db.flush()
    audit(db, user, "player.created", "player", player.id)
    db.commit()
    return player


@router.get("/{player_id}", response_model=PlayerOut)
def get_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return authorize_player(db, user, _get(db, player_id), "player.read")


@router.patch("/{player_id}", response_model=PlayerOut)
def update_player(player_id: int, body: PlayerUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    player = authorize_player(db, user, _get(db, player_id), "player.update")
    data = body.model_dump(exclude_unset=True)
    if "squad_id" in data and data["squad_id"] != player.squad_id:
        if user.role != UserRole.admin:
            raise HTTPException(403, "Only an administrator can move a player between squads")
        target = db.get(Squad, data["squad_id"])
        if target is None:
            raise HTTPException(404, "Squad not found")
        _check_age(target, player.date_of_birth)
    for k, v in data.items():
        setattr(player, k, v)
    audit(db, user, "player.updated", "player", player.id, ",".join(data))
    db.commit()
    return player


@router.put("/{player_id}/link-user", response_model=PlayerOut)
def link_user(player_id: int, body: LinkUserIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Attach a login (role=player) to a player record so the player can see their own data."""
    player = authorize_player(db, user, _get(db, player_id), "player.link_user")
    if body.user_id is not None:
        target = db.get(User, body.user_id)
        if target is None or target.role != UserRole.player:
            raise HTTPException(400, "user_id must be an existing user with role 'player'")
        if db.scalar(select(Player.id).where(Player.user_id == body.user_id, Player.id != player.id)):
            raise HTTPException(409, "That login is already linked to another player")
    player.user_id = body.user_id
    audit(db, user, "player.link_user", "player", player.id, f"user={body.user_id}")
    db.commit()
    return player


# ───────────── availability: the only health info coaches see ─────────────
@router.put("/{player_id}/availability", response_model=PlayerOut)
def set_availability(player_id: int, body: AvailabilityIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    player = authorize_player(db, user, _get(db, player_id), "availability.write")
    player.availability = body.availability
    player.availability_note = body.availability_note
    audit(db, user, "availability.set", "player", player.id, body.availability.value)
    db.commit()
    return player


# ───────────── medical detail: physio only, encrypted, audited ─────────────
@router.get("/{player_id}/medical", response_model=MedicalOut)
def get_medical(player_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    player = _get(db, player_id)
    # Everyone without medical.read gets 403 (not 404) - the endpoint's existence is not a secret,
    # but the audit trail records the attempt.
    if not role_allows(user, "medical.read"):
        audit(db, user, "medical.denied", "player", player_id)
        db.commit()
    player = authorize_player(db, user, player, "medical.read")
    audit(db, user, "medical.read", "player", player.id)
    db.commit()
    m = player.medical
    if m is None:
        return MedicalOut(player_id=player.id)
    return MedicalOut(player_id=player.id, current_health=(m.current_health or {}).get("text"),
                      injury_history=m.injury_history, reports=m.reports,
                      injured_body_parts=m.injured_body_parts, updated_at=m.updated_at)


@router.put("/{player_id}/medical", response_model=MedicalOut)
def put_medical(player_id: int, body: MedicalIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    player = _get(db, player_id)
    if not role_allows(user, "medical.write"):
        audit(db, user, "medical.denied", "player", player_id)
        db.commit()
    player = authorize_player(db, user, player, "medical.write")
    m = player.medical or PlayerMedical(player_id=player.id)
    data = body.model_dump(exclude_unset=True)
    if "current_health" in data:
        m.current_health = {"text": data["current_health"]}
    for field in ("injury_history", "reports", "injured_body_parts"):
        if field in data:
            setattr(m, field, data[field])
    m.updated_by = user.id
    db.add(m)
    audit(db, user, "medical.write", "player", player.id, ",".join(data))
    db.commit()
    return MedicalOut(player_id=player.id, current_health=(m.current_health or {}).get("text"),
                      injury_history=m.injury_history, reports=m.reports,
                      injured_body_parts=m.injured_body_parts, updated_at=m.updated_at)
