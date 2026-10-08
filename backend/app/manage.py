"""Development schema bootstrap only; production requires migrations with separate role."""
from pathlib import Path
from sqlalchemy import text
from app.db import Base,engine
from app import models  # noqa: F401

def bootstrap():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name=="postgresql":
        script=Path(__file__).resolve().parents[1]/"db"/"security"/"rls.sql"
        statements=[s.strip() for s in script.read_text().split(";") if s.strip()]
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

if __name__=="__main__":
    bootstrap()
    print("Developer database initialized; production migrations still required.")
