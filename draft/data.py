"""Fetch and cache daily bars and quarterly income statements from Webull.

Cache lives in draft/cache/ (git-ignored). Delete it, or pass refresh=True, to re-download.
"""
import os

import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
MAX_BARS = 1200  # API limit per request (~4.75 years of daily bars)


def _client():
    return DataClient(make_client())


def load_bars(symbols, refresh=False):
    """Daily OHLCV, forward-adjusted. Returns {field: DataFrame[date x symbol]}."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "bars.pkl")
    cached = pd.read_pickle(path) if os.path.exists(path) and not refresh else None
    have = set(cached["close"].columns) if cached is not None else set()
    missing = [s for s in symbols if s not in have]
    if missing:
        data, rows = _client(), []
        for i in range(0, len(missing), 5):
            resp = data.market_data.get_batch_history_bar(missing[i:i + 5], "US_STOCK", "D", count=str(MAX_BARS)).json()
            for item in resp["result"]:
                for b in item.get("result") or []:
                    day = pd.Timestamp(b["time"]).tz_convert("America/New_York").normalize().tz_localize(None)
                    rows.append((day, item["symbol"], float(b["open"]), float(b["high"]), float(b["low"]),
                                 float(b["close"]), float(b["volume"])))
        long = pd.DataFrame(rows, columns=["date", "symbol", "open", "high", "low", "close", "volume"])
        fresh = {f: long.pivot(index="date", columns="symbol", values=f) for f in ("open", "high", "low", "close", "volume")}
        cached = fresh if cached is None else {f: cached[f].join(fresh[f], how="outer") for f in fresh}
        pd.to_pickle(cached, path)
    return {f: df[[s for s in symbols if s in df]].sort_index() for f, df in cached.items()}


def load_income(symbols, refresh=False):
    """Quarterly income statements (up to 20 quarters) with publish dates. Long DataFrame."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "income.pkl")
    cached = pd.read_pickle(path) if os.path.exists(path) and not refresh else pd.DataFrame()
    have = set(cached["symbol"]) if len(cached) else set()
    missing = [s for s in symbols if s not in have]
    if missing:
        data, rows = _client(), []
        for sym in missing:
            try:
                quarters = data.fundamentals.get_financials_income(sym, type="QUARTERLY", count=20).json() or []
            except Exception:
                quarters = []
            for q in quarters:
                rows.append({"symbol": sym, "fiscal_year": q.get("fiscal_year"), "fiscal_period": q.get("fiscal_period"),
                             "end_date": q.get("end_date"), "publish_date": q.get("publish_date"),
                             "revenue": q.get("total_revenue"), "op_income": q.get("op_income"),
                             "net_income": q.get("net_income")})
        fresh = pd.DataFrame(rows)
        if len(fresh):
            for col in ("revenue", "op_income", "net_income"):
                fresh[col] = pd.to_numeric(fresh[col], errors="coerce")
            for col in ("end_date", "publish_date"):
                fresh[col] = pd.to_datetime(fresh[col], errors="coerce")
            cached = pd.concat([cached, fresh], ignore_index=True)
            pd.to_pickle(cached, path)
    return cached[cached["symbol"].isin(symbols)].copy() if len(cached) else cached


def load_intraday(symbols, timespan="M30", refresh=False):
    """Regular-session intraday bars, as far back as the API allows (180 days for minute bars).

    Returns {field: DataFrame[bar start, New York time x symbol]} for open, high, low, close, volume.
    """
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"intraday_{timespan}.pkl")
    cached = pd.read_pickle(path) if os.path.exists(path) and not refresh else None
    have = set(cached["close"].columns) if cached is not None else set()
    missing = [s for s in symbols if s not in have]
    if missing:
        data, rows = _client(), []
        floor_ms = int((pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=178)).timestamp() * 1000)
        for sym in missing:
            end = None
            for _ in range(6):                                  # page backwards until the 180-day limit
                kwargs = {"end_time": end} if end else {}
                try:
                    resp = data.market_data.get_history_bar(sym, "US_STOCK", timespan, count=str(MAX_BARS), **kwargs).json()
                except Exception:
                    break
                bars = (resp["result"][0].get("result") if isinstance(resp, dict) else resp) or []
                if not bars:
                    break
                for b in bars:
                    rows.append((pd.Timestamp(b["time"]).tz_convert("America/New_York").tz_localize(None), sym,
                                 float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"]), float(b["volume"])))
                earliest = int(min(pd.Timestamp(b["time"]).timestamp() for b in bars) * 1000)
                if len(bars) < MAX_BARS or earliest - 1 <= floor_ms:
                    break
                end = earliest - 1
        long = pd.DataFrame(rows, columns=["time", "symbol", "open", "high", "low", "close", "volume"]).drop_duplicates(["time", "symbol"])
        fresh = {f: long.pivot(index="time", columns="symbol", values=f) for f in ("open", "high", "low", "close", "volume")}
        cached = fresh if cached is None else {f: cached[f].join(fresh[f], how="outer") for f in fresh}
        pd.to_pickle(cached, path)
    return {f: df[[s for s in symbols if s in df]].sort_index() for f, df in cached.items()}
