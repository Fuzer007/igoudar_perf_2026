from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import PricePoint, Stock


def main() -> None:
    session = SessionLocal()
    try:
        total_stocks = session.scalar(select(func.count()).select_from(Stock))
        with_purchase = session.scalar(
            select(func.count()).select_from(Stock).where(Stock.purchase_price.is_not(None))
        )
        with_last = session.scalar(
            select(func.count()).select_from(Stock).where(Stock.last_price.is_not(None))
        )
        pp_count = session.scalar(select(func.count()).select_from(PricePoint))
        latest_pp = session.execute(select(func.max(PricePoint.observed_at))).scalar_one()

        print("stocks_total", total_stocks)
        print("stocks_with_purchase", with_purchase)
        print("stocks_with_last", with_last)
        print("price_points", pp_count)
        print("latest_price_point_at", latest_pp)

        missing = (
            session.execute(
                select(Stock.ticker).where(Stock.last_price.is_(None)).order_by(Stock.ticker.asc())
            )
            .scalars()
            .all()
        )
        print("missing_last_price", len(missing))
        print("missing_tickers_sample", missing[:20])
    finally:
        session.close()


if __name__ == "__main__":
    main()
