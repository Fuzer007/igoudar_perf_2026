"""Finnhub API service for fetching stock prices.

Free tier: 60 calls/minute - plenty for 32 stocks.
Works from cloud servers (Render, etc).
"""
from __future__ import annotations

import os
import time
import requests
from datetime import datetime, timezone

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "d4jjfkhr01qgcb0tlt50d4jjfkhr01qgcb0tlt5g")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_quote(ticker: str) -> dict | None:
    """Get current quote for a single ticker.
    
    Returns dict with keys: c (current), h (high), l (low), o (open), pc (previous close), t (timestamp)
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/quote",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        # Finnhub returns {"c":0,"d":null,"dp":null,...} for invalid tickers
        if data.get("c") == 0 and data.get("t") == 0:
            return None
        
        return data
    except Exception as e:
        print(f"[finnhub] Error fetching {ticker}: {e}")
        return None


def get_quotes_batch(tickers: list[str], delay_between: float = 0.5) -> dict[str, dict]:
    """Get quotes for multiple tickers with rate limiting.
    
    Returns dict mapping ticker -> quote data
    """
    results = {}
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(delay_between)  # Rate limit: 60/min = 1/sec max
        
        quote = get_quote(ticker)
        if quote:
            results[ticker] = quote
    
    return results


def get_candles(ticker: str, from_ts: int, to_ts: int, resolution: str = "D") -> list[tuple] | None:
    """Get historical candles for a ticker.
    
    Args:
        ticker: Stock symbol
        from_ts: Unix timestamp start
        to_ts: Unix timestamp end
        resolution: D=daily, W=weekly, M=monthly, 1/5/15/30/60=minutes
    
    Returns list of (timestamp, open, high, low, close, volume) tuples
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/candle",
            params={
                "symbol": ticker,
                "resolution": resolution,
                "from": from_ts,
                "to": to_ts,
                "token": FINNHUB_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("s") == "no_data":
            return None
        
        candles = []
        for i in range(len(data.get("t", []))):
            candles.append((
                data["t"][i],  # timestamp
                data["o"][i],  # open
                data["h"][i],  # high
                data["l"][i],  # low
                data["c"][i],  # close
                data["v"][i],  # volume
            ))
        
        return candles
    except Exception as e:
        print(f"[finnhub] Error fetching candles for {ticker}: {e}")
        return None
