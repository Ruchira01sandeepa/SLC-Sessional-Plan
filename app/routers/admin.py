from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import audit, require
from ..models import ApprovalStatus, Squad, SquadStaff, User, UserRole
from ..schemas import (ApproveIn, SignupRequestOut, SquadCreate, SquadOut, StaffAssign, UserCreate, UserOut,
                       UserUpdate)
from ..security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = Depends(require("users.manage"))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = admin_only):
    user = User(email=body.email.lower(), full_name=body.full_name, role=body.role, language=body.language,
                password_hash=hash_password(body.temp_password), must_change_password=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    audit(db, admin, "user.created", "user", user.id, f"role={body.role.value}")
    db.commit()
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = admin_only):
    """Approved and rejected accounts. Pending sign-ups are listed separately (GET /admin/signup-requests)."""
    return db.scalars(select(User).where(User.approval_status != ApprovalStatus.pending).order_by(User.full_name)).all()


# ───────────── self sign-up requests ─────────────
@router.get("/signup-requests", response_model=list[SignupRequestOut])
def list_signup_requests(db: Session = Depends(get_db), _: User = admin_only):
    pending = db.scalars(select(User).where(User.approval_status == ApprovalStatus.pending).order_by(User.created_at)).all()
    return [SignupRequestOut.model_validate(u).model_copy(update={"role_can_sign_in": settings.role_enabled(u.role.value)}) for u in pending]


def _reviewable(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.approval_status == ApprovalStatus.approved:
        raise HTTPException(404, "Access request not found")
    return user


@router.post("/signup-requests/{user_id}/approve", response_model=UserOut)
def approve_signup(user_id: int, body: ApproveIn, db: Session = Depends(get_db), admin: User = admin_only):
    """Approve a pending (or previously rejected) request, optionally with a different role than the one asked for."""
    user = _reviewable(db, user_id)
    if body.role is not None:
        user.role = body.role
    user.approval_status, user.is_active = ApprovalStatus.approved, True
    user.reviewed_by, user.reviewed_at = admin.id, datetime.now(timezone.utc)
    audit(db, admin, "signup.approved", "user", user.id, f"role={user.role.value}")
    db.commit()
    return user


@router.post("/signup-requests/{user_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_signup(user_id: int, db: Session = Depends(get_db), admin: User = admin_only):
    """The account is kept (so the audit trail stays intact) but can never sign in unless approved later."""
    user = _reviewable(db, user_id)
    user.approval_status, user.is_active = ApprovalStatus.rejected, False
    user.reviewed_by, user.reviewed_at = admin.id, datetime.now(timezone.utc)
    audit(db, admin, "signup.rejected", "user", user.id)
    db.commit()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = admin_only):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("is_active") is False or ("role" in data and data["role"] != UserRole.admin)):
        raise HTTPException(400, "You cannot deactivate or demote your own account")
    for k, v in data.items():
        setattr(user, k, v)
    audit(db, admin, "user.updated", "user", user.id, ",".join(data))
    db.commit()
    return user


@router.post("/squads", response_model=SquadOut, status_code=201)
def create_squad(body: SquadCreate, db: Session = Depends(get_db), admin: User = Depends(require("squads.manage"))):
    squad = Squad(**body.model_dump())
    db.add(squad)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A squad with this name already exists")
    audit(db, admin, "squad.created", "squad", squad.id)
    db.commit()
    return squad


@router.get("/squads", response_model=list[SquadOut])
def list_squads(db: Session = Depends(get_db), _: User = Depends(require("squads.manage"))):
    return db.scalars(select(Squad).order_by(Squad.name)).all()


@router.get("/squads/{squad_id}/staff", response_model=list[UserOut])
def get_squad_staff(squad_id: int, db: Session = Depends(get_db), _: User = Depends(require("squads.manage"))):
    if db.get(Squad, squad_id) is None:
        raise HTTPException(404, "Squad not found")
    return db.scalars(select(User).join(SquadStaff, SquadStaff.user_id == User.id)
                      .where(SquadStaff.squad_id == squad_id).order_by(User.full_name)).all()


@router.put("/squads/{squad_id}/staff", response_model=list[UserOut])
def set_squad_staff(squad_id: int, body: StaffAssign, db: Session = Depends(get_db),
                    admin: User = Depends(require("squads.manage"))):
    """Replace the staff list of a squad. Players cannot be squad staff."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(404, "Squad not found")
    users = db.scalars(select(User).where(User.id.in_(body.user_ids))).all() if body.user_ids else []
    if len(users) != len(set(body.user_ids)):
        raise HTTPException(400, "One or more user ids do not exist")
    if any(u.role in (UserRole.player,) for u in users):
        raise HTTPException(400, "Players cannot be assigned as squad staff")
    if any(u.approval_status != ApprovalStatus.approved for u in users):
        raise HTTPException(400, "Approve the access request before assigning this person to a squad")
    # Apply the difference (not "delete all + insert all"): inserting a row that already exists
    # would violate the unique (user, squad) constraint before the old row is flushed away.
    wanted = {u.id for u in users}
    for link in list(squad.staff):
        if link.user_id not in wanted:
            squad.staff.remove(link)
    have = {link.user_id for link in squad.staff}
    for uid in wanted - have:
        squad.staff.append(SquadStaff(user_id=uid, squad_id=squad.id))
    audit(db, admin, "squad.staff_set", "squad", squad.id, f"users={sorted(body.user_ids)}")
    db.commit()
    return users
