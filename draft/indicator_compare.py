"""Which yardstick best tells "stretched" from "cheap" on a name that spikes?

Every indicator drives the same savings plan (one unit a week): pause buying when the indicator is in
the top `pause` share of its own trailing two years, sell 20% of the holding when it is in the top
`sell` share. Because each indicator is ranked against its own history, they are compared on equal
terms: the only difference is what each one measures.

  price vs average   z-score and % gap to the 50 / 100 / 200-day average
  momentum           14-day RSI, 3-month return
  valuation          P/S (price / trailing-12-month sales per share), P/B (price / book value per share),
                     both using only figures already published on each day

Usage: python draft/indicator_compare.py [--start 2025-01-01] [--end 2026-11-13] [SYMBOL ...]
"""
import argparse
import os

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from data import CACHE, load_bars

SLIP = 0.0005
LEVELS = {"top 30% / top 10%": (0.70, 0.90), "top 20% / top 5%": (0.80, 0.95), "top 10% / top 2.5%": (0.90, 0.975)}


def load_per_share(symbols):
    """Published sales per share (trailing 12 months) and book value per share, by publish date."""
    path = os.path.join(CACHE, "per_share.pkl")
    cached = pd.read_pickle(path) if os.path.exists(path) else {}
    missing = [s for s in symbols if s not in cached]
    if missing:
        data = DataClient(make_client())
        for sym in missing:
            inc = pd.DataFrame(data.fundamentals.get_financials_income(sym, type="QUARTERLY", count=20).json())
            bal = pd.DataFrame(data.fundamentals.get_financials_balance_sheet(sym, type="QUARTERLY", count=20).json())
            inc = inc.assign(pub=pd.to_datetime(inc.publish_date), end=pd.to_datetime(inc.end_date)).sort_values("end")
            sps = (pd.to_numeric(inc.total_revenue) / pd.to_numeric(inc.diluted_avg_shares)).rolling(4).sum()
            bal = bal.assign(pub=pd.to_datetime(bal.publish_date), end=pd.to_datetime(bal.end_date)).sort_values("end")
            bps = pd.to_numeric(bal.total_sh_equity) / pd.to_numeric(bal.common_shares_out)
            cached[sym] = {"sps": pd.Series(sps.values, index=inc.pub.values).dropna().groupby(level=0).last().sort_index(),
                           "bps": pd.Series(bps.values, index=bal.pub.values).dropna().groupby(level=0).last().sort_index()}
        pd.to_pickle(cached, path)
    return cached


def as_of(series, index):
    """Value published strictly before each day."""
    return series.reindex(index.union(series.index)).ffill().shift(1).reindex(index)


def indicators(close, per_share):
    logp = np.log(close)
    out = {}
    for n in (50, 100, 200):
        out[f"z-score vs {n}-day avg"] = (logp - logp.rolling(n).mean()) / logp.rolling(n).std()
        out[f"% above {n}-day avg"] = close / close.rolling(n).mean() - 1
    delta = close.diff()
    gain, loss = delta.clip(lower=0).ewm(alpha=1 / 14).mean(), (-delta.clip(upper=0)).ewm(alpha=1 / 14).mean()
    out["RSI (14 days)"] = 100 - 100 / (1 + gain / loss)
    out["3-month return"] = close.pct_change(63)
    out["P/S"] = close / as_of(per_share["sps"], close.index)
    book = as_of(per_share["bps"], close.index)
    out["P/B"] = (close / book).where(book > 0)
    return {name: s.shift(1) for name, s in out.items()}       # known before the open


def trailing_rank(series, window=500, min_periods=250):
    return series.rolling(window, min_periods=min_periods).apply(lambda w: (w <= w[-1]).mean(), raw=True)


