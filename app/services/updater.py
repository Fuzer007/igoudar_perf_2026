from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import random
import time

import yfinance as yf

from app.config import DATA_DIR
from app.models import PricePoint, Stock
from app.services.yahoo import fetch_daily_closes, fetch_latest_prices, fetch_purchase_closes_on_or_after


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


def backfill_daily_history(
    session: Session,
    *,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    only_missing: bool = True,
) -> dict[str, int]:
    """Populate DB with daily close prices since start_date (default earliest purchase_date).

    This is the main "populate the database" operation.
    """
    inserted = 0
    skipped = 0
    failed = 0

    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
    if not stocks:
        return {"inserted": 0, "skipped": 0, "failed": 0}

    if start_date is None:
        start_date = min(s.purchase_date for s in stocks)

    if only_missing:
        target = [s for s in stocks if s.purchase_price is None or s.last_price is None]
    else:
        target = stocks

    tickers = [s.ticker for s in target]
    # Use larger batches (fewer API calls) with adequate sleep between them.
    series_map = fetch_daily_closes(
        tickers,
        start=start_date,
        end=end_date,
    )
    if not series_map:
        return {"inserted": 0, "skipped": len(tickers), "failed": 0}

    stocks_by_ticker = {s.ticker: s for s in stocks}

    # For each ticker, insert daily closes, skipping duplicates.
    for ticker, points in series_map.items():
        stock = stocks_by_ticker.get(ticker)
        if stock is None:
            continue
        try:
            existing_times = {
                _normalize_observed_at(t)
                for (t,) in session.execute(
                    select(PricePoint.observed_at).where(PricePoint.stock_id == stock.id)
                ).all()
            }

            for observed_at, price, currency in points:
                observed_at = _normalize_observed_at(observed_at)
                if observed_at in existing_times:
                    skipped += 1
                    continue
                session.add(
                    PricePoint(
                        stock_id=stock.id,
                        observed_at=observed_at,
                        price=price,
                        currency=currency,
                    )
                )
                existing_times.add(observed_at)
                inserted += 1

                # Set purchase price on the first bar on/after purchase_date.
                if stock.purchase_price is None and observed_at.date() >= stock.purchase_date:
                    stock.purchase_price = price
                    stock.purchase_currency = currency

                # Update last price as we go.
                if stock.last_price_at is None or observed_at >= stock.last_price_at:
                    stock.last_price = price
                    stock.last_price_at = observed_at
                    stock.last_currency = currency
        except Exception:
            failed += 1

    session.commit()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


def slow_update_prices(session: Session, *, delay_seconds: float = 12.0) -> dict[str, int]:
    """Update prices one ticker at a time with delays to avoid rate limits.
    
    This is the reliable method used by the scheduler.
    Uses longer delays and retry logic for cloud environments (Render, etc).
    """
    updated = 0
    skipped = 0
    failed = 0

    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
    if not stocks:
        return {"updated": 0, "skipped": 0, "failed": 0}

    print(f"[slow_update] Starting update for {len(stocks)} stocks...")
    print(f"[slow_update] Using {delay_seconds}s base delay between requests")
    
    for i, stock in enumerate(stocks):
        # Wait between each ticker to avoid rate limits
        if i > 0:
            sleep_time = delay_seconds + random.uniform(0, 3)
            time.sleep(sleep_time)
        
        # Retry logic with exponential backoff
        df = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                t = yf.Ticker(stock.ticker)
                # Get last 2 days of hourly data
                df = t.history(period="2d", interval="1h", auto_adjust=False)
                break  # Success, exit retry loop
            except Exception as e:
                err_str = str(e).lower()
                if "rate" in err_str or "too many" in err_str or "429" in err_str:
                    backoff = (attempt + 1) * 30  # 30s, 60s, 90s
                    print(f"[slow_update] {stock.ticker}: rate limited, waiting {backoff}s...")
                    time.sleep(backoff)
                else:
                    print(f"[slow_update] {stock.ticker}: error - {e}")
                    break  # Non-rate-limit error, don't retry
        
        try:
            if df is None or df.empty or "Close" not in df.columns:
                print(f"[slow_update] {stock.ticker}: no data")
                skipped += 1
                continue
            
            # Get the latest close
            series = df["Close"].dropna()
            if series.empty:
                skipped += 1
                continue
            
            observed_at = series.index[-1].to_pydatetime()
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=dt.timezone.utc)
            observed_at = observed_at.replace(tzinfo=None, microsecond=0)
            price = float(series.iloc[-1])
            
            # Skip if we already have this timestamp
            if stock.last_price_at is not None and observed_at <= stock.last_price_at:
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
            
            print(f"[slow_update] {stock.ticker}: {price:.2f}")
            updated += 1
            
        except Exception as e:
            print(f"[slow_update] {stock.ticker}: error - {e}")
            failed += 1
    
    _mark_updated_now()
    print(f"[slow_update] Done: {updated} updated, {skipped} skipped, {failed} failed")
    return {"updated": updated, "skipped": skipped, "failed": failed}


