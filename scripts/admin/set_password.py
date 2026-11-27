"""Set a user's own, permanent password (local administration).   python -m scripts.admin.set_password you@example.com

The password is typed at a hidden prompt, twice; it never appears on the command line, in shell history or in a log.
It is the user's real password: they are NOT asked to change it at the next sign-in. Any sign-in lockout is cleared.
Use this instead of handing out temporary passwords when you are setting your own."""
import getpass
import sys

from app.core.db import SessionLocal
from app.core.models import User
from app.core.security import hash_password, validate_password_strength

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    email = sys.argv[1].strip().lower()
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).first()
        if not user:
            sys.exit(f"No user with the email {email}")
        if not sys.stdin.isatty():                      # piped in (e.g. from set_password.ps1, which shows *** while typing)
            lines = sys.stdin.read().splitlines() + ["", ""]
            pw, again = lines[0], lines[1]
        else:
            pw = getpass.getpass("New password (10+ characters, upper and lower case, a digit): ")
            again = None
        try:
            validate_password_strength(pw)
        except ValueError as e:
            sys.exit(str(e))
        if (again if again is not None else getpass.getpass("Type it again: ")) != pw:
            sys.exit("The two passwords do not match. Nothing was changed.")
        user.password_hash = hash_password(pw)
        user.must_change_password = False
        user.failed_logins = 0
        user.locked_until = None
        db.commit()
    print(f"Password set for {email}. Sign in with it; you will not be asked to change it.")
