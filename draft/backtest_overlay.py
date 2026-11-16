"""Core + overlay: hold the whole security universe, lean into laggards and trim leaders.

  core      every name at an equal weight, `--core` of equity in total (the rest is cash reserve)
  buy more  a name whose 2-day return trails the sector by z <= -entry goes to 1.5x its core weight
  trim      a name that leads the sector by z >= +entry goes to 0.5x its core weight
  reset     back to the core weight once |z| < 0.5
  limit     at most `--max-trades` orders per day (largest |z| first), filled at the next bar's open

Compared with simply holding the same core, so the difference is what the trading adds.

Usage: python draft/backtest_overlay.py [--entry 2] [--core 0.7] [--slip 0.0005]
"""
import argparse

import numpy as np
import pandas as pd

from backtest_intraday import BARS_PER_DAY, signals, summarize
from data import load_intraday
from universe import UNIVERSE


def simulate(bars, symbols, args, trade=True):
    close, open_ = bars["close"][symbols].ffill(), bars["open"][symbols]
    z, _, _ = signals(bars["close"], symbols, args.lookback)
    times, start = close.index, 12 * BARS_PER_DAY
    base = args.core / len(symbols)
    tilt = pd.Series(1.0, index=symbols)                      # multiple of the core weight currently held
    px0 = close.iloc[start - 1]
    shares = base / (px0 * (1 + args.slip))                   # equity starts at 1.0
    cash = 1.0 - args.core
    pending, trades_today, day, orders, equity = [], 0, None, [], {}
    for i in range(start, len(times)):
        t = times[i]
        if t.normalize() != day:
            day, trades_today = t.normalize(), 0
        for sym, target in pending:
            if trades_today >= args.max_trades:
                break
            px = open_.iloc[i][sym]
            px = close.iloc[i - 1][sym] if np.isnan(px) else px
            value = cash + (shares * close.iloc[i - 1]).sum()
            want = target * base * value / px
            delta = want - shares[sym]
            if delta > 0 and delta * px * (1 + args.slip) > cash:
                continue                                      # not enough reserve to buy more
            cash -= delta * px * (1 + args.slip if delta > 0 else 1 - args.slip)
            shares[sym], tilt[sym] = want, target
            trades_today += 1
            orders.append({"time": t, "symbol": sym, "side": "buy" if delta > 0 else "sell", "to": target})
        pending = []
        equity[t] = cash + (shares * close.iloc[i]).sum()
        if not trade:
            continue
        zi = z.iloc[i].dropna()
        for sym in zi.abs().sort_values(ascending=False).index:
            target = 1.5 if zi[sym] <= -args.entry else 0.5 if zi[sym] >= args.entry else 1.0 if abs(zi[sym]) < 0.5 else tilt[sym]
            if target != tilt[sym]:
                pending.append((sym, target))
    return pd.Series(equity), pd.DataFrame(orders)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", type=float, default=2.0)
    parser.add_argument("--lookback", type=int, default=2)
    parser.add_argument("--core", type=float, default=0.70)
    parser.add_argument("--max-trades", type=int, default=5)
    parser.add_argument("--slip", type=float, default=0.0005)
    args = parser.parse_args()
    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    bars = load_intraday(symbols + ["CIBR", "QQQ"])
    rows = {}
    held, _ = simulate(bars, symbols, args, trade=False)
    rows[f"core only ({args.core:.0%} held, no trading)"] = summarize(held)
    for entry in (1.5, 2.0, 2.5):
        for lookback in (1, 2, 3):
            a = argparse.Namespace(**{**vars(args), "entry": entry, "lookback": lookback})
            eq, orders = simulate(bars, symbols, a)
            s = summarize(eq)
            s["orders/day"] = len(orders) / eq.index.normalize().nunique()
            s["vs core %"] = s["return%"] - rows[f"core only ({args.core:.0%} held, no trading)"]["return%"]
            rows[f"overlay entry {entry} lookback {lookback}d"] = s
    print(f"Period: {held.index[0].date()} -> {held.index[-1].date()}  ({held.index.normalize().nunique()} trading days)   slip {args.slip:.2%}/side\n")
    pd.set_option("display.width", 220, "display.float_format", "{:.2f}".format)
    print(pd.DataFrame(rows).T.to_string())


if __name__ == "__main__":
    main()
