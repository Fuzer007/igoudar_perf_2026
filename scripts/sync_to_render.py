#!/usr/bin/env python3
"""
Fetch latest prices locally and sync to Render's PostgreSQL.

Usage:
    python scripts/sync_to_render.py "postgres://user:pass@host/db"
    
    Or set RENDER_DATABASE_URL environment variable:
    export RENDER_DATABASE_URL="postgres://..."
    python scripts/sync_to_render.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Base, Industry, Stock, PricePoint
from app.services.updater import slow_update_prices

LOCAL_DB_URL = "sqlite:///./data/app.db"


def normalize_postgres_url(url: str) -> str:
    """Normalize postgres:// to postgresql+psycopg://"""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def sync_to_postgres(postgres_url: str):
    """Sync local SQLite data to Render's Postgres."""
    postgres_url = normalize_postgres_url(postgres_url)
    
    print(f"\n📤 Syncing to Postgres...")
    
    local_engine = create_engine(LOCAL_DB_URL)
    remote_engine = create_engine(postgres_url)
    
    with Session(local_engine) as local_session, Session(remote_engine) as remote_session:
        # Sync stocks (update existing, prices and timestamps)
        local_stocks = local_session.query(Stock).all()
        
        for ls in local_stocks:
            # Update remote stock with latest price info
            remote_session.execute(
                text("""
                    UPDATE stocks 
                    SET last_price = :last_price,
                        last_price_at = :last_price_at,
                        purchase_price = COALESCE(purchase_price, :purchase_price)
                    WHERE ticker = :ticker
                """),
                {
                    "ticker": ls.ticker,
                    "last_price": ls.last_price,
                    "last_price_at": ls.last_price_at,
                    "purchase_price": ls.purchase_price,
                }
            )
        
        # Sync new price points
        # Get max timestamp per stock from remote
        remote_max_times = {}
        rows = remote_session.execute(
            text("SELECT stock_id, MAX(observed_at) as max_time FROM price_points GROUP BY stock_id")
        ).fetchall()
        for row in rows:
            remote_max_times[row[0]] = row[1]
        
        # Get ticker to remote stock_id mapping
        ticker_to_remote_id = {}
        for row in remote_session.execute(text("SELECT id, ticker FROM stocks")).fetchall():
            ticker_to_remote_id[row[1]] = row[0]
        
        # Insert new price points
        new_points = 0
        for ls in local_stocks:
            remote_stock_id = ticker_to_remote_id.get(ls.ticker)
            if not remote_stock_id:
                continue
                
            remote_max = remote_max_times.get(remote_stock_id)
            
            for pp in ls.prices:
                # Skip if already exists (based on timestamp)
                if remote_max and pp.observed_at <= remote_max:
                    continue
                
                remote_session.execute(
                    text("""
                        INSERT INTO price_points (stock_id, observed_at, price, currency)
                        VALUES (:stock_id, :observed_at, :price, :currency)
                        ON CONFLICT (stock_id, observed_at) DO NOTHING
                    """),
                    {
                        "stock_id": remote_stock_id,
                        "observed_at": pp.observed_at,
                        "price": pp.price,
                        "currency": pp.currency,
                    }
                )
                new_points += 1
        
        remote_session.commit()
        print(f"✅ Synced {len(local_stocks)} stocks, {new_points} new price points")


def main():
    # Get Postgres URL from arg or environment
    if len(sys.argv) >= 2:
        postgres_url = sys.argv[1]
    else:
        postgres_url = os.environ.get("RENDER_DATABASE_URL")
    
    if not postgres_url:
        print("Usage: python scripts/sync_to_render.py <POSTGRES_URL>")
        print("Or set RENDER_DATABASE_URL environment variable")
        sys.exit(1)
    
    # Step 1: Fetch latest prices locally
    print("📊 Fetching latest prices from Yahoo Finance...")
    with SessionLocal() as session:
        result = slow_update_prices(session, delay_seconds=5.0)
        print(f"✅ Updated: {result['updated']}, Skipped: {result['skipped']}, Failed: {result['failed']}")
    
    # Step 2: Sync to Render's Postgres
    sync_to_postgres(postgres_url)
    
    print("\n🎉 Done! Your Render app now has the latest data.")


if __name__ == "__main__":
    main()
