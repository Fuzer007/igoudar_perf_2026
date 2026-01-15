# Stock Performance Tracker (Jan 2, 2026 →)

Tracks a set of stocks, stores hourly price snapshots, and shows performance vs the initial purchase price and by industry.

## Features

- FastAPI web app + Jinja2 UI
- SQLite database (stored in `./data/app.db`)
- Hourly price updater (in-process scheduler) using `yfinance`
- Seeded industries + your Technology stock list
- Performance views: per-stock and aggregated by industry

## Quickstart

1) Create a virtualenv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Run the app:

```bash
uvicorn app.main:app --reload
```

3) Open:

- http://127.0.0.1:8000/

## Config

Copy `.env.example` to `.env` (optional). Defaults work out of the box.

Key variables:

- `DATABASE_URL` (default: `sqlite:///./data/app.db`)
- `UPDATE_INTERVAL_MINUTES` (default: `60`)

## Notes

- If a stock has no `purchase_price`, the app will auto-fill it using the first available close on or after `2026-01-02`.
- Some tickers may not be available on Yahoo Finance (e.g., older delisted symbols). Those will be skipped during updates.
