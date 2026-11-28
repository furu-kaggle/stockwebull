"""Review of the live plan: what was bought, what it is worth, and how other choices would have done.

Every comparison spends the same dollars at the same minutes as the real fills, so the only
difference is what was bought. Prices at the time of a fill come from 5-minute bars.

Usage: python draft/weekly_review.py [--week-start 2026-11-23]
"""
import argparse
import os

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from fills import load_fills
from plan_live import fresh_bars
from universe import UNIVERSE

HERE = os.path.dirname(os.path.abspath(__file__))
SEC = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]


def five_minute(data, symbols):
    rows = []
    for i in range(0, len(symbols), 5):
        resp = data.market_data.get_batch_history_bar(symbols[i:i + 5], "US_STOCK", "M5", count="1200").json()
        for item in resp["result"]:
            for b in item.get("result") or []:
                rows.append((pd.Timestamp(b["time"]).tz_convert("America/New_York").tz_localize(None), item["symbol"], float(b["open"]), float(b["close"])))
    long = pd.DataFrame(rows, columns=["time", "symbol", "open", "close"])
    return long.pivot(index="time", columns="symbol", values="open").sort_index(), long.pivot(index="time", columns="symbol", values="close").sort_index()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-start", default="2026-11-23")
    args = parser.parse_args()
    fills = load_fills(refresh=False)
    data = DataClient(make_client())
    names = sorted(set(SEC) | set(fills.symbol) | {"CIBR", "QQQ", "SPY", "IWM", "UI", "XLP", "SGOV"})
    daily = fresh_bars(data, names, count=30)
    close, open_ = daily["close"], daily["open"]
    last = close.iloc[-1]
    m5_open, m5_close = five_minute(data, names)

    def price_at(t, sym):                                         # the 5-minute bar the fill happened in
        bar = m5_open.index[m5_open.index.searchsorted(t, side="right") - 1]
        return m5_close.at[bar, sym] if not np.isnan(m5_close.at[bar, sym]) else close.at[t.normalize(), sym]

    held = fills.groupby("symbol").agg(qty=("qty", "sum"), cost=("dollars", "sum"))
    held["avg_price"] = held.cost / held.qty
    held["last"] = last[held.index]
    held["value"] = held.qty * held["last"]
    held["pnl"] = held.value - held.cost
    held["pnl_pct"] = held.pnl / held.cost * 100
    held["weight_pct"] = held.value / held.value.sum() * 100
    print(f"marked at the close of {close.index[-1].date()}")
    print(held.round(2).sort_values("value", ascending=False).to_string())
    invested, value = held.cost.sum(), held.value.sum()
    print(f"invested ${invested:.2f}  value ${value:.2f}  P&L ${value - invested:+.2f} ({(value / invested - 1) * 100:+.2f}%)\n")

    baskets = {"what was bought": None, "QLYS + TENB half each": ["QLYS", "TENB"], "22 security names equally": [s for s in SEC if s in close.columns],
               "security ETF (CIBR)": ["CIBR"], "Nasdaq-100 ETF (QQQ)": ["QQQ"], "S&P 500 ETF (SPY)": ["SPY"], "small caps (IWM)": ["IWM"]}
    rows = {}
    for name, basket in baskets.items():
        total = 0.0
        for f in fills.itertuples():
            if basket is None:
                total += f.qty * last[f.symbol]
            else:
                for s in basket:
                    total += f.dollars / len(basket) / price_at(f.time, s) * last[s]
        rows[name] = dict(value=total, pnl=total - invested, pct=(total / invested - 1) * 100)
    # the same names and dollars, but bought at the day's open or close instead of the real minute
    for label, px in (("same names, bought at the open", open_), ("same names, bought at the close", close)):
        total = sum(f.dollars / px.at[f.time.normalize(), f.symbol] * last[f.symbol] for f in fills.itertuples())
        rows[label] = dict(value=total, pnl=total - invested, pct=(total / invested - 1) * 100)
    print(pd.DataFrame(rows).T.round(2).to_string(), "\n")

    week = pd.Timestamp(args.week_start)
    before = fills[fills.time < week]
    prev_close = close[close.index < week].iloc[-1]
    start_value = (before.groupby("symbol").qty.sum() * prev_close).dropna().sum()
    bought = fills[fills.time >= week].dollars.sum()
    print(f"week from {week.date()}: value before ${start_value:.2f}, bought ${bought:.2f}, value now ${value:.2f}, week P&L ${value - start_value - bought:+.2f}")
    wk = (close.iloc[-1] / prev_close - 1) * 100
    print("week moves %:", wk[list(held.index) + ["CIBR", "QQQ", "SPY", "IWM"]].round(1).to_dict())
    sec_week = wk[[s for s in SEC if s in wk.index]].sort_values()
    print("security names this week: mean %.1f, best %s, worst %s" % (sec_week.mean(), sec_week.tail(4).round(1).to_dict(), sec_week.head(4).round(1).to_dict()))

    by_day = fills.assign(day=fills.time.dt.normalize(), now=lambda d: d.qty * d.symbol.map(last))
    d = by_day.groupby("day").agg(orders=("symbol", "count"), dollars=("dollars", "sum"), now=("now", "sum"))
    d["pnl_pct"] = (d.now / d.dollars - 1) * 100
    print("\nby purchase day"); print(d.round(2).to_string())
    slip = fills.copy()
    slip["bar"] = [price_at(t, s) for t, s in zip(slip.time, slip.symbol)]
    slip["vs_close"] = (slip.price / [close.at[t.normalize(), s] for t, s in zip(slip.time, slip.symbol)] - 1) * 100
    print("\nfill against that day's close, by day %:", slip.groupby(slip.time.dt.date).vs_close.mean().round(2).to_dict(), " overall", round(slip.vs_close.mean(), 2))


if __name__ == "__main__":
    main()
