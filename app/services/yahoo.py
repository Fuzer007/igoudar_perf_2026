from __future__ import annotations

import datetime as dt

import pandas as pd
import requests_cache
import yfinance as yf


import os
import random

_cached_session = requests_cache.CachedSession(
    cache_name="data/yfinance_cache",
    backend="sqlite",
    expire_after=60 * 30,
)


# Configurable via environment for tuning on different hosts
DEFAULT_BATCH_SIZE = int(os.getenv("YF_BATCH_SIZE", "10"))
DEFAULT_BATCH_SLEEP_SECONDS = float(os.getenv("YF_SLEEP_SECONDS", "3.0"))


def _download_with_retries(**kwargs):
    """Download with exponential backoff and jitter to avoid rate limits."""
    import time
    last_exc: Exception | None = None
    for attempt, base_delay in enumerate((0, 5, 15, 45)):
        try:
            if base_delay:
                # Add jitter: 50-150% of base delay
                jitter = base_delay * (0.5 + random.random())
                time.sleep(jitter)
            return yf.download(session=_cached_session, **kwargs)
        except Exception as exc:
            msg = str(exc)
            if "Rate limited" in msg or "Too Many Requests" in msg:
                # Longer cooldown on rate limit
                time.sleep(60 + random.randint(0, 30))
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    return None


def _chunked(seq: list[str], n: int) -> list[list[str]]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def _single_history_daily(
    ticker: str,
    *,
    start: dt.date,
    end: dt.date,
) -> list[tuple[dt.datetime, float, str | None]]:
    try:
        t = yf.Ticker(ticker, session=_cached_session)
        df = t.history(start=start, end=end, interval="1d", auto_adjust=False)
    except Exception:
        return []
    if df is None or df.empty or "Close" not in df.columns:
        return []
    series = df["Close"].dropna()
    if series.empty:
        return []
    points: list[tuple[dt.datetime, float, str | None]] = []
    for idx, value in series.items():
        observed_at = _ensure_tz(pd.Timestamp(idx).to_pydatetime())
        points.append((observed_at, float(value), None))
    return points


def _ensure_tz(ts: dt.datetime) -> dt.datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=dt.timezone.utc)


def _close_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of Close prices with columns = tickers."""
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" not in df.columns.get_level_values(0):
            return pd.DataFrame(index=df.index)
        close = df["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame()
        return close
    if "Close" not in df.columns:
        return pd.DataFrame(index=df.index)
    close = df[["Close"]].copy()
    close.columns = ["Close"]
    return close


def fetch_latest_prices(
    tickers: list[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_seconds: float = DEFAULT_BATCH_SLEEP_SECONDS,
) -> dict[str, tuple[dt.datetime, float, str | None]]:
    """Batch fetch best-effort latest close from recent hourly bars."""
    if not tickers:
        return {}
    out: dict[str, tuple[dt.datetime, float, str | None]] = {}
    import time

    for batch in _chunked(tickers, max(1, int(batch_size))):
        try:
            df = _download_with_retries(
                tickers=batch,
                period="2d",
                interval="1h",
                progress=False,
                auto_adjust=False,
                threads=False,
                group_by="column",
            )
        except Exception:
            continue

        if df is None or df.empty:
            time.sleep(sleep_seconds)
            continue

        close = _close_frame(df)
        if close.empty:
            time.sleep(sleep_seconds + random.uniform(0, sleep_seconds))
            continue

        for ticker in close.columns:
            series = close[ticker].dropna()
            if series.empty:
                continue
            observed_at = _ensure_tz(pd.Timestamp(series.index[-1]).to_pydatetime())
            out[str(ticker)] = (observed_at, float(series.iloc[-1]), None)

        time.sleep(sleep_seconds + random.uniform(0, sleep_seconds))

    return out


def fetch_purchase_closes_on_or_after(
    tickers: list[str],
    purchase_date: dt.date,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_seconds: float = DEFAULT_BATCH_SLEEP_SECONDS,
) -> dict[str, tuple[dt.datetime, float, str | None]]:
    """Batch fetch first available daily close on/after purchase_date."""
    if not tickers:
        return {}

    start = purchase_date
    end = purchase_date + dt.timedelta(days=7)
    out: dict[str, tuple[dt.datetime, float, str | None]] = {}
    import time

    for batch in _chunked(tickers, max(1, int(batch_size))):
        try:
            df = _download_with_retries(
                tickers=batch,
                start=start,
                end=end,
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
                group_by="column",
            )
        except Exception:
            continue

        if df is None or df.empty:
            time.sleep(sleep_seconds)
            continue

        close = _close_frame(df)
        if close.empty:
            time.sleep(sleep_seconds)
            continue

        for ticker in close.columns:
            series = close[ticker].dropna()
            if series.empty:
                continue
            observed_at = _ensure_tz(pd.Timestamp(series.index[0]).to_pydatetime())
            out[str(ticker)] = (observed_at, float(series.iloc[0]), None)

        time.sleep(sleep_seconds)

    return out


def fetch_daily_closes(
    tickers: list[str],
    start: dt.date,
    end: dt.date | None = None,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_seconds: float = DEFAULT_BATCH_SLEEP_SECONDS,
) -> dict[str, list[tuple[dt.datetime, float, str | None]]]:
    """Batch fetch daily closes for tickers between start and end.

    Returns a dict: ticker -> list of (observed_at, close, currency).
    """
    if not tickers:
        return {}

    end_dt = end
    if end_dt is None:
        end_dt = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1))

    out: dict[str, list[tuple[dt.datetime, float, str | None]]] = {}
    import time

    for batch in _chunked(tickers, max(1, int(batch_size))):
        try:
            df = _download_with_retries(
                tickers=batch,
                start=start,
                end=end_dt,
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
                group_by="column",
            )
        except Exception:
            continue

        if df is None or df.empty:
            # Fallback: for single tickers, try the alternate history() endpoint.
            if len(batch) == 1:
                ticker = batch[0]
                points = _single_history_daily(ticker, start=start, end=end_dt)
                if points:
                    out[ticker] = points
            time.sleep(sleep_seconds)
            continue

        close = _close_frame(df)
        if close.empty:
            if len(batch) == 1:
                ticker = batch[0]
                points = _single_history_daily(ticker, start=start, end=end_dt)
                if points:
                    out[ticker] = points
            time.sleep(sleep_seconds)
            continue

        for ticker in close.columns:
            series = close[ticker].dropna()
            if series.empty:
                continue
            points: list[tuple[dt.datetime, float, str | None]] = []
            for idx, value in series.items():
                observed_at = _ensure_tz(pd.Timestamp(idx).to_pydatetime())
                points.append((observed_at, float(value), None))
            out[str(ticker)] = points

        time.sleep(sleep_seconds)

    return out
