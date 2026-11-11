from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import audit, current_user_any
from ..models import ApprovalStatus, User, UserRole
from ..schemas import SIGNUP_ROLES, AuthConfigOut, LoginIn, PasswordChangeIn, SignupIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Same message for unknown email / wrong password / locked / rejected, so the API cannot be used to enumerate accounts.
_BAD = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
_DUMMY_HASH = hash_password("dummy-password-for-timing")
# Shown only AFTER the correct password, so it reveals nothing to someone guessing emails.
PENDING = "account_pending"
# Identical for a new request and for an email that already has an account (no account enumeration).
SIGNUP_RECEIVED = {"detail": "Thank you. Your request has been sent to an administrator. "
                             "You can sign in once it has been approved."}


@router.get("/config", response_model=AuthConfigOut)
def auth_config():
    """Public: what the sign-in screen should offer."""
    enabled = list(UserRole) if settings.enabled_roles == "all" else [UserRole(r) for r in settings.enabled_roles.split(",")]
    return AuthConfigOut(signup_enabled=settings.signup_enabled, signup_roles=list(SIGNUP_ROLES), enabled_roles=enabled)


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    """Ask for an account. It is created as PENDING and cannot sign in until an administrator approves it.
    The answer is the same whether or not the email is already registered."""
    if not settings.signup_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Self sign-up is turned off. Ask an administrator for an account.")
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        verify_password(body.password, _DUMMY_HASH)                # keep timing similar to the hashing path below
        audit(db, None, "signup.duplicate", "user", None, email)
        db.commit()
        return SIGNUP_RECEIVED
    waiting = db.scalar(select(func.count()).select_from(User).where(User.approval_status == ApprovalStatus.pending))
    if waiting >= settings.max_pending_signups:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Too many access requests are waiting. Please try again later or contact an administrator.")
    user = User(email=email, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password),
                must_change_password=False, is_active=True, approval_status=ApprovalStatus.pending, signup_note=body.note or None)
    db.add(user)
    db.flush()
    audit(db, None, "signup.requested", "user", user.id, f"role={body.role.value}")
    db.commit()
    return SIGNUP_RECEIVED


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    now = datetime.now(timezone.utc)
    if user is None:
        verify_password(body.password, _DUMMY_HASH)          # keep timing similar
        raise _BAD
    locked = user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now
    if locked or not user.is_active:
        audit(db, user, "login.blocked", "user", user.id, "locked" if locked else "inactive")
        db.commit()
        raise _BAD
    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
            audit(db, user, "login.locked", "user", user.id)
        else:
            audit(db, user, "login.failed", "user", user.id)
        db.commit()
        raise _BAD
    user.failed_logins = 0
    user.locked_until = None
    if user.approval_status == ApprovalStatus.rejected:
        audit(db, user, "login.rejected_account", "user", user.id)
        db.commit()
        raise _BAD
    if user.approval_status == ApprovalStatus.pending:
        audit(db, user, "login.pending", "user", user.id)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, PENDING)
    if not settings.role_enabled(user.role.value):
        audit(db, user, "login.role_disabled", "user", user.id)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only administrators can sign in at the moment. Other roles will be enabled later.")
    audit(db, user, "login.ok", "user", user.id)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role.value),
                    must_change_password=user.must_change_password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user_any)):
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeIn, user: User = Depends(current_user_any), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must differ from the current one")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, user, "password.changed", "user", user.id)
    db.commit()
