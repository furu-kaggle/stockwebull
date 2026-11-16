"""Switching a savings plan on and off by how stretched the price is, on a high-volatility name.

One unit of cash arrives every week. The price's z-score (log price against its own N-day average,
in units of its N-day spread, known at the previous close) decides what to do at that day's open:

  rich   z > off          buy nothing; the cash waits
  normal                  buy up to `catch` units (more than 1 lets waiting cash re-enter gradually)
  cheap  z < boost        buy up to `boost_mult` units
  very rich  z > sell     sell `sell_frac` of the holding back to cash (once a week)

Reported per rule: wealth per unit contributed at the end ("multiple"), the same at its highest and
lowest points, and the deepest fall in wealth from a peak. A grid search finds the best rule on one
symbol; the same rule is then run unchanged on the other symbols to see whether it travels.

Usage: python draft/dca_switch.py [--symbol IONQ] [--start 2025-01-01] [--end 2026-11-13]
"""
import argparse
import itertools

import numpy as np
import pandas as pd

from data import load_bars

INF = float("inf")
SLIP = 0.0005
PLAIN = dict(n=100, off=INF, boost=-INF, boost_mult=1, catch=1, sell=INF, sell_frac=0.0)
NAMED = {
    "plain weekly": PLAIN,
    "pause when rich": dict(PLAIN, off=1.0, catch=2),
    "pause when rich + buy more when cheap": dict(PLAIN, off=1.0, catch=2, boost=-1.0, boost_mult=3),
    "same + trim when very rich": dict(PLAIN, off=1.0, catch=2, boost=-1.0, boost_mult=3, sell=2.0, sell_frac=0.2),
    "only buy when cheap": dict(PLAIN, off=-1.0, catch=3, boost=-1.0, boost_mult=3),
    "only buy in uptrends (z > 0)": dict(PLAIN, off=INF, boost=0.0, boost_mult=0, catch=2),
}


def zscore(close, n):
    logp = np.log(close)
    return ((logp - logp.rolling(n).mean()) / logp.rolling(n).std()).shift(1)   # known before the open


def simulate(open_, close, start, end, n, off, boost, boost_mult, catch, sell, sell_frac):
    z = zscore(close, n)
    days = close.loc[start:end].index
    week = pd.Series(days.isocalendar().week.values, index=days)
    buy_days = set(days[week.ne(week.shift()).values])
    shares = cash = paid = 0.0
    wealth, contributed = [], []
    for day in days:
        if day in buy_days:
            cash += 1.0
            paid += 1.0
            zi, px = z[day], open_[day]
            if not np.isnan(zi):
                if zi > sell and shares > 0:
                    cash += shares * sell_frac * px * (1 - SLIP)
                    shares *= 1 - sell_frac
                elif zi <= off:
                    spend = min(cash, boost_mult if zi < boost else catch)
                    shares += spend / (px * (1 + SLIP))
                    cash -= spend
        wealth.append(shares * close[day] + cash)
        contributed.append(paid)
    w, c = pd.Series(wealth, index=days), pd.Series(contributed, index=days)
    mult = w / c
    return {"multiple": mult.iloc[-1], "highest": mult.max(), "lowest": mult.min(),
            "max fall%": (w / w.cummax() - 1).min() * 100, "cash% at end": (w.iloc[-1] - shares * close[days[-1]]) / w.iloc[-1] * 100}


def lump(open_, close, start, end):
    px = close.loc[start:end]
    w = px / open_.loc[start:end].iloc[0]
    return {"multiple": w.iloc[-1], "highest": w.max(), "lowest": w.min(), "max fall%": (w / w.cummax() - 1).min() * 100, "cash% at end": 0.0}


def grid():
    for n, off, (boost, boost_mult), sell, frac in itertools.product(
            (50, 100, 200), (0.5, 1.0, 1.5, INF), ((-INF, 1), (-0.5, 3), (-1.0, 3)), (INF, 1.5, 2.0, 2.5), (0.2, 0.5)):
        if sell == INF and frac != 0.2:
            continue
        yield dict(n=n, off=off, boost=boost, boost_mult=boost_mult, catch=2 if off < INF else 1, sell=sell, sell_frac=frac if sell < INF else 0.0)


