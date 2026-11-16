"""Chart indexed prices (start = 100) for a set of symbols over the last N trading days.

Usage: python draft/chart_prices.py TENB QLYS RPD --ref CIBR --days 252 --title "..." --out charts/name.png
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from data import load_bars

PALETTE = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--ref", default="CIBR", help="reference drawn dashed")
    parser.add_argument("--days", type=int, default=252)
    parser.add_argument("--title", default="Price, indexed to 100")
    parser.add_argument("--out", default="charts/prices.png")
    args = parser.parse_args()

    names = args.symbols + ([args.ref] if args.ref else [])
    close = load_bars(names)["close"].tail(args.days + 1)
    indexed = close / close.iloc[0] * 100
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=160)
    for i, sym in enumerate(names):
        ref = sym == args.ref
        color = "#6b7280" if ref else PALETTE[i % len(PALETTE)]
        ax.plot(indexed.index, indexed[sym], color=color, lw=1.4 if ref else 2.2, ls="--" if ref else "-")
        ax.annotate(f"{sym}  {indexed[sym].iloc[-1] - 100:+.0f}%", (indexed.index[-1], indexed[sym].iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", color=color, fontsize=10, fontweight="bold")
    ax.axhline(100, color="#9ca3af", lw=0.8)
    fig.text(0.075, 0.95, args.title, fontsize=13, fontweight="bold", va="top")
    fig.text(0.075, 0.90, f"{close.index[0].date()} to {close.index[-1].date()}, daily close"
             + (f" ({args.ref} dashed for reference)" if args.ref else ""), fontsize=9, color="#6b7280", va="top")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.grid(axis="y", color="#e5e7eb", lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.margins(x=0.01)
    fig.subplots_adjust(left=0.075, right=0.86, top=0.84, bottom=0.08)
    fig.savefig(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
