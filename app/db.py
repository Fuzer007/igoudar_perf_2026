from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(db_url: str) -> None:
    if db_url.startswith("sqlite"):
        DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_database_url(db_url: str) -> str:
    # Render Postgres often provides DATABASE_URL as postgres:// or postgresql://.
    # SQLAlchemy's default postgresql driver is psycopg2; this project uses psycopg (v3).
    # Normalize so SQLAlchemy uses the installed driver.
    if db_url.startswith("postgres://"):
        return "postgresql+psycopg://" + db_url.removeprefix("postgres://")
    if db_url.startswith("postgresql://") and "+" not in db_url.split("://", 1)[0]:
        return "postgresql+psycopg://" + db_url.removeprefix("postgresql://")
    return db_url



db_url = _normalize_database_url(settings.database_url)
_ensure_sqlite_dir(db_url)

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
