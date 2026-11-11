"""Settings, read from environment variables (or a .env file)."""
from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SLC_", extra="ignore")

    # SQLite for local dev; use e.g. postgresql+psycopg://user:pw@host/db in production.
    database_url: str = "sqlite:///./slc_u15.db"

    # JWT signing key. MUST be overridden in production.
    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 8

    # Fernet key (urlsafe base64, 32 bytes) used to encrypt medical/injury data at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # MUST be overridden in production and backed up: losing it makes medical data unreadable.
    medical_key: str = "ZGV2LW9ubHktbWVkaWNhbC1rZXktMzItYnl0ZXMtISE="

    @field_validator("medical_key")
    @classmethod
    def _valid_fernet_key(cls, v: str) -> str:
        try:
            Fernet(v.encode())
        except Exception:
            raise ValueError(
                "SLC_MEDICAL_KEY is not a valid encryption key (it looks like a placeholder). "
                "Run:  python -m scripts.make_env   to create a .env with fresh keys, "
                "or delete the SLC_MEDICAL_KEY line to use the development key.") from None
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _real_secret(cls, v: str) -> str:
        if v.upper().startswith("CHANGE-ME") or len(v) < 32:
            raise ValueError("SLC_JWT_SECRET is a placeholder or too short (min 32 characters). "
                             "Run:  python -m scripts.make_env   or delete the line to use the development secret.")
        return v

    # Lock an account for this long after too many failed logins.
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # Which roles may sign in. The app is ADMIN-ONLY for now. To open it up later set e.g.
    #   SLC_ENABLED_ROLES=all            or    SLC_ENABLED_ROLES=admin,coach,physio
    enabled_roles: str = "admin"

    @field_validator("enabled_roles")
    @classmethod
    def _roles_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if v == "all":
            return v
        names = {x.strip() for x in v.split(",") if x.strip()}
        if not names or names - {"player", "coach", "sc_coach", "physio", "admin"}:
            raise ValueError("SLC_ENABLED_ROLES must be 'all' or a comma list of: player, coach, sc_coach, physio, admin")
        return ",".join(sorted(names))

    # Self sign-up: anyone can ASK for an account; it does nothing until an administrator approves it.
    # Set SLC_SIGNUP_ENABLED=false to hide the "Request access" form and turn the endpoint off.
    signup_enabled: bool = True
    # Stop accepting new requests while this many are waiting (protects against form spam filling the table).
    max_pending_signups: int = 50

    def role_enabled(self, role: str) -> bool:
        return self.enabled_roles == "all" or role in self.enabled_roles.split(",")


settings = Settings()
