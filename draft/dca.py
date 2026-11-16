"""Lump sum vs. spreading purchases over time (dollar-cost averaging), for every possible start month.

For each start month in the daily history: put the money in at once, or in `--months` equal monthly
instalments (uninvested cash earns nothing). Both are measured `--horizon` months after the start.
Drawdown is measured on total wealth (shares + cash still waiting), which is what you actually feel.

Usage: python draft/dca.py [--months 12] [--horizon 24] [SYMBOL ...]
"""
import argparse

import numpy as np
import pandas as pd

from data import load_bars
from universe import UNIVERSE


def paths(price, start_idx, month_starts, months, horizon):
    window = price.iloc[month_starts[start_idx]:month_starts[start_idx + horizon] + 1]
    lump = window / window.iloc[0]
    shares, cash, wealth = 0.0, 1.0, []
    buy_days = set(price.index[month_starts[start_idx + k]] for k in range(months))
    for day, px in window.items():
        if day in buy_days:
            shares += (1 / months) / px
            cash -= 1 / months
        wealth.append(shares * px + cash)
    return lump, pd.Series(wealth, index=window.index)


def drawdown(series):
    return (series / series.cummax() - 1).min() * 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", default=["CIBR", "EW22", "QLYS", "TENB"])
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--horizon", type=int, default=24)
    args = parser.parse_args()

    security = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    close = load_bars(security + ["CIBR", "QQQ"])["close"]
    close["EW22"] = (1 + close[security].pct_change().mean(axis=1).fillna(0)).cumprod()
    month = pd.Series(close.index.to_period("M"), index=close.index)
    month_starts = [close.index.get_loc(d) for d in close.index[month.ne(month.shift()).values]]
    rows = {}
    for sym in args.symbols:
        price = close[sym].dropna()
        starts = [i for i in range(len(month_starts) - args.horizon) if close.index[month_starts[i]] >= price.index[0]]
        res = []
        for i in starts:
            lump, dca = paths(close[sym], i, month_starts, args.months, args.horizon)
            res.append({"lump_ret": (lump.iloc[-1] - 1) * 100, "dca_ret": (dca.iloc[-1] - 1) * 100,
                        "lump_dd": drawdown(lump), "dca_dd": drawdown(dca)})
        r = pd.DataFrame(res)
        rows[sym] = {"starts": len(r),
                     "lump: median return%": r.lump_ret.median(), "dca: median return%": r.dca_ret.median(),
                     "lump wins %": (r.lump_ret > r.dca_ret).mean() * 100,
                     "lump: worst return%": r.lump_ret.min(), "dca: worst return%": r.dca_ret.min(),
                     "lump: median max drop%": r.lump_dd.median(), "dca: median max drop%": r.dca_dd.median(),
                     "lump: worst drop%": r.lump_dd.min(), "dca: worst drop%": r.dca_dd.min()}
    print(f"History {close.index[0].date()} -> {close.index[-1].date()};  instalments over {args.months} months, measured after {args.horizon} months\n")
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()
