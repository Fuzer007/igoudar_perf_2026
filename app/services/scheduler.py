from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import SessionLocal
from app.services.updater import finnhub_update_prices


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    def _job() -> None:
        print("[scheduler] Starting hourly price update via Finnhub...")
        session = SessionLocal()
        try:
            finnhub_update_prices(session, delay_seconds=1.0)
        finally:
            session.close()
        print("[scheduler] Hourly update complete.")

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
