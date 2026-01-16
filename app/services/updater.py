"""Stock price updater using Finnhub API only."""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import PricePoint, Stock
from app.services import finnhub


_LAST_UPDATE_FILE = DATA_DIR / "last_update_utc.txt"


def _normalize_observed_at(value: dt.datetime) -> dt.datetime:
    """Normalize datetimes to naive UTC for SQLite storage and comparisons."""
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _recently_updated(within_seconds: int) -> bool:
    try:
        txt = _LAST_UPDATE_FILE.read_text().strip()
        if not txt:
            return False
        last = dt.datetime.fromisoformat(txt)
        now = dt.datetime.now(dt.timezone.utc)
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt.timezone.utc)
        return (now - last).total_seconds() < within_seconds
    except Exception:
        return False


def _mark_updated_now() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_UPDATE_FILE.write_text(dt.datetime.now(dt.timezone.utc).isoformat())


def compute_return_pct(purchase: float | None, current: float | None) -> float | None:
    if purchase is None or current is None or purchase == 0:
        return None
    return ((current - purchase) / purchase) * 100


def compute_return_abs(purchase: float | None, current: float | None) -> float | None:
    if purchase is None or current is None:
        return None
    return current - purchase


def finnhub_update_prices(session: Session, *, delay_seconds: float = 1.0) -> dict[str, int]:
    """Update prices using Finnhub API - works from cloud servers like Render.
    
    Finnhub free tier: 60 calls/minute, so 1 second delay is safe.
    """
    updated = 0
    skipped = 0
    failed = 0

    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
    if not stocks:
        return {"updated": 0, "skipped": 0, "failed": 0}

    print(f"[finnhub_update] Starting update for {len(stocks)} stocks...")
    
    for i, stock in enumerate(stocks):
        if i > 0:
            time.sleep(delay_seconds)
        
        try:
            quote = finnhub.get_quote(stock.ticker)
            
            if not quote or quote.get("c") == 0:
                print(f"[finnhub_update] {stock.ticker}: no data")
                skipped += 1
                continue
            
            price = float(quote["c"])  # current price
            timestamp = quote.get("t", 0)  # Unix timestamp
            
            if timestamp:
                observed_at = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).replace(tzinfo=None)
            else:
                observed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            
            # Normalize stored last_price_at to naive UTC for comparison
            stored_time = stock.last_price_at
            if stored_time and stored_time.tzinfo is not None:
                stored_time = stored_time.astimezone(dt.timezone.utc).replace(tzinfo=None)
            
            # Skip if we already have this or newer
            if stored_time and observed_at <= stored_time:
                print(f"[finnhub_update] {stock.ticker}: already up to date")
                skipped += 1
                continue
            
            # Add price point
            session.add(
                PricePoint(
                    stock_id=stock.id,
                    observed_at=observed_at,
                    price=price,
                )
            )
            stock.last_price = price
            stock.last_price_at = observed_at
            session.commit()
            
            print(f"[finnhub_update] {stock.ticker}: ${price:.2f}")
            updated += 1
            
        except Exception as e:
            print(f"[finnhub_update] {stock.ticker}: error - {e}")
            failed += 1
    
    _mark_updated_now()
    print(f"[finnhub_update] Done: {updated} updated, {skipped} skipped, {failed} failed")
    return {"updated": updated, "skipped": skipped, "failed": failed}


def finnhub_backfill_history(
    session: Session,
    *,
    start_date: dt.date | None = None,
    delay_seconds: float = 1.0,
) -> dict[str, int]:
    """Backfill daily history using Finnhub candles API.
    
    WARNING: Finnhub free tier does NOT have access to candles endpoint (403 Forbidden).
    This function will fail. Use only finnhub_update_prices() which uses the quote endpoint.
    """
    print("[finnhub_backfill] ERROR: Finnhub free tier does not support candles endpoint")
    print("[finnhub_backfill] Use finnhub_update_prices() to fetch current prices instead")
    return {"inserted": 0, "skipped": 0, "failed": 0}
