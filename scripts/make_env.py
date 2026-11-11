"""Create a .env with fresh random secrets.   python -m scripts.make_env
Refuses to overwrite an existing .env. Back up SLC_MEDICAL_KEY: without it medical records cannot be read."""
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

path = Path(".env")
if path.exists():
    sys.exit(".env already exists - not overwriting. Delete it first if you really want new keys "
             "(existing medical data would become unreadable).")
path.write_text(f"SLC_DATABASE_URL=sqlite:///./slc_u15.db\nSLC_JWT_SECRET={secrets.token_urlsafe(48)}\n"
                f"SLC_MEDICAL_KEY={Fernet.generate_key().decode()}\n", encoding="utf-8")
print(".env created. KEEP A SEPARATE BACKUP OF SLC_MEDICAL_KEY.")
