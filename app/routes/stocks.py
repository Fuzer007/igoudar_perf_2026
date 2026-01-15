from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db import SessionLocal
from app.models import PricePoint, Stock
from app.services.updater import compute_return_abs, compute_return_pct
from app.web import templates


router = APIRouter(prefix="/stocks")


@router.get("")
def list_stocks(request: Request):
    session = SessionLocal()
    try:
        stocks = session.execute(select(Stock)).scalars().all()
        rows = []
        for s in stocks:
            rows.append(
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "name": s.name,
                    "industry": s.industry.name if s.industry else None,
                    "purchase_date": s.purchase_date,
                    "purchase_price": s.purchase_price,
                    "last_price": s.last_price,
                    "last_price_at": s.last_price_at,
                    "return_abs": compute_return_abs(s.purchase_price, s.last_price),
                    "return_pct": compute_return_pct(s.purchase_price, s.last_price),
                }
            )

        def _sort_key(r: dict) -> tuple[bool, float, str]:
            rp = r.get("return_pct")
            return (rp is None, -(float(rp) if rp is not None else 0.0), str(r.get("ticker") or ""))

        rows = sorted(rows, key=_sort_key)
        return templates.TemplateResponse("stocks.html", {"request": request, "rows": rows})
    finally:
        session.close()


@router.get("/{stock_id}")
def stock_detail(stock_id: int, request: Request):
    session = SessionLocal()
    try:
        stock = session.get(Stock, stock_id)
        if stock is None:
            raise HTTPException(status_code=404, detail="Stock not found")

        prices = (
            session.execute(
                select(PricePoint)
                .where(PricePoint.stock_id == stock_id)
                .order_by(PricePoint.observed_at.asc())
            )
            .scalars()
            .all()
        )

        chart_points = [
            {"t": p.observed_at.isoformat(), "y": p.price}
            for p in prices
            if p.price is not None
        ]

        return templates.TemplateResponse(
            "stock_detail.html",
            {
                "request": request,
                "stock": stock,
                "prices": prices[-200:],
                "chart_points": chart_points[-500:],
                "return_abs": compute_return_abs(stock.purchase_price, stock.last_price),
                "return_pct": compute_return_pct(stock.purchase_price, stock.last_price),
            },
        )
    finally:
        session.close()
