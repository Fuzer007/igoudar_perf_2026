from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Industry, Stock
from app.services.updater import backfill_daily_history, compute_return_abs, compute_return_pct, slow_update_prices


router = APIRouter(prefix="/api", tags=["api"])


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            # Treat naive datetimes as UTC for display.
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.isoformat()
    return str(value)


@router.get("/summary")
def summary() -> dict:
    session = SessionLocal()
    try:
        stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()  # noqa: E712
        industries = session.execute(select(Industry)).scalars().all()

        stock_rows: list[dict] = []
        for s in stocks:
            stock_rows.append(
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "name": s.name,
                    "industry": s.industry.name if s.industry else None,
                    "purchase_date": _iso(s.purchase_date),
                    "purchase_price": s.purchase_price,
                    "last_price": s.last_price,
                    "last_price_at": _iso(s.last_price_at),
                    "return_abs": compute_return_abs(s.purchase_price, s.last_price),
                    "return_pct": compute_return_pct(s.purchase_price, s.last_price),
                }
            )

        stock_rows = sorted(
            stock_rows,
            key=lambda r: (
                r["return_pct"] is None,
                -(float(r["return_pct"]) if r["return_pct"] is not None else 0.0),
                r["ticker"],
            ),
        )

        industry_rows: list[dict] = []
        for ind in industries:
            ind_stocks = [s for s in stocks if s.industry_id == ind.id]
            rets = [compute_return_pct(s.purchase_price, s.last_price) for s in ind_stocks]
            rets = [r for r in rets if r is not None]
            avg = (sum(rets) / len(rets)) if rets else None
            industry_rows.append(
                {
                    "id": ind.id,
                    "name": ind.name,
                    "stock_count": len(ind_stocks),
                    "avg_return_pct": avg,
                }
            )

        industry_rows = sorted(
            industry_rows,
            key=lambda r: (
                r["avg_return_pct"] is None,
                -(float(r["avg_return_pct"]) if r["avg_return_pct"] is not None else 0.0),
                r["name"],
            ),
        )

        return {
            "now_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "stocks": stock_rows,
            "industries": industry_rows,
        }
    finally:
        session.close()


@router.post("/actions/update")
def action_update() -> dict:
    """Slow but reliable price update (one ticker at a time with delays)."""
    session = SessionLocal()
    try:
        result = slow_update_prices(session, delay_seconds=5.0)
        return {"ok": True, "result": result}
    finally:
        session.close()


@router.post("/actions/backfill")
def action_backfill(*, only_missing: bool = True) -> dict:
    """Best-effort daily backfill. `only_missing=true` targets tickers missing pricing."""
    session = SessionLocal()
    try:
        result = backfill_daily_history(session, only_missing=only_missing)
        return {"ok": True, "result": result}
    finally:
        session.close()
