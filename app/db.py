from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
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

try:
    safe_url = make_url(db_url).set(password="***")
except Exception:
    safe_url = "<invalid DATABASE_URL>"

try:
    engine = create_engine(db_url, future=True, connect_args=connect_args)
except Exception as exc:
    raise RuntimeError(f"Failed to create SQLAlchemy engine for {safe_url}") from exc
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
