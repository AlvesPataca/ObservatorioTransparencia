import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'data' / 'observatorio.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)


def _ensure_sqlite_columns() -> None:
    if engine.dialect.name != "sqlite":
        return
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "public_records" in inspector.get_table_names():
            cols = {col["name"] for col in inspector.get_columns("public_records")}
            if "year" not in cols:
                with engine.begin() as conn:
                    conn.execute(text('ALTER TABLE public_records ADD COLUMN "year" INTEGER'))
    except Exception:
        pass


_ensure_sqlite_columns()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
