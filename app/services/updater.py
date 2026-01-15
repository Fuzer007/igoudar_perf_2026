from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    # Be gentle: single-ticker batches and a small delay.
    series_map = fetch_daily_closes(
        tickers,
        start=start_date,
        end=end_date,
        batch_size=1,
        sleep_seconds=2.0,
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
