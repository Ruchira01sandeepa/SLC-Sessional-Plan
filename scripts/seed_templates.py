from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401  (register tables)
from app.seed_templates import seed

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print("seeded:", seed(db))
