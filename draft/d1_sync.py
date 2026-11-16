"""Copy the X posts in draft/x_posts.csv into the Cloudflare D1 database `stockwebull` (table x_posts).

Rows are upserted by post id, so the script can be run again at any time as the CSV grows.
The Cloudflare API token is injected by the session's network proxy; outside this environment set
CLOUDFLARE_API_TOKEN (needs D1 edit permission on the account).

Usage: python draft/d1_sync.py [--check]
"""
import argparse
import os
import time

import pandas as pd
import requests

from x_sentiment import POSTS, QUERY, is_relevant

ACCOUNT = "5b9d56560a49281cb1e711282a1f4260"
DATABASE = "31f8892f-6e57-4187-b903-8ba2e64e752b"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DATABASE}/query"
HEADERS = {"Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_TOKEN', 'proxy-injected')}"}
BATCH = 50                                                     # rows per statement (kept well under D1's statement size limit)


def lit(value):
    """SQL literal for a value: NULL, a number, or a quoted string with quotes doubled."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(int(value))
    return "'" + str(value).replace("'", "''").replace("\x00", "") + "'"


def run(sql):
    for attempt in range(5):
        resp = requests.post(URL, headers=HEADERS, json={"sql": sql}, timeout=60)
        if resp.status_code != 429:                            # Cloudflare asks callers to slow down now and then
            break
        time.sleep(10 * (attempt + 1))
    body = resp.json()
    if resp.status_code != 200 or not body.get("success"):
        raise RuntimeError(f"D1 query failed ({resp.status_code}): {str(body.get('errors'))[:300]}")
    return body["result"][0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only report what is in D1")
    args = parser.parse_args()
    if not args.check:
        posts = pd.read_csv(POSTS, dtype={"id": str})
        posts = posts[posts["id"].notna()].drop_duplicates("id")
        posts["specialist"] = posts["specialist"].astype(str).eq("True")
        posts["verified"] = posts["verified"].astype(str).eq("True")
        kinds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_kinds.csv")
        if os.path.exists(kinds_path):                         # classification from x_classify.py
            kinds = pd.read_csv(kinds_path, dtype={"id": str}).rename(columns={"source": "kind_source"})
            posts = posts.merge(kinds[["id", "kind", "kind_source"]], on="id", how="left")
        else:
            posts["kind"], posts["kind_source"] = None, None
        query = lit(QUERY)
        for start in range(0, len(posts), BATCH):
            chunk = posts.iloc[start:start + BATCH]
            values = ",".join(
                "(" + ",".join([lit(r.id), lit(r.week), lit(r.created), lit(r.user), lit(r.followers), lit(bool(r.verified)),
                                lit(bool(r.specialist)), lit(r.likes), lit(r.reposts), lit(r.replies), lit(r.views), lit(r.text), query,
                                lit(None if pd.isna(r.bio) else r.bio), lit(is_relevant(r.text)),
                                lit(None if pd.isna(r.kind) else r.kind), lit(None if pd.isna(r.kind_source) else r.kind_source)]) + ")"
                for r in chunk.itertuples())
            run("INSERT INTO x_posts (id, week, created_at, user_name, followers, verified, specialist, likes, reposts, replies, views, text, query, bio, relevant, kind, kind_source) "
                f"VALUES {values} ON CONFLICT(id) DO UPDATE SET likes=excluded.likes, reposts=excluded.reposts, replies=excluded.replies, "
                "views=excluded.views, followers=excluded.followers, specialist=excluded.specialist, text=excluded.text, bio=excluded.bio, "
                "relevant=excluded.relevant, kind=excluded.kind, kind_source=excluded.kind_source, fetched_at=datetime('now')")
        print(f"sent {len(posts)} posts")
    summary = run("SELECT COUNT(*) AS posts, COUNT(DISTINCT week) AS weeks, MIN(week) AS first_week, MAX(week) AS last_week, "
                  "SUM(likes) AS likes, SUM(specialist) AS specialist_posts, SUM(relevant) AS relevant_posts FROM x_posts")["results"][0]
    print("in D1:", summary)


if __name__ == "__main__":
    main()
