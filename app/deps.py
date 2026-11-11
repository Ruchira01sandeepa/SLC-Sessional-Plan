from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .config import settings
from .models import ApprovalStatus, AuditLog, User
from .permissions import ACTIONS
from .security import decode_access_token
import jwt

_bearer = HTTPBearer(auto_error=False)


def _load_user(creds: HTTPAuthorizationCredentials | None, db: Session) -> User:
    unauth = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauth
    try:
        payload = decode_access_token(creds.credentials)
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauth
    # Re-check the DB on every request: a deactivated user or a changed role takes effect immediately,
    # even though their token has not expired.
    if (user is None or not user.is_active or user.approval_status != ApprovalStatus.approved
            or user.role.value != payload.get("role")
            or not settings.role_enabled(user.role.value)):
        raise unauth
    return user


def current_user_any(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    """Authenticated user, even if they still must change their initial password."""
    return _load_user(creds, db)


def current_user(user: User = Depends(current_user_any)) -> User:
    if user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
    return user


def require(action: str):
    """Dependency factory: `Depends(require("users.manage"))` -> 403 unless the role is allowed."""
    allowed = ACTIONS[action]

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role may not perform this action")
        return user
    return dep


def audit(db: Session, user: User | None, action: str, entity: str | None = None,
          entity_id: int | None = None, detail: str | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity=entity,
                    entity_id=entity_id, detail=(detail or "")[:300] or None))
