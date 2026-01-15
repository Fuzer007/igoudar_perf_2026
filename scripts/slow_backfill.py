#!/usr/bin/env python
"""Slow backfill script that fetches one ticker at a time with delays to avoid rate limits."""
import time
import random
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
from datetime import date, datetime, timezone, timedelta
from app.db import SessionLocal
from app.models import Stock, PricePoint
from sqlalchemy import select

def main():
    session = SessionLocal()
    stocks = session.execute(select(Stock).where(Stock.active == True)).scalars().all()

    print(f'Fetching data for {len(stocks)} stocks one at a time with delays...')
    start_date = date(2026, 1, 2)
    end_date = date.today() + timedelta(days=1)
    success = 0
    failed = 0

    for i, stock in enumerate(stocks):
        print(f'[{i+1}/{len(stocks)}] {stock.ticker}...', end=' ', flush=True)
        try:
            # Wait 5-8 seconds between each ticker
            time.sleep(5 + random.uniform(0, 3))
            t = yf.Ticker(stock.ticker)
            df = t.history(start=start_date, end=end_date, interval='1d', auto_adjust=False)
            
            if df is None or df.empty or 'Close' not in df.columns:
                print('no data')
                failed += 1
                continue
            
            # Get existing timestamps to avoid duplicates
            existing = set()
            for pp in stock.prices:
                existing.add(pp.observed_at)
            
            inserted = 0
            for idx, row in df.iterrows():
                observed_at = idx.to_pydatetime()
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=timezone.utc)
                observed_at = observed_at.replace(tzinfo=None, microsecond=0)
                
                if observed_at in existing:
                    continue
                
                price = float(row['Close'])
                session.add(PricePoint(stock_id=stock.id, observed_at=observed_at, price=price))
                existing.add(observed_at)
                inserted += 1
                
                # Set purchase price if needed
                if stock.purchase_price is None and observed_at.date() >= stock.purchase_date:
                    stock.purchase_price = price
                
                # Update last price
                if stock.last_price_at is None or observed_at >= stock.last_price_at:
                    stock.last_price = price
                    stock.last_price_at = observed_at
            
            session.commit()
            print(f'+{inserted}')
            success += 1
        except Exception as e:
            print(f'error: {e}')
            failed += 1

    session.close()
    print(f'\nDone: {success} succeeded, {failed} failed')


if __name__ == '__main__':
    main()