def simulate(open_, close, rank, start, end, pause, sell, frac=0.2):
    days = close.loc[start:end].index
    week = pd.Series(days.isocalendar().week.values.astype(int), index=days)
    buy_days = set(days[(week != week.shift()).values])
    shares = cash = paid = 0.0
    wealth, sells = [], []
    for day in days:
        if day in buy_days:
            cash += 1.0
            paid += 1.0
            r, px = rank.get(day, np.nan), open_[day]
            if not np.isnan(r) and r >= sell and shares > 0:
                cash += shares * frac * px * (1 - SLIP)
                shares *= 1 - frac
                sells.append(day)
            elif np.isnan(r) or r < pause:
                spend = min(cash, 2.0)
                shares += spend / (px * (1 + SLIP))
                cash -= spend
        wealth.append((shares * close[day] + cash, paid))
    w = pd.DataFrame(wealth, index=days, columns=["wealth", "paid"])
    return {"multiple": w.wealth.iloc[-1] / w.paid.iloc[-1], "max fall%": (w.wealth / w.wealth.cummax() - 1).min() * 100, "sells": sells}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", default=["IONQ", "RGTI", "QBTS", "QUBT"])
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-11-13")
    args = parser.parse_args()
    bars = load_bars(args.symbols)
    per_share = load_per_share(args.symbols)
    pd.set_option("display.width", 230, "display.float_format", "{:.2f}".format)

    rows, sells_log, plain = [], {}, {}
    for sym in args.symbols:
        open_, close = bars["open"][sym].dropna(), bars["close"][sym].dropna()
        never = pd.Series(np.nan, index=close.index)
        plain[sym] = simulate(open_, close, never, args.start, args.end, 2, 2)
        peak = close.loc[args.start:args.end].idxmax()
        for name, series in indicators(close, per_share[sym]).items():
            rank = trailing_rank(series)
            for level, (pause, sell) in LEVELS.items():
                res = simulate(open_, close, rank, args.start, args.end, pause, sell)
                near = [d for d in res["sells"] if abs((d - peak).days) <= 21]
                rows.append({"indicator": name, "level": level, "symbol": sym, "multiple": res["multiple"], "max fall%": res["max fall%"],
                             "sells": len(res["sells"]), "sells near peak": len(near)})
                if level.startswith("top 20%"):
                    sells_log[(name, sym)] = res["sells"]
    table = pd.DataFrame(rows)

    print(f"One unit a week, {args.start} -> {args.end}; sell 20% when stretched. Plain weekly multiples: "
          + ", ".join(f"{s} {plain[s]['multiple']:.2f}" for s in args.symbols) + "\n")
    summary = table.groupby("indicator").agg(avg_multiple=("multiple", "mean"), worst=("multiple", "min"), best=("multiple", "max"),
                                             avg_max_fall=("max fall%", "mean"), avg_sells=("sells", "mean"),
                                             near_peak_share=("sells near peak", "sum"))
    summary["near_peak_share"] = summary["near_peak_share"] / table.groupby("indicator")["sells"].sum() * 100
    beats = table.assign(beat=[r.multiple > plain[r.symbol]["multiple"] for r in table.itertuples()]).groupby("indicator")["beat"].mean() * 100
    summary["beats plain %"] = beats
    print("All symbols and all three strictness levels together:")
    print(summary.sort_values("avg_multiple", ascending=False).to_string(), "\n")

    mid = table[table.level.str.startswith("top 20%")].pivot(index="indicator", columns="symbol", values="multiple")[args.symbols]
    mid["average"] = mid.mean(axis=1)
    print("Multiple by symbol at the middle level (pause in top 20%, sell in top 5%):")
    print(mid.sort_values("average", ascending=False).to_string(), "\n")

    by_level = table.pivot_table(index="indicator", columns="level", values="multiple", aggfunc="mean")[list(LEVELS)]
    print("Average multiple by strictness level:")
    print(by_level.loc[summary.sort_values("avg_multiple", ascending=False).index].to_string(), "\n")

    sym = args.symbols[0]
    close = bars["close"][sym]
    print(f"{sym}: weeks each indicator said 'sell' (middle level), with the price that day")
    for name in summary.sort_values("avg_multiple", ascending=False).index:
        days = sells_log[(name, sym)]
        text = ", ".join(f"{d.strftime('%y-%m-%d')} ${close[d]:.0f}" for d in days[:14]) + (" ..." if len(days) > 14 else "")
        print(f"  {name:24} {len(days):2d}  {text}")
    table.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "indicator_compare.csv"), index=False)


if __name__ == "__main__":
    main()
