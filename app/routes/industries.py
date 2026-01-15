from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Industry, Stock
from app.services.updater import compute_return_pct
from app.web import templates


router = APIRouter(prefix="/industries")


@router.get("")
def list_industries(request: Request):
    session = SessionLocal()
    try:
        industries = session.execute(select(Industry)).scalars().all()
        rows = []
        for ind in industries:
            stocks = session.execute(select(Stock).where(Stock.industry_id == ind.id)).scalars().all()
            rets = [compute_return_pct(s.purchase_price, s.last_price) for s in stocks]
            rets = [r for r in rets if r is not None]
            avg = sum(rets) / len(rets) if rets else None
            rows.append(
                {
                    "id": ind.id,
                    "name": ind.name,
                    "stock_count": len(stocks),
                    "avg_return_pct": avg,
                }
            )

        def _sort_key(r: dict) -> tuple[bool, float, str]:
            rp = r.get("avg_return_pct")
            return (rp is None, -(float(rp) if rp is not None else 0.0), str(r.get("name") or ""))

        rows = sorted(rows, key=_sort_key)
        return templates.TemplateResponse("industries.html", {"request": request, "rows": rows})
    finally:
        session.close()


@router.get("/{industry_id}")
def industry_detail(industry_id: int, request: Request):
    session = SessionLocal()
    try:
        ind = session.get(Industry, industry_id)
        if ind is None:
            raise HTTPException(status_code=404, detail="Industry not found")
        stocks = session.execute(select(Stock).where(Stock.industry_id == ind.id)).scalars().all()
        rows = []
        for s in stocks:
            rows.append(
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "name": s.name,
                    "purchase_price": s.purchase_price,
                    "last_price": s.last_price,
                    "return_pct": compute_return_pct(s.purchase_price, s.last_price),
                }
            )
        rows = sorted(
            rows,
            key=lambda r: (
                r["return_pct"] is None,
                -(float(r["return_pct"]) if r["return_pct"] is not None else 0.0),
                r["ticker"],
            ),
        )
        rets = [r["return_pct"] for r in rows if r["return_pct"] is not None]
        avg = sum(rets) / len(rets) if rets else None
        return templates.TemplateResponse(
            "industry_detail.html",
            {"request": request, "industry": ind, "rows": rows, "avg_return_pct": avg},
        )
    finally:
        session.close()
