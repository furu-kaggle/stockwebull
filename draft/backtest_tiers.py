"""Backtest the tier ranking with point-in-time data.

At each month-end the ranking is rebuilt using only what was known then: quarters already published,
that day's price, and the stock's P/S history up to that day. The top N names are held equal-weight
until the next month-end; orders fill at the next open and pay `--cost` per side.

Known shortcuts: share counts are held at today's value (so past P/S levels are approximate), and the
universe is today's list (companies acquired or delisted along the way are missing).

Usage: python draft/backtest_tiers.py [--top 5] [--cost 0.003]
"""
import argparse

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from backtest_security import run, stats
from data import load_bars, load_income
from tiers import peer_relative, priced_in, tier, valuation
from universe import UNIVERSE

MIN_HISTORY = 250   # trading days of P/S history needed before a name can be ranked


def build_panels(symbols, close, income, shares):
    """Daily point-in-time panels: TTM growth, TTM operating margin and P/S for every symbol."""
    growth, margin, ps = (pd.DataFrame(np.nan, index=close.index, columns=symbols) for _ in range(3))
    for sym in symbols:
        q = income[(income.symbol == sym) & income.publish_date.notna()].sort_values("end_date")
        q = q[~q.publish_date.duplicated(keep="last")]
        if len(q) < 4 or sym not in shares:
            continue
        rev, op = q.revenue.rolling(4).sum(), q.op_income.rolling(4).sum()
        facts = pd.DataFrame({"rev": rev.values, "growth": (rev / rev.shift(4) - 1).values * 100,
                              "margin": (op / rev).values * 100}, index=q.publish_date.values).sort_index()
        # A report published on day D is usable from the next session.
        daily = facts.reindex(close.index.union(facts.index)).ffill().shift(1).reindex(close.index)
        growth[sym], margin[sym] = daily["growth"], daily["margin"]
        ps[sym] = close[sym] * shares[sym] / daily["rev"]
    return growth, margin, ps


def snapshot(day, growth, margin, ps):
    hist = ps.loc[:day]
    table = pd.DataFrame({"growth%": growth.loc[day], "op_margin%": margin.loc[day], "P/S": ps.loc[day],
                          "ps_pctile": (hist.le(hist.iloc[-1])).sum() / hist.notna().sum() * 100,
                          "n": hist.notna().sum()})
    table = table[(table["n"] >= MIN_HISTORY)].dropna(subset=["growth%", "op_margin%", "P/S"])
    if len(table) < 8:
        return None
    table["vs_peers"] = peer_relative(table)
    table["tier"] = table.apply(tier, axis=1)
    table["priced_in"] = table.apply(priced_in, axis=1)
    table["full"] = table["priced_in"] == "high"
    table["rule40"] = table["growth%"] + table["op_margin%"]
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--cost", type=float, default=0.003)
    args = parser.parse_args()

    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    bars = load_bars(symbols + ["QQQ", "CIBR", "IEF"])
    close, income = bars["close"], load_income(symbols)
    val = valuation(symbols)
    shares = {s: val.loc[s, "cap_$B"] * 1e9 / close[s].dropna().iloc[-1] for s in symbols if s in val.index}
    growth, margin, ps = build_panels(symbols, close[symbols], income, shares)

    days = close.index
    month = pd.Series(days.month, index=days)
    month_ends = days[month.shift(-1).ne(month).values][:-1]
    orders = {
        "ranking (tier, then room)": lambda t: t.sort_values(["full", "tier", "ps_pctile"]),
        "tier only (quality)": lambda t: t.sort_values(["tier", "rule40"], ascending=[True, False]),
        "room only (cheap vs own past)": lambda t: t.sort_values(["full", "ps_pctile"]),
        "reverse (priced-in first)": lambda t: t.sort_values(["full", "tier", "ps_pctile"], ascending=[False, False, False]),
        "all eligible, equal weight": None,
    }
    weights = {name: pd.DataFrame(0.0, index=month_ends, columns=symbols) for name in orders}
    picks_log, first = {}, None
    for day in month_ends:
        table = snapshot(day, growth, margin, ps)
        if table is None:
            continue
        first = first or day
        for name, order in orders.items():
            picks = list(table.index) if order is None else list(order(table).index[:args.top])
            weights[name].loc[day, picks] = 1 / len(picks)
            if name.startswith("ranking"):
                picks_log[day] = (picks, len(table), int(table["full"].sum()))
    start = days[days.get_loc(first) + 1]
    print(f"Period: {start.date()} -> {days[-1].date()}  ({len([d for d in month_ends if d >= first])} monthly rebalances)"
          f"   top {args.top}, cost {args.cost:.2%}/side\n")

    rows, curves = {}, {}
    for name in orders:
        equity, turnover = run(bars, weights[name].loc[first:], args.cost)
        curves[name] = equity[start:]
        rows[name] = stats(curves[name], turnover)
    for b in ("CIBR", "QQQ"):
        curves[b] = close[b][start:] / close[b][start]
        rows[f"{b} buy & hold"] = stats(curves[b])
    pd.set_option("display.width", 220, "display.float_format", "{:.2f}".format)
    print(pd.DataFrame(rows).T.to_string(), "\n")
    yearly = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda s: (s.iloc[-1] / s.iloc[0] - 1) * 100) for k, v in curves.items()})
    print("Return by calendar year (%)"); print(yearly.T.to_string(), "\n")

    held = pd.Series([s for picks, _, _ in picks_log.values() for s in picks]).value_counts()
    print("Months held in the ranking portfolio:", ", ".join(f"{s} {n}" for s, n in held.items()))
    print("Picks over time (ranked universe size / priced-in count):")
    for day, (picks, n, full) in list(picks_log.items())[::3]:
        print(f"  {day.date()}  {', '.join(picks)}   ({n} / {full})")
    last_day = list(picks_log)[-1]
    print(f"  {last_day.date()}  {', '.join(picks_log[last_day][0])}   (latest)")


if __name__ == "__main__":
    main()
