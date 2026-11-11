"""Password hashing, JWT tokens, and field-level encryption for medical data."""
import json
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

from .config import settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(pw: str) -> None:
    if len(pw) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if pw.lower() == pw or pw.upper() == pw or not any(c.isdigit() for c in pw):
        raise ValueError("Password needs upper case, lower case and a digit.")


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


_fernet = Fernet(settings.medical_key.encode())


class EncryptedJSON(TypeDecorator):
    """Stores any JSON-serialisable value as Fernet-encrypted text.

    Encrypted columns cannot be searched or sorted in SQL. That is intentional
    for medical/injury data: the database alone (a backup, a leaked dump) reveals nothing.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet.encrypt(json.dumps(value).encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(_fernet.decrypt(value.encode()))
        except InvalidToken as e:  # wrong key or tampered data: fail loudly, never return garbage
            raise RuntimeError("Medical data could not be decrypted (wrong key?)") from e
