from app.core.db import Base, SessionLocal, engine
from app.core import models  # noqa: F401  (register tables)
from app.reference.seed_templates import seed

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print("seeded:", seed(db))
