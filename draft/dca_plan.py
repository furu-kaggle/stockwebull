"""Simulate a fixed savings plan: equal daily purchases over N business days, split across symbols.

Runs the plan from every possible start day in the price history and reports how it would have
ended: value when the last purchase is made, and after holding for 6 and 12 more months.
Fractional shares, purchases at each day's close, no commission, currency moves ignored.

Usage: python draft/dca_plan.py [QLYS TENB] [--days 60] [--budget 100000]
"""
import argparse

import numpy as np
import pandas as pd

from data import load_bars


def run(close, start, days):
    """Value per unit invested, day by day, for a plan starting at integer position `start`."""
    window = close.iloc[start:]
    buys = window.iloc[:days]
    shares = (1 / days / buys).cumsum()                        # equal amount each day
    shares = shares.reindex(window.index).ffill()
    paid = pd.Series(np.minimum(np.arange(1, len(window) + 1), days) / days, index=window.index)
    return shares * window, paid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", default=["QLYS", "TENB"])
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--budget", type=float, default=100000)
    parser.add_argument("--compare", default="CIBR")
    args = parser.parse_args()

    close = load_bars(args.symbols + [args.compare])["close"].dropna()
    horizons = {"at last purchase": args.days - 1, "+6 months": args.days - 1 + 126, "+12 months": args.days - 1 + 252}
    plans = {"+".join(args.symbols): args.symbols, **{s: [s] for s in args.symbols}, args.compare: [args.compare]}
    rows, worst_dip = [], {}
    for name, members in plans.items():
        results = {h: [] for h in horizons}
        lump = {h: [] for h in horizons}
        dips = []
        for start in range(len(close) - args.days):
            value = sum(run(close[m], start, args.days)[0] for m in members) / len(members)
            paid = run(close[members[0]], start, args.days)[1]
            dips.append(((value / paid).iloc[:args.days + 252] - 1).min() * 100)
            for h, offset in horizons.items():
                if offset < len(value):
                    results[h].append((value.iloc[offset] / paid.iloc[offset] - 1) * 100)
                    lump[h].append(np.mean([close[m].iloc[start + offset] / close[m].iloc[start] - 1 for m in members]) * 100)
        worst_dip[name] = (np.median(dips), np.min(dips))
        for h in horizons:
            r, l = np.array(results[h]), np.array(lump[h])
            rows.append({"plan": name, "measured": h, "starts": len(r), "median%": np.median(r), "worst%": r.min(), "best%": r.max(),
                         "ended up%": (r > 0).mean() * 100, "lump median%": np.median(l), "lump worst%": l.min()})
    table = pd.DataFrame(rows)
    pd.set_option("display.width", 220, "display.float_format", "{:.1f}".format)
    print(f"Equal purchases on {args.days} consecutive business days, every start day from {close.index[0].date()} to "
          f"{close.index[-args.days].date()}\n")
    print(table.to_string(index=False), "\n")
    print("Deepest point below the money put in, within 12 months of finishing (median start / worst start):")
    for name, (med, low) in worst_dip.items():
        print(f"  {name:10} {med:6.1f}% / {low:6.1f}%")

    name = "+".join(args.symbols)
    print(f"\nIn yen for a {args.budget:,.0f} yen plan in {name} ({args.budget / args.days:,.0f} yen a day, exchange rate held fixed):")
    for h in horizons:
        r = table[(table.plan == name) & (table.measured == h)].iloc[0]
        print(f"  {h:17} median {args.budget * (1 + r['median%'] / 100):>9,.0f}   worst {args.budget * (1 + r['worst%'] / 100):>9,.0f}"
              f"   best {args.budget * (1 + r['best%'] / 100):>9,.0f}")

    print("\nThe plan started on selected dates (value vs money put in, at last purchase / +6 months / +12 months):")
    for label, day in (("60 days before the Apr 2026 low", close.index[close.index.get_loc(pd.Timestamp("2026-04-10")) - 59]),
                       ("at the Apr 2026 low", pd.Timestamp("2026-04-10")),
                       ("most recent full plan", close.index[-args.days]),
                       ("one year ago", close.index[-args.days - 252])):
        start = close.index.get_loc(day)
        value = sum(run(close[m], start, args.days)[0] for m in args.symbols) / len(args.symbols)
        paid = run(close[args.symbols[0]], start, args.days)[1]
        cells = [f"{(value.iloc[o] / paid.iloc[o] - 1) * 100:+.1f}%" if o < len(value) else "n/a" for o in horizons.values()]
        print(f"  {label:32} {day.date()}  " + " / ".join(cells))


if __name__ == "__main__":
    main()
