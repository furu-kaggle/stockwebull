"""Which signals actually predict returns in the security universe?

For each signal, the weekly rank correlation (IC) with the following 1-week and 1-month return,
and the spread between the top and bottom third. No costs: this is a diagnostic, not a strategy.

Usage: python draft/signal_check.py
"""
import numpy as np
import pandas as pd

from backtest_security import WARMUP, insect_score
from data import load_bars, load_income
from universe import UNIVERSE


def main():
    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    bars = load_bars(symbols + ["QQQ", "CIBR", "IEF"])
    close, income = bars["close"][symbols], load_income(symbols)
    _, reaction = insect_score(bars["close"], income, symbols)

    cols = {k: pd.DataFrame(np.nan, index=close.index, columns=symbols) for k in ("growth", "margin")}
    days_since = pd.DataFrame(np.nan, index=close.index, columns=symbols)
    for sym in symbols:
        q = income[(income.symbol == sym) & income.publish_date.notna()].sort_values("end_date").copy()
        q["growth"] = q.revenue / q.revenue.shift(4) - 1
        q["margin"] = q.op_income / q.revenue - q.op_income.shift(4) / q.revenue.shift(4)
        s = close[sym].dropna()
        for _, r in q.iterrows():
            pos = s.index.searchsorted(r.publish_date)
            if 1 <= pos < len(s) - 1:
                cols["growth"].loc[s.index[pos + 1], sym] = r.growth
                cols["margin"].loc[s.index[pos + 1], sym] = r.margin
                days_since.loc[s.index[pos + 1], sym] = 0
    since = days_since.copy()
    for sym in symbols:                                     # sessions since the last earnings reaction
        last = None
        for i, v in enumerate(days_since[sym].values):
            last = 0 if v == 0 else (last + 1 if last is not None else None)
            since.iloc[i, since.columns.get_loc(sym)] = last if last is not None else np.nan

    signals = {
        "momentum 12m (skip 1m)": close.shift(21) / close.shift(252) - 1,
        "momentum 6m (skip 1w)": close.shift(5) / close.shift(126) - 1,
        "momentum 3m": close / close.shift(63) - 1,
        "return 1m": close / close.shift(21) - 1,
        "return 1w": close / close.shift(5) - 1,
        "distance from 52w high": close / close.rolling(252, min_periods=126).max() - 1,
        "volatility 3m (low is +)": -close.pct_change().rolling(63).std(),
        "earnings reaction (all)": reaction,
        "earnings reaction (<=1m old)": reaction.where(since <= 21),
        "revenue growth yoy": cols["growth"].ffill(limit=100),
        "op margin change yoy": cols["margin"].ffill(limit=100),
    }
    days = close.index[WARMUP:]
    weeks = pd.Series(days.isocalendar().week.values, index=days)
    rebalance = days[weeks.shift(-1).ne(weeks).values]
    print(f"{len(rebalance)} weekly observations, {len(symbols)} names\n")
    print(f"{'signal':30}{'IC 1w':>8}{'t':>6}{'IC 1m':>8}{'t':>6}{'top-bottom 1m':>15}{'n/wk':>6}")
    for name, sig in signals.items():
        out = []
        for horizon in (5, 21):
            fwd = close.shift(-horizon) / close - 1
            ics, spreads, counts = [], [], []
            step = rebalance if horizon == 5 else rebalance[::4]     # non-overlapping monthly samples
            for day in step:
                x, y = sig.loc[day], fwd.loc[day]
                ok = x.notna() & y.notna()
                if ok.sum() < 6:
                    continue
                ics.append(x[ok].rank().corr(y[ok].rank()))
                third = max(ok.sum() // 3, 1)
                order = x[ok].sort_values()
                spreads.append(y[order.index[-third:]].mean() - y[order.index[:third]].mean())
                counts.append(ok.sum())
            ics = pd.Series(ics)
            out.append((ics.mean(), ics.mean() / ics.std() * np.sqrt(len(ics)), np.mean(spreads) * 100, np.mean(counts)))
        print(f"{name:30}{out[0][0]:8.3f}{out[0][1]:6.1f}{out[1][0]:8.3f}{out[1][1]:6.1f}{out[1][2]:14.2f}%{out[1][3]:6.0f}")


if __name__ == "__main__":
    main()
