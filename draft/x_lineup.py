"""What X says about each candidate for the five slots: how much, and in what tone.

For every ticker, English posts carrying its cashtag with 30 likes or more are collected month by month
(up to 60 a month, the most-liked first). From them:
  heat    posts in the last two months against the average of the months before (also by likes, which still
          works for the busiest names, whose monthly count stops at the cap)
  tone    posts with buying words minus posts with selling words, as a share of all posts (last two months)
  alarm   share of recent posts that talk about the price being too high
Output: draft/x_lineup.csv (the posts) and, with --summary, the table by ticker.

Usage: python draft/x_lineup.py [--start 2026-05] [--workers 4] [--summary]
"""
import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from x_vuln_future import fetch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "x_lineup.csv")
SLOTS = {"defense": ["LHX", "NOC", "HII", "GD", "LMT", "RTX"], "restaurants": ["MCD", "YUM", "SBUX", "CMG", "DRI"], "tobacco": ["PM", "MO"],
         "power": ["NEE", "SO", "DUK", "AEP", "XEL"], "gold": ["GLD", "NEM"], "drinks": ["PEP", "KO"], "drug makers": ["LLY", "MRK", "JNJ", "PFE", "ABBV", "AMGN"],
         "insurance": ["PGR", "CB", "TRV"]}
BUY = re.compile(r"\b(buy|buying|bought|long|bullish|undervalued|cheap|bargain|upgrade[ds]?|accumulat\w+|adding|added|breakout|beat[s]?|raise[sd]?|insider buy\w*|oversold)\b", re.I)
SELL = re.compile(r"\b(sell|selling|sold|short|bearish|overvalued|downgrade[ds]?|miss(es|ed)?|cut[s]?|lawsuit|probe|crash\w*|plunge[sd]?|dump\w*|avoid|trimm\w+)\b", re.I)
RICH = re.compile(r"bubble|overvalued|expensive|nosebleed|\bP/?E\b|\d+\s?[x×]\s?(earnings|P/?E|sales)?|priced for perfection", re.I)


def collect(ticker, months, pages):
    rows = []
    for m in months:
        tweets, capped = fetch(f"${ticker} min_faves:30 lang:en", m.start_time.strftime("%Y-%m-%d"), (m + 1).start_time.strftime("%Y-%m-%d"), pages)
        for t in tweets:
            rows.append(dict(ticker=ticker, month=str(m), capped=capped, id=str(t["id"]), created=t["createdAt"], user=t["author"]["userName"],
                             followers=t["author"].get("followers"), likes=t.get("likeCount"), views=t.get("viewCount"), text=t["text"].replace("\n", " ")))
    print(ticker, {str(m): sum(r["month"] == str(m) for r in rows) for m in months}, flush=True)
    return rows


def summary():
    d = pd.read_csv(OUT)
    d = d[d.apply(lambda r: bool(re.search(r"\$" + re.escape(r.ticker) + r"\b", r.text, re.I)), axis=1)]      # the cashtag itself, not a longer one
    months = sorted(d.month.unique())
    recent, before = months[-2:], months[:-2]
    slot = {t: s for s, names in SLOTS.items() for t in names}
    rows = []
    for t, g in d.groupby("ticker"):
        by = g.groupby("month").id.count().reindex(months, fill_value=0)
        r = g[g.month.isin(recent)]
        buy, sell = r.text.apply(lambda x: bool(BUY.search(x))), r.text.apply(lambda x: bool(SELL.search(x)))
        many = g.text.apply(lambda x: len(re.findall(r"\$[A-Za-z]{1,5}\b", x)) > 6)                             # ticker lists say little about one name
        likes = g.groupby("month").likes.sum().reindex(months, fill_value=0)   # the search returns the most-liked first, so this still means something at the 60-post cap
        rows.append(dict(slot=slot[t], ticker=t, before=by[before].mean(), **{m[5:]: by[m] for m in recent}, heat=by[recent].mean() / max(by[before].mean(), 1),
                         heat_likes=likes[recent].mean() / max(likes[before].mean(), 1), likes_recent=likes[recent].mean(),
                         posts=len(r), tone=(buy.sum() - sell.sum()) / max(len(r), 1) * 100, buy=buy.mean() * 100, sell=sell.mean() * 100,
                         rich_talk=r.text.apply(lambda x: bool(RICH.search(x))).mean() * 100, lists=many[g.month.isin(recent)].mean() * 100, capped=bool(g[g.month.isin(recent)].capped.any())))
    return pd.DataFrame(rows).set_index("ticker"), d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-05")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if not args.summary:
        months = pd.period_range(args.start, pd.Timestamp.now().strftime("%Y-%m"), freq="M")
        tickers = [t for names in SLOTS.values() for t in names]
        with ThreadPoolExecutor(args.workers) as pool:
            rows = [r for part in pool.map(lambda t: collect(t, months, args.pages), tickers) for r in part]
        pd.DataFrame(rows).drop_duplicates(["ticker", "id"]).to_csv(OUT, index=False)
    t, _ = summary()
    pd.set_option("display.width", 220, "display.max_rows", 100, "display.float_format", "{:.1f}".format)
    print(t.sort_values(["slot", "heat"]).to_string())


if __name__ == "__main__":
    main()
