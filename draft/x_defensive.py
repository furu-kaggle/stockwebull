"""How much is X talking about the places to move to? Monthly counts of English posts above a like threshold.

  rotation   the "move into defensive stocks" story itself
  staples    cashtags of the staples that are already rich (KO, PG, WMT, COST, CL)
  defense    NOC, GD, LMT, RTX
  unloved    PEP, MCD
  bills      Treasury-bill funds and "T-bills"
  core       QLYS, TENB (for comparison)

A rising count means the idea is getting crowded; a flat one means it is not yet a popular trade.
Output: draft/x_defensive.csv.

Usage: python draft/x_defensive.py [--start 2025-11] [--pages 10]
"""
import argparse
import os

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-11")
    parser.add_argument("--pages", type=int, default=10)
    args = parser.parse_args()
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
