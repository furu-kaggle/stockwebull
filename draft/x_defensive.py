"""How much is X talking about the places to move to? Monthly counts of English posts above a like threshold.

  rotation   the "move into defensive stocks" story itself
  staples    cashtags of the staples that are already rich (KO, PG, WMT, COST, CL)
  defense    NOC, GD, LMT, RTX
  unloved    PEP, MCD
  bills      Treasury-bill funds and "T-bills"
  core       QLYS, TENB (for comparison)

A rising count means the idea is getting crowded; a flat one means it is not yet a popular trade.
Output: draft/x_defensive.csv.

Usage: python draft/x_defensive.py [--start 2025-11] [--pages 10] [--summary]
"""
import argparse
import os
import re

import pandas as pd

from x_vuln_future import fetch

HERE = os.path.dirname(os.path.abspath(__file__))
TALK = "(stock OR stocks OR shares OR buy OR buying OR long OR bullish OR portfolio)"
QUERIES = {
    "rotation": '("defensive stocks" OR "consumer staples" OR "staples stocks" OR "defensive rotation" OR "rotation into defensives" OR "flight to safety") min_faves:100 lang:en',
    "staples": f'($KO OR $PG OR $WMT OR $COST OR $CL) {TALK} min_faves:50 lang:en',
    "defense": f'($NOC OR $GD OR $LMT OR $RTX) {TALK} min_faves:50 lang:en',
    "unloved": f'($PEP OR $MCD) {TALK} min_faves:50 lang:en',
    "bills": '($SGOV OR $SHV OR $BIL OR "T-bills" OR "treasury bills") min_faves:100 lang:en',
    "core": f'($QLYS OR $TENB) {TALK} min_faves:10 lang:en',
}


MARKET = re.compile(r"stock|staples|\$[A-Za-z]{1,5}\b|market|investor|portfolio|equit|rally|sell-?off|S&P|nasdaq", re.I)
NOT_MARKET = re.compile(r"pick & roll|pick &amp; roll|basketball|NBA|Army|troops", re.I)          # "defensive rotation" is also a basketball term
VALUATION = re.compile(r"bubble|overvalued|expensive|\bP/?E\b|\d+\s?[x×]\b|multiple|priced for|nosebleed|rich valuation", re.I)
TICKERS = ["KO", "WMT", "COST", "PG", "NOC", "GD", "LMT", "RTX", "PEP", "MCD"]


def summary():
    """Monthly counts from the saved posts: the rotation story (market posts only), staples posts that talk about
    valuation, and posts naming each ticker (any of the searches)."""
    d = pd.read_csv(os.path.join(HERE, "x_defensive.csv"))
    months = sorted(d.month.unique())
    count = lambda rows: rows.groupby("month").id.count().reindex(months, fill_value=0)
    rotation = count(d[(d.q == "rotation") & d.text.apply(lambda t: bool(MARKET.search(t)) and not NOT_MARKET.search(t))])
    valuation = count(d[(d.q == "staples") & d.text.apply(lambda t: bool(VALUATION.search(t)))])
    tickers = pd.DataFrame({sym: count(d[d.text.str.contains(r"\$" + sym + r"\b", case=False, regex=True)].drop_duplicates("id")) for sym in TICKERS})
    return rotation, valuation, tickers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-11")
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--summary", action="store_true", help="print the counts from the saved posts without searching again")
    args = parser.parse_args()
    if args.summary:
        rotation, valuation, tickers = summary()
        pd.set_option("display.width", 200)
        print(pd.DataFrame({"rotation story": rotation, "staples posts on valuation": valuation}).join(tickers).to_string())
        return
    months = pd.period_range(args.start, pd.Timestamp.now().strftime("%Y-%m"), freq="M")
    rows = []
    for name, query in QUERIES.items():
        for m in months:
            tweets, capped = fetch(query, m.start_time.strftime("%Y-%m-%d"), (m + 1).start_time.strftime("%Y-%m-%d"), args.pages)
            for t in tweets:
                rows.append(dict(q=name, month=str(m), capped=capped, id=str(t["id"]), created=t["createdAt"], user=t["author"]["userName"],
                                 followers=t["author"].get("followers"), likes=t.get("likeCount"), reposts=t.get("retweetCount"),
                                 views=t.get("viewCount"), text=t["text"].replace("\n", " ")))
            print(name, m, len(tweets), "capped" if capped else "", flush=True)
        pd.DataFrame(rows).drop_duplicates(["q", "id"]).to_csv(os.path.join(HERE, "x_defensive.csv"), index=False)


if __name__ == "__main__":
    main()
