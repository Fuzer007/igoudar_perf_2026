from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from app.db import SessionLocal
from app.models import Industry, Stock
from app.services.updater import (
    backfill_daily_history,
    compute_return_abs,
    compute_return_pct,
    update_all_prices,
)
from app.web import templates


router = APIRouter()


@router.get("/")
def home(request: Request):
    session = SessionLocal()
    try:
        stocks = session.query(Stock).all()
        industries = session.query(Industry).all()

        with_perf = []
        for s in stocks:
            with_perf.append(
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "name": s.name,
                    "industry": s.industry.name if s.industry else None,
                    "purchase_price": s.purchase_price,
                    "last_price": s.last_price,
                    "return_abs": compute_return_abs(s.purchase_price, s.last_price),
                    "return_pct": compute_return_pct(s.purchase_price, s.last_price),
                }
            )

        missing = [
            s.ticker
            for s in stocks
            if (s.purchase_price is None) or (s.last_price is None)
        ]

        industry_rows = []
        for ind in industries:
            ind_stocks = [s for s in stocks if s.industry_id == ind.id]
            returns = [compute_return_pct(s.purchase_price, s.last_price) for s in ind_stocks]
            returns = [r for r in returns if r is not None]
            avg_return = (sum(returns) / len(returns)) if returns else None
            priced_in_industry = len([s for s in ind_stocks if s.last_price is not None])
            industry_rows.append(
                {
                    "id": ind.id,
                    "name": ind.name,
                    "stock_count": len(ind_stocks),
                    "priced_count": priced_in_industry,
                    "avg_return_pct": avg_return,
                }
            )

        def _stock_sort_key(r: dict) -> tuple[bool, float, str]:
            rp = r.get("return_pct")
            return (rp is None, -(float(rp) if rp is not None else 0.0), str(r.get("ticker") or ""))

        def _industry_sort_key(r: dict) -> tuple[bool, float, str]:
            rp = r.get("avg_return_pct")
            return (rp is None, -(float(rp) if rp is not None else 0.0), str(r.get("name") or ""))

        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "stock_count": len(stocks),
                "industry_count": len(industries),
                "priced_count": len([s for s in stocks if s.last_price is not None]),
                "missing_count": len(missing),
                "missing_tickers": ", ".join(sorted(missing)) if missing else "",
                "industry_rows": sorted(industry_rows, key=_industry_sort_key),
                "top": sorted(
                    [x for x in with_perf if x["return_pct"] is not None],
                    key=lambda x: x["return_pct"],
                    reverse=True,
                )[:5],
                "rows": sorted(with_perf, key=_stock_sort_key),
            },
        )
    finally:
        session.close()


@router.get("/update-now")
def update_now(request: Request):
    session = SessionLocal()
    try:
        update_all_prices(session, force=True)
    finally:
        session.close()
    return RedirectResponse(url="/", status_code=303)


@router.get("/backfill-now")
def backfill_now(request: Request):
    session = SessionLocal()
    try:
        backfill_daily_history(session, only_missing=True)
    finally:
        session.close()
    return RedirectResponse(url="/", status_code=303)
