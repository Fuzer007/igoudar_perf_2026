#!/usr/bin/env python3
"""
Export local SQLite data to Render's PostgreSQL database.

Usage:
    1. Add PostgreSQL addon on Render Dashboard
    2. Copy the "External Database URL" from Render
    3. Run: python scripts/export_to_postgres.py "postgres://user:pass@host/db"
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Industry, Stock, PricePoint

# Local SQLite database
LOCAL_DB_URL = "sqlite:///./data/app.db"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_to_postgres.py <POSTGRES_URL>")
        print("Get the External Database URL from Render Dashboard → PostgreSQL → Connections")
        sys.exit(1)
    
    postgres_url = sys.argv[1]
    
    # Normalize postgres:// to postgresql://
    if postgres_url.startswith("postgres://"):
        postgres_url = postgres_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif postgres_url.startswith("postgresql://") and "+psycopg" not in postgres_url:
        postgres_url = postgres_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    print(f"Source: {LOCAL_DB_URL}")
    print(f"Target: {postgres_url[:50]}...")
    
    # Connect to local SQLite
    local_engine = create_engine(LOCAL_DB_URL)
    
    # Connect to remote Postgres
    remote_engine = create_engine(postgres_url)
    
    # Create tables on Postgres
    print("\nCreating tables on Postgres...")
    Base.metadata.create_all(remote_engine)
    
    # Export data
    with Session(local_engine) as local_session, Session(remote_engine) as remote_session:
        # Clear existing data on remote (in correct order for foreign keys)
        print("Clearing existing data on Postgres...")
        remote_session.execute(text("DELETE FROM price_points"))
        remote_session.execute(text("DELETE FROM stocks"))
        remote_session.execute(text("DELETE FROM industries"))
        remote_session.commit()
        
        # Copy industries first
        industries = local_session.query(Industry).all()
        print(f"\nExporting {len(industries)} industries...")
        
        industry_id_map = {}  # local_id -> remote_id
        for ind in industries:
            new_industry = Industry(name=ind.name)
            remote_session.add(new_industry)
            remote_session.flush()
            industry_id_map[ind.id] = new_industry.id
            print(f"  {ind.name}")
        remote_session.commit()
        
        # Copy stocks
        stocks = local_session.query(Stock).all()
        print(f"\nExporting {len(stocks)} stocks...")
        
        stock_id_map = {}  # local_id -> remote_id
        for s in stocks:
            new_stock = Stock(
                ticker=s.ticker,
                name=s.name,
                industry_id=industry_id_map[s.industry_id],
                purchase_date=s.purchase_date,
                purchase_price=s.purchase_price,
                purchase_currency=s.purchase_currency,
                last_price=s.last_price,
                last_price_at=s.last_price_at,
                last_currency=s.last_currency,
                active=s.active,
            )
            remote_session.add(new_stock)
            remote_session.flush()
            stock_id_map[s.id] = new_stock.id
            print(f"  {s.ticker}: purchase={s.purchase_price}, last={s.last_price}")
        remote_session.commit()
        
        # Copy price points
        price_points = local_session.query(PricePoint).all()
        print(f"\nExporting {len(price_points)} price points...")
        
        batch_size = 500
        for i, pp in enumerate(price_points):
            remote_session.add(PricePoint(
                stock_id=stock_id_map[pp.stock_id],
                observed_at=pp.observed_at,
                price=pp.price,
                currency=pp.currency,
            ))
            if (i + 1) % batch_size == 0:
                remote_session.commit()
                print(f"  {i + 1}/{len(price_points)} exported...")
        
        remote_session.commit()
        print(f"  {len(price_points)}/{len(price_points)} exported!")
    
    print("\n✅ Export complete!")
    print("\nNext steps:")
    print("1. On Render Dashboard, set DATABASE_URL to the Internal Database URL")
    print("2. Redeploy your app - it will now use Postgres with all your data!")


if __name__ == "__main__":
    main()