def label(p):
    parts = [f"N={p['n']}", "never pause" if p["off"] == INF else f"pause z>{p['off']}"]
    if p["boost"] > -INF:
        parts.append(f"x{p['boost_mult']} if z<{p['boost']}")
    if p["sell"] < INF:
        parts.append(f"sell {p['sell_frac']:.0%} if z>{p['sell']}")
    return ", ".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="IONQ")
    parser.add_argument("--others", nargs="*", default=["RGTI", "QBTS", "QUBT"])
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-11-13")
    args = parser.parse_args()
    names = [args.symbol] + args.others
    bars = load_bars(names)
    open_, close = bars["open"], bars["close"]
    pd.set_option("display.width", 230, "display.float_format", "{:.2f}".format, "display.max_colwidth", 70)

    sym = args.symbol
    print(f"{sym}: one unit a week, {args.start} -> {args.end}\n")
    rows = {name: simulate(open_[sym], close[sym], args.start, args.end, **p) for name, p in NAMED.items()}
    rows["lump sum on day one"] = lump(open_[sym], close[sym], args.start, args.end)
    print(pd.DataFrame(rows).T.to_string(), "\n")

    results = [(p, simulate(open_[sym], close[sym], args.start, args.end, **p)) for p in grid()]
    table = pd.DataFrame([{"rule": label(p), **r} for p, r in results]).sort_values("multiple", ascending=False)
    plain = rows["plain weekly"]["multiple"]
    print(f"Grid search on {sym}: {len(table)} rules, {(table['multiple'] > plain).mean():.0%} beat plain weekly ({plain:.2f}); "
          f"median {table['multiple'].median():.2f}\n")
    print("Top 5:"); print(table.head(5).to_string(index=False), "\n")
    print("Bottom 3:"); print(table.tail(3).to_string(index=False), "\n")

    def average_effect(column, values):
        return {str(v): np.mean([r["multiple"] for p, r in results if p[column] == v]) for v in values}
    print("Average multiple by setting (which knob matters):")
    print("  pause threshold  ", {k: round(v, 2) for k, v in average_effect("off", (0.5, 1.0, 1.5, INF)).items()})
    print("  buy more if cheap", {k: round(v, 2) for k, v in average_effect("boost", (-INF, -0.5, -1.0)).items()})
    print("  trim threshold   ", {k: round(v, 2) for k, v in average_effect("sell", (INF, 1.5, 2.0, 2.5)).items()})
    print("  window N         ", {k: round(v, 2) for k, v in average_effect("n", (50, 100, 200)).items()}, "\n")

    best = max(results, key=lambda pr: pr[1]["multiple"])[0]
    print(f"Does the best {sym} rule travel?  [{label(best)}]")
    check = {}
    for other in names:
        base = simulate(open_[other], close[other], args.start, args.end, **PLAIN)
        tuned = simulate(open_[other], close[other], args.start, args.end, **best)
        simple = simulate(open_[other], close[other], args.start, args.end, **NAMED["same + trim when very rich"])
        check[other] = {"plain weekly": base["multiple"], f"best {sym} rule": tuned["multiple"], "simple preset rule": simple["multiple"],
                        "plain max fall%": base["max fall%"], "best max fall%": tuned["max fall%"], "preset max fall%": simple["max fall%"]}
    print(pd.DataFrame(check).to_string(), "\n")

    print(f"Same comparison on {sym} for different end dates (start {args.start}):")
    ends = {}
    for end in ("2025-10-13", "2025-12-31", "2026-03-31", "2026-05-29", args.end):
        ends[end] = {"plain weekly": simulate(open_[sym], close[sym], args.start, end, **PLAIN)["multiple"],
                     f"best {sym} rule": simulate(open_[sym], close[sym], args.start, end, **best)["multiple"],
                     "simple preset rule": simulate(open_[sym], close[sym], args.start, end, **NAMED["same + trim when very rich"])["multiple"],
                     "lump sum": lump(open_[sym], close[sym], args.start, end)["multiple"]}
    print(pd.DataFrame(ends).to_string())


if __name__ == "__main__":
    main()
