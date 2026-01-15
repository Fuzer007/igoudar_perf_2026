from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import SessionLocal
from app.services.updater import update_all_prices


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    def _job() -> None:
        session = SessionLocal()
        try:
            update_all_prices(session)
        finally:
            session.close()

    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=settings.update_interval_minutes,
        id="price-updater",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    return scheduler