def slow_backfill_daily_history(
    session: Session,
    *,
    start_date: dt.date | None = None,
    delay_seconds: float = 12.0,
) -> dict[str, int]:
    """Backfill daily history one ticker at a time with delays to avoid rate limits.
    
    This is the reliable method for populating the database.
    Uses longer delays and retry logic for cloud environments (Render, etc).
    """
    inserted = 0
    skipped = 0
    failed = 0

    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
    if not stocks:
        return {"inserted": 0, "skipped": 0, "failed": 0}

    if start_date is None:
        start_date = min(s.purchase_date for s in stocks)
    
    end_date = dt.date.today() + dt.timedelta(days=1)
    
    print(f"[slow_backfill] Starting backfill for {len(stocks)} stocks from {start_date}...")
    print(f"[slow_backfill] Using {delay_seconds}s base delay between requests")
    
    for i, stock in enumerate(stocks):
        # Wait between each ticker to avoid rate limits
        if i > 0:
            sleep_time = delay_seconds + random.uniform(0, 3)
            print(f"[slow_backfill] Waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
        
        print(f"[slow_backfill] [{i+1}/{len(stocks)}] {stock.ticker}...", end=" ", flush=True)
        
        # Retry logic with exponential backoff
        df = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                t = yf.Ticker(stock.ticker)
                df = t.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
                break  # Success, exit retry loop
            except Exception as e:
                err_str = str(e).lower()
                if "rate" in err_str or "too many" in err_str or "429" in err_str:
                    backoff = (attempt + 1) * 30  # 30s, 60s, 90s
                    print(f"rate limited, waiting {backoff}s...", end=" ", flush=True)
                    time.sleep(backoff)
                else:
                    print(f"error: {e}")
                    break  # Non-rate-limit error, don't retry
        
        try:
            if df is None or df.empty or "Close" not in df.columns:
                print("no data")
                failed += 1
                continue
            
            # Get existing timestamps to avoid duplicates
            existing = set()
            for pp in stock.prices:
                existing.add(pp.observed_at)
            
            ticker_inserted = 0
            for idx, row in df.iterrows():
                observed_at = idx.to_pydatetime()
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=dt.timezone.utc)
                observed_at = observed_at.replace(tzinfo=None, microsecond=0)
                
                if observed_at in existing:
                    skipped += 1
                    continue
                
                price = float(row["Close"])
                session.add(
                    PricePoint(
                        stock_id=stock.id,
                        observed_at=observed_at,
                        price=price,
                    )
                )
                existing.add(observed_at)
                inserted += 1
                ticker_inserted += 1
                
                # Set purchase price if needed
                if stock.purchase_price is None and observed_at.date() >= stock.purchase_date:
                    stock.purchase_price = price
                
                # Update last price
                if stock.last_price_at is None or observed_at >= stock.last_price_at:
                    stock.last_price = price
                    stock.last_price_at = observed_at
            
            session.commit()
            print(f"+{ticker_inserted}")
            
        except Exception as e:
            print(f"error: {e}")
            failed += 1
    
    print(f"[slow_backfill] Done: {inserted} inserted, {skipped} skipped, {failed} failed")
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


def update_all_prices(session: Session, *, force: bool = False) -> dict[str, int]:
    updated = 0
    skipped = 0
    failed = 0

    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
    if not force and _recently_updated(within_seconds=120):
        return {"updated": 0, "skipped": len(stocks), "failed": 0}

    stocks_by_ticker = {s.ticker: s for s in stocks}

    # Fill missing purchase prices in one batched request.
    missing_purchase = [s.ticker for s in stocks if s.purchase_price is None]
    if missing_purchase:
        purchase_date = stocks[0].purchase_date
        purchase_map = fetch_purchase_closes_on_or_after(missing_purchase, purchase_date)
        for ticker, (observed_at, price, currency) in purchase_map.items():
            stock = stocks_by_ticker.get(ticker)
            if stock is None or stock.purchase_price is not None:
                continue
            observed_at = _normalize_observed_at(observed_at)
            stock.purchase_price = price
            stock.purchase_currency = currency
            session.add(
                PricePoint(
                    stock_id=stock.id,
                    observed_at=observed_at,
                    price=price,
                    currency=currency,
                )
            )

    # Fetch latest prices in one batched request.
    latest_map = fetch_latest_prices([s.ticker for s in stocks])
    if not latest_map and stocks:
        # Common in dev: Yahoo blocks aggressive fetching.
        print("[updater] No latest prices returned (possibly rate limited).")

    for stock in stocks:
        try:
            latest = latest_map.get(stock.ticker)
            if latest is None:
                skipped += 1
                continue
            observed_at, price, currency = latest
            observed_at = _normalize_observed_at(observed_at)

            # Avoid duplicates if we re-run quickly.
            if stock.last_price_at is not None and observed_at <= stock.last_price_at:
                skipped += 1
                continue

            session.add(
                PricePoint(
                    stock_id=stock.id,
                    observed_at=observed_at,
                    price=price,
                    currency=currency,
                )
            )
            stock.last_price = price
            stock.last_price_at = observed_at
            stock.last_currency = currency
            updated += 1
        except Exception:
            failed += 1

    session.commit()
    _mark_updated_now()

    return {"updated": updated, "skipped": skipped, "failed": failed}


def compute_return_pct(purchase_price: float | None, last_price: float | None) -> float | None:
    if not purchase_price or not last_price:
        return None
    return (last_price - purchase_price) / purchase_price * 100.0


def compute_return_abs(purchase_price: float | None, last_price: float | None) -> float | None:
    if purchase_price is None or last_price is None:
        return None
    return last_price - purchase_price
