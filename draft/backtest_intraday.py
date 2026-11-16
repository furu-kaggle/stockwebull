"""Intraday relative-value strategy for the security universe (long only, 30-minute bars).

Idea: lean long while the sector is rising; buy names that have fallen behind the sector, add once
if they fall further, and sell when they have run ahead of it.

  cheap / rich   z-score of a stock's return over the last `--lookback` days minus the sector's
                 (equal-weight basket), scaled by that gap's own volatility over the last 10 days
  uptrend        the sector basket is above its 10-day average
  buy            z <= -entry while the sector is in an uptrend (one unit = `--unit` of equity)
  add            z <= -(entry + 1) on a name already held, at most two units per name
  sell           z >= exit ("ran ahead"), or held for `--max-days`, or down `--stop` from average cost
  limits         at most `--max-trades` orders per day, at most `--max-exposure` of equity invested

Signals are read at a bar's close and filled at the next bar's open, paying `--slip` per side
(Webull Japan charges no commission on US stocks; this stands for the spread). Cash earns nothing.

Usage: python draft/backtest_intraday.py [--entry 2] [--exit 1] [--lookback 2] [--sensitivity]
"""
import argparse

import numpy as np
import pandas as pd

from data import load_income, load_intraday
from universe import UNIVERSE

BARS_PER_DAY = 13


def signals(close, symbols, lookback_days):
    px = close[symbols].ffill()
    basket = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    n = lookback_days * BARS_PER_DAY
    gap = px.pct_change(n).sub(basket.pct_change(n), axis=0)
    z = gap / gap.rolling(10 * BARS_PER_DAY).std()
    uptrend = basket > basket.rolling(10 * BARS_PER_DAY).mean()
    return z, uptrend, basket


def earnings_blackout(times, symbols, days):
    """True where a bar falls within `days` sessions after an earnings release (no new buys there)."""
    blocked = pd.DataFrame(False, index=times, columns=symbols)
    if not days:
        return blocked
    sessions = pd.DatetimeIndex(sorted(set(times.normalize())))
    income = load_income(symbols)
    for sym in symbols:
        for pub in income[(income.symbol == sym) & income.publish_date.notna()].publish_date:
            pos = sessions.searchsorted(pub)
            window = sessions[pos:pos + days + 1]             # release day and the sessions after it
            blocked.loc[times.normalize().isin(window), sym] = True
    return blocked


def simulate(bars, symbols, args):
    close, open_ = bars["close"][symbols].ffill(), bars["open"][symbols]
    blackout = earnings_blackout(close.index, symbols, args.blackout)
    z, uptrend, basket = signals(bars["close"], symbols, args.lookback)
    times = close.index
    start = 12 * BARS_PER_DAY                                 # warm-up for the 10-day windows
    cash, shares = 1.0, pd.Series(0.0, index=symbols)
    units = pd.Series(0, index=symbols)
    cost = pd.Series(0.0, index=symbols)                      # average entry price
    age = pd.Series(0, index=symbols)                         # bars since first entry
    pending, trades_today, day = [], 0, None
    equity, log = {}, []
    for i in range(start, len(times)):
        t = times[i]
        if t.normalize() != day:
            day, trades_today = t.normalize(), 0
        value = cash + (shares * close.iloc[i - 1]).sum()
        for side, sym, reason in pending:                     # fill last bar's decisions at this open
            if trades_today >= args.max_trades:
                break
            px = open_.iloc[i][sym]
            px = close.iloc[i - 1][sym] if np.isnan(px) else px
            if side == "sell" and shares[sym] > 0:
                proceeds = shares[sym] * px * (1 - args.slip)
                log.append({"time": t, "symbol": sym, "side": "sell", "reason": reason, "bars": age[sym],
                            "pnl%": (px * (1 - args.slip) / cost[sym] - 1) * 100, "units": units[sym]})
                cash += proceeds
                shares[sym], units[sym], cost[sym], age[sym] = 0.0, 0, 0.0, 0
                trades_today += 1
            elif side == "buy":
                spend = min(args.unit * value, cash)
                if spend < 0.5 * args.unit * value:
                    continue
                qty = spend / (px * (1 + args.slip))
                cost[sym] = (cost[sym] * shares[sym] + px * (1 + args.slip) * qty) / (shares[sym] + qty)
                shares[sym] += qty
                units[sym] += 1
                cash -= spend
                log.append({"time": t, "symbol": sym, "side": "buy", "reason": reason, "bars": 0, "pnl%": np.nan, "units": units[sym]})
                trades_today += 1
        pending = []
        held = shares > 0
        age[held] += 1
        price, zi = close.iloc[i], z.iloc[i]
        equity[t] = cash + (shares * price).sum()

        # Decide at this close; exits are queued first so that they are never crowded out by entries.
        for sym in symbols:
            if not held[sym]:
                continue
            if price[sym] / cost[sym] - 1 <= -args.stop:
                pending.append(("sell", sym, "stop"))
            elif zi[sym] >= args.exit:
                pending.append(("sell", sym, "ran ahead"))
            elif age[sym] >= args.max_days * BARS_PER_DAY:
                pending.append(("sell", sym, "time"))
        selling = {sym for _, sym, _ in pending}
        invested = (shares * price).sum() / equity[t]
        if uptrend.iloc[i]:
            for sym in zi.dropna().sort_values().index:       # cheapest first
                if sym in selling or blackout.iloc[i][sym] or invested + args.unit > args.max_exposure + 1e-9:
                    continue
                if units[sym] == 0 and zi[sym] <= -args.entry:
                    pending.append(("buy", sym, "cheap"))
                    invested += args.unit
                elif units[sym] == 1 and zi[sym] <= -(args.entry + 1):
                    pending.append(("buy", sym, "add"))
                    invested += args.unit
    return pd.Series(equity), pd.DataFrame(log), basket.iloc[start:]


