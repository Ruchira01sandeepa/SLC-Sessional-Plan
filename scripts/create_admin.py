"""Create the first administrator.   python -m scripts.create_admin you@example.com "Full Name"
The password is read from the prompt (never from the command line / shell history)."""
import getpass
import sys

from app.db import SessionLocal
from app.models import User, UserRole
from app.security import hash_password, validate_password_strength

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    email, name = sys.argv[1].lower(), sys.argv[2]
    pw = getpass.getpass("Temporary password: ")
    validate_password_strength(pw)
    with SessionLocal() as db:
        if db.query(User).filter_by(email=email).first():
            sys.exit("User already exists")
        db.add(User(email=email, full_name=name, role=UserRole.admin, password_hash=hash_password(pw), must_change_password=True))
        db.commit()
    print("Admin created. They must change the password at first login.")
