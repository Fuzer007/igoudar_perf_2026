from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Industry, Stock


PURCHASE_DATE = dt.date(2026, 1, 2)


def seed_defaults(session: Session) -> None:
    def ensure_industry(name: str) -> Industry:
        ind = session.execute(select(Industry).where(Industry.name == name)).scalar_one_or_none()
        if ind is None:
            ind = Industry(name=name)
            session.add(ind)
            session.flush()
        return ind

    # Note: "Sandisk" is not a currently traded standalone ticker in many markets.
    # Keeping SNDK as a best-effort; if Yahoo has no data it will be skipped during updates.
    seed_data: dict[str, list[tuple[str, str]]] = {
        "Technology": [
            ("GOOGL", "Google"),
            ("NVDA", "Nvidia"),
            ("MU", "Micron"),
            ("WDC", "Western Digital"),
            ("STX", "Seagate"),
            ("AVGO", "Broadcom"),
            ("KLAC", "KLA"),
            ("LRCX", "Lam Research"),
            ("MSFT", "Microsoft"),
            ("APP", "AppLovin"),
            ("PLTR", "Palantir"),
            ("SNDK", "Sandisk"),
            ("CLS", "Celestica"),
            ("TSM", "TSMC"),
            ("INTC", "Intel"),
        ],
        "Industrials": [
            ("CAT", "Caterpillar"),
            ("BWXT", "BWX Technologies"),
            ("HWM", "Howmet Aerospace"),
            ("GE", "General Electric"),
        ],
        "Financials": [
            ("JPM", "JPMorgan"),
            ("BAC", "Bank of America"),
            ("HOOD", "Robinhood"),
            ("MS", "Morgan Stanley"),
            ("AXP", "American Express"),
            ("V", "Visa"),
            ("ALLY", "Ally"),
        ],
        "Healthcare": [
            ("ISRG", "Intuitive Surgical"),
            ("JNJ", "Johnson & Johnson"),
            ("LLY", "Eli Lilly"),
            ("VKTX", "Viking Therapeutics"),
            ("DVAX", "Dynavax"),
            ("OMER", "Omeros"),
        ],
    }

    existing_tickers = {t for (t,) in session.execute(select(Stock.ticker)).all()}

    for industry_name, stocks in seed_data.items():
        industry = ensure_industry(industry_name)
        for ticker, name in stocks:
            if ticker in existing_tickers:
                continue
            session.add(
                Stock(
                    ticker=ticker,
                    name=name,
                    industry_id=industry.id,
                    purchase_date=PURCHASE_DATE,
                    purchase_price=None,
                )
            )
            existing_tickers.add(ticker)
