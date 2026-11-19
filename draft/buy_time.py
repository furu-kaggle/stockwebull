"""Does the time of day of a daily purchase matter? Uses 30-minute bars (about 180 days).

For every trading day and stock, the price at each half-hour is compared with the day's
average half-hourly price. A negative number means buying at that time was cheaper than
spreading the purchase evenly over the day.
"""
import sys
import numpy as np
import pandas as pd
from data import load_intraday
from universe import UNIVERSE

SEC = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
BUY = ["QLYS", "TENB", "GEN", "FTNT", "AXON", "FFIV"]


def table(open_, close, symbols):
    o, c = open_[symbols], close[symbols]
    day = o.index.normalize()
    slots = o.index.strftime("%H:%M")
    px = o.copy()                                   # the price at the start of each half-hour
    last = c.groupby(day).tail(1)                   # add the closing print as a final slot
    avg = px.groupby(day).transform("mean")
    rel = (px / avg - 1) * 100
    rel_close = (last / avg.groupby(day).tail(1).values - 1) * 100
    per_day = rel.groupby([day, slots]).mean().mean(axis=1).unstack()          # day x slot, averaged over stocks
    per_day["close"] = rel_close.mean(axis=1).groupby(rel_close.index.normalize()).mean()
    per_day = per_day.dropna(thresh=10)
    stats = pd.DataFrame({"mean%": per_day.mean(), "t": per_day.mean() / (per_day.std() / np.sqrt(per_day.count())),
                          "cheaper_than_avg%": (per_day < 0).mean() * 100})
    return stats, per_day


def main():
    b = load_intraday(sorted(set(SEC + BUY)), "M30", refresh="--refresh" in sys.argv)
    open_, close = b["open"], b["close"]
    print("days", open_.index.normalize().nunique(), open_.index.min().date(), "to", open_.index.max().date())
    for name, syms in (("six names bought", BUY), ("22 security names", [s for s in SEC if s in open_.columns])):
        syms = [s for s in syms if s in open_.columns]
        stats, per_day = table(open_, close, syms)
        print(f"\n{name} ({len(syms)}): price at each time against the day's average")
        print(stats.round(2).T.to_string())
        early, late = per_day.get("09:30"), per_day["close"]
        d = (late - per_day["10:00"]).dropna()
        print(f"close minus 10:00 purchase: mean {d.mean():+.2f}%  t {d.mean() / (d.std() / np.sqrt(len(d))):.1f}  close cheaper on {100 * (d < 0).mean():.0f}% of days")
        half = len(per_day) // 2
        print("first half / second half of sample, 10:00 vs close:", round(per_day["10:00"].iloc[:half].mean(), 2), round(per_day["close"].iloc[:half].mean(), 2), "|",
              round(per_day["10:00"].iloc[half:].mean(), 2), round(per_day["close"].iloc[half:].mean(), 2))


if __name__ == "__main__":
    main()
