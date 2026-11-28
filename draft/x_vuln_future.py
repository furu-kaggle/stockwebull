"""English posts on X about where software vulnerabilities are heading, by month.

Three searches, each paged until it runs out or hits the page cap, so the monthly count is a real
count of posts above the like threshold (1,000 likes for the two topic searches, 10 for the stock one;
a month that hits the cap is marked). Output: draft/x_vuln_future.csv.

Usage: python draft/x_vuln_future.py [--start 2025-11] [--pages 10]
"""
import argparse
import os
import time

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.twitterapi.io/twitter/tweet/advanced_search"
QUERIES = {
    "ai_finds_bugs": '(vulnerabilities OR vulnerability OR CVE OR CVEs OR "zero-day" OR "zero-days" OR "0day") (AI OR LLM OR Mythos OR agents OR "AI-discovered" OR "AI-found") min_faves:1000 lang:en',
    "outlook": '(vulnerabilities OR CVEs OR "vulnerability management" OR patching) ("next year" OR future OR 2027 OR tsunami OR flood OR explosion OR backlog OR "going to" OR "will be") min_faves:1000 lang:en',
    "stocks": '($TENB OR $QLYS OR $RPD OR "vulnerability management" OR "exposure management") (stock OR stocks OR shares OR bullish OR long OR buy) min_faves:10 lang:en',
}


def fetch(query, start, end, pages):
    key, cursor, out, capped = os.environ["TWITTERAPI_IO_SECRET"], "", [], False
    for page in range(pages):
        data, tweets = {}, []
        for attempt in range(4):                                # the search sometimes comes back empty; ask again before believing it
            try:
                data = requests.get(API, headers={"X-API-Key": key}, params={"query": f"{query} since:{start} until:{end}", "queryType": "Top", "cursor": cursor}, timeout=60).json()
                tweets = data.get("tweets", [])
                if tweets or (page > 0 and attempt >= 1):
                    break
            except Exception:
                pass
            time.sleep(2 + attempt)
        out += tweets
        if not tweets or not data.get("has_next_page"):
            break
        cursor = data.get("next_cursor", "")
        capped = page == pages - 1
        time.sleep(0.15)
    return out, capped


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
    df = pd.DataFrame(rows).drop_duplicates(["q", "id"])
    df.to_csv(os.path.join(HERE, "x_vuln_future.csv"), index=False)


if __name__ == "__main__":
    main()
