"""Sector overview: recent moves for the security / quantum universe, and a factor
decomposition of the mega-caps against the pure-play baskets.

Usage: python draft/sectors.py [--days 260] [--window 120] [--csv out.csv]
"""
import argparse

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from universe import UNIVERSE


def fetch_closes(data, symbols, days):
    closes = {}
    for i in range(0, len(symbols), 10):
        chunk = symbols[i:i + 10]
        resp = data.market_data.get_batch_history_bar(chunk, "US_STOCK", "D", count=str(days)).json()
        for item in resp["result"]:
            bars = item.get("result") or []
            closes[item["symbol"]] = pd.Series(
                {pd.Timestamp(b["time"]).tz_convert("America/New_York").date(): float(b["close"]) for b in bars})
    return pd.DataFrame(closes).sort_index()


def overview(closes):
    rows = {}
    for sym in closes:
        s = closes[sym].dropna()
        if len(s) < 2:
            continue
        ret = lambda n: (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else np.nan
        daily = s.pct_change().dropna()
        rows[sym] = {
            "close": s.iloc[-1], "1D%": ret(1), "1W%": ret(5), "1M%": ret(21), "3M%": ret(63), "6M%": ret(126),
            "from52wHigh%": (s.iloc[-1] / s.max() - 1) * 100,
            "vol20d%": daily.tail(20).std() * np.sqrt(252) * 100,
            "bars": len(s),
        }
    return pd.DataFrame(rows).T


def decompose(returns, target, factors):
    """OLS of target daily returns on factor returns. Returns betas and R^2."""
    df = returns[[target] + factors].dropna()
    y = df[target].values
    X = np.column_stack([np.ones(len(df))] + [df[f].values for f in factors])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1 - resid.var() / y.var()
    return dict(zip(factors, beta[1:])), r2, len(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=260)
    parser.add_argument("--window", type=int, default=120, help="trading days used for the decomposition")
    parser.add_argument("--csv")
    args = parser.parse_args()

    meta = pd.DataFrame(UNIVERSE, columns=["symbol", "sector", "group", "note"]).set_index("symbol")
    closes = fetch_closes(DataClient(make_client()), list(meta.index), args.days)
    table = meta.join(overview(closes))
    print(f"Last bar: {closes.index[-1]}\n")
    pd.set_option("display.width", 250, "display.max_rows", 200, "display.float_format", "{:.1f}".format)
    for (sector, group), part in table.groupby(["sector", "group"], sort=False):
        print(f"--- {sector} / {group}")
        print(part.drop(columns=["sector", "group", "note"]).sort_values("1M%", ascending=False).to_string(), "\n")
    if args.csv:
        table.to_csv(args.csv)

    # Equal-weight pure-play baskets, then strip out the market so the factors are sector-specific.
    rets = closes.pct_change().tail(args.window)
    pure = lambda sector: list(meta[(meta.sector == sector) & (meta.group == "pure")].index)
    rets["SEC"] = rets[pure("security")].mean(axis=1)
    rets["QNTM"] = rets[pure("quantum")].mean(axis=1)
    for basket in ("SEC", "QNTM"):
        betas, r2, _ = decompose(rets, basket, ["QQQ"])
        rets[basket + "x"] = rets[basket] - betas["QQQ"] * rets["QQQ"]
        print(f"{basket} basket vs QQQ: beta {betas['QQQ']:.2f}, R2 {r2:.2f}")
    print(f"corr(SECx, QNTMx) = {rets['SECx'].corr(rets['QNTMx']):.2f}\n")

    print(f"--- decomposition over last {args.window} trading days (daily returns)")
    print(f"{'sym':6}{'b_QQQ':>7}{'b_SECx':>8}{'b_QNTMx':>9}{'R2 mkt':>8}{'R2 all':>8}{'+sector':>9}{'idio':>7}")
    for sym in list(meta[meta.group.isin(["mega", "mixed"])].index):
        _, r2_mkt, _ = decompose(rets, sym, ["QQQ"])
        betas, r2_all, n = decompose(rets, sym, ["QQQ", "SECx", "QNTMx"])
        print(f"{sym:6}{betas['QQQ']:7.2f}{betas['SECx']:8.2f}{betas['QNTMx']:9.2f}"
              f"{r2_mkt:8.2f}{r2_all:8.2f}{r2_all - r2_mkt:9.2f}{1 - r2_all:7.2f}")


if __name__ == "__main__":
    main()
