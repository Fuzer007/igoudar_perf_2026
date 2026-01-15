from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = Path("/data") if Path("/data").exists() else (PROJECT_ROOT / "data")
DATA_DIR = Path(os.getenv("DATA_DIR", str(_DEFAULT_DATA_DIR)))


def _default_database_url() -> str:
    # If a Render persistent disk is mounted at /data, use it automatically.
    if Path("/data").exists():
        return "sqlite:////data/app.db"
    return "sqlite:///./data/app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    database_url: str = Field(default_factory=_default_database_url)
    update_interval_minutes: int = 60


load_dotenv(PROJECT_ROOT / ".env")
settings = Settings()