def summarize(equity, trades=None):
    daily = equity.groupby(equity.index.normalize()).last()
    r = daily.pct_change().dropna()
    out = {"return%": (equity.iloc[-1] / equity.iloc[0] - 1) * 100,
           "vol%/yr": r.std() * np.sqrt(252) * 100,
           "Sharpe": r.mean() / r.std() * np.sqrt(252) if r.std() else np.nan,
           "maxDD%": (equity / equity.cummax() - 1).min() * 100}
    if trades is not None and len(trades):
        sells = trades[trades.side == "sell"]
        per_day = trades.groupby(trades.time.dt.normalize()).size()
        out.update({"round trips": len(sells), "win%": (sells["pnl%"] > 0).mean() * 100, "avg pnl%": sells["pnl%"].mean(),
                    "avg hold days": sells["bars"].mean() / BARS_PER_DAY, "orders/day": len(trades) / daily.shape[0],
                    "max orders/day": per_day.max()})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", type=float, default=2.0)
    parser.add_argument("--exit", type=float, default=1.0)
    parser.add_argument("--lookback", type=int, default=2, help="days over which cheap/rich is measured")
    parser.add_argument("--unit", type=float, default=0.10)
    parser.add_argument("--max-exposure", type=float, default=0.60)
    parser.add_argument("--max-trades", type=int, default=5)
    parser.add_argument("--max-days", type=int, default=5)
    parser.add_argument("--stop", type=float, default=0.06)
    parser.add_argument("--slip", type=float, default=0.0005)
    parser.add_argument("--blackout", type=int, default=0, help="sessions after an earnings release with no new buys")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()

    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    bars = load_intraday(symbols + ["CIBR", "QQQ"])
    equity, trades, basket = simulate(bars, symbols, args)
    print(f"Period: {equity.index[0].date()} -> {equity.index[-1].date()}  ({equity.index.normalize().nunique()} trading days, 30-minute bars)\n")
    rows = {"strategy": summarize(equity, trades),
            "all 22 equal weight, held": summarize(basket / basket.iloc[0]),
            "same, scaled to strategy's avg exposure": None}
    for b in ("CIBR", "QQQ"):
        c = bars["close"][b].ffill().loc[equity.index[0]:]
        rows[f"{b} held"] = summarize(c / c.iloc[0])
    pd.set_option("display.width", 220, "display.float_format", "{:.2f}".format)
    del rows["same, scaled to strategy's avg exposure"]
    print(pd.DataFrame(rows).T.to_string(), "\n")
    if len(trades):
        sells = trades[trades.side == "sell"]
        print("Exits by reason:"); print(sells.groupby("reason")["pnl%"].agg(["count", "mean", lambda s: (s > 0).mean() * 100]).rename(columns={"<lambda_0>": "win%"}).to_string(), "\n")
        monthly = equity.groupby(equity.index.to_period("M")).last().pct_change() * 100
        monthly.iloc[0] = (equity.groupby(equity.index.to_period("M")).last().iloc[0] / equity.iloc[0] - 1) * 100
        bm = basket.groupby(basket.index.to_period("M")).last()
        bmr = bm.pct_change() * 100; bmr.iloc[0] = (bm.iloc[0] / basket.iloc[0] - 1) * 100
        print("Monthly return %:"); print(pd.DataFrame({"strategy": monthly, "all 22 held": bmr}).T.to_string(), "\n")
        print("Most traded:", ", ".join(f"{s} {n}" for s, n in sells.symbol.value_counts().head(8).items()))

    if args.sensitivity:
        print("\nSensitivity (return% / Sharpe / maxDD% / round trips)")
        for lookback in (1, 2, 3):
            for entry in (1.5, 2.0, 2.5):
                for slip in (0.0005, 0.0015):
                    a = argparse.Namespace(**{**vars(args), "lookback": lookback, "entry": entry, "slip": slip})
                    eq, tr, _ = simulate(bars, symbols, a)
                    s = summarize(eq, tr)
                    print(f"  lookback {lookback}d  entry {entry}  slip {slip:.2%}: {s['return%']:6.1f}  {s['Sharpe']:5.2f}  {s['maxDD%']:6.1f}  {s.get('round trips', 0):4.0f}")


if __name__ == "__main__":
    main()
