"""X (Twitter) attention to security incidents, week by week, and whether it reaches beyond specialists.

For every week the script pulls the most-engaged English posts (1,000+ likes) that mention security
incidents or vulnerabilities, via twitterapi.io (key in TWITTERAPI_IO_SECRET; billed per post read).
Each author is tagged "specialist" when their name or bio reads as security / hacking / threat
research, otherwise "general" (news outlets, commentators, companies, ordinary accounts).

  heat          total likes on those posts
  public reach  likes on posts written by general accounts
  public share  public reach as a share of the heat

`fetch` downloads missing weeks into draft/x_posts.csv (finished weeks are never fetched twice);
`analyze` compares weekly spikes with the security ETF's later returns and with Google Trends.

Usage: python draft/x_sentiment.py fetch [--start 2022-01-30] [--pages 3]
       python draft/x_sentiment.py analyze
"""
import argparse
import os
import re
import time

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "x_posts.csv")
API = "https://api.twitterapi.io/twitter/tweet/advanced_search"
QUERY = ('("zero-day" OR 0day OR CVE OR ransomware OR "data breach" OR cyberattack OR "cyber attack" '
         'OR "security vulnerability") min_faves:1000 lang:en')
SPECIALIST = re.compile(r"secur|infosec|cyber|hack|malware|threat|vuln|exploit|pentest|red ?team|bug ?bount|ransom|"
                        r"reverse engineer|ciso|osint|forensic|0day|zero.?day|cve|breach", re.I)
RELEVANT = re.compile(r"hack|breach|ransomware|malware|exploit|vulnerab|cve-?\d|cyber ?attack|cybersecurity|phishing|spyware|botnet|"
                      r"zero.?day (exploit|vuln|bug|flaw|attack)|0day|patch(ed|es)?\b|stolen data|leaked? (data|database|password)|"
                      r"infosec|security (flaw|bug|hole|update|researcher|incident|advisory)|ddos|backdoor", re.I)
COLUMNS = ["week", "id", "created", "user", "followers", "verified", "specialist", "likes", "reposts", "replies", "views", "text", "bio"]


def is_relevant(text):
    """True when a post reads as being about a security incident or flaw, not just a keyword coincidence."""
    return bool(RELEVANT.search(str(text)))


def fetch_week(session, since, until, pages):
    rows, cursor, complete = [], "", True
    for page in range(pages):
        for attempt in range(4):
            try:
                resp = session.get(API, params={"query": f"{QUERY} since:{since} until:{until}", "queryType": "Top", "cursor": cursor}, timeout=60)
                if resp.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"twitterapi.io failed for week {since}")
        body = resp.json()
        for t in body.get("tweets", []):
            a = t.get("author") or {}
            about = ((a.get("profile_bio") or {}).get("description") or a.get("description") or "").replace("\n", " ").replace("\r", " ")
            bio = f"{a.get('name', '')} {a.get('userName', '')} {about}"
            rows.append([since, t.get("id"), t.get("createdAt"), a.get("userName"), a.get("followers"), bool(a.get("isBlueVerified")),
                         bool(SPECIALIST.search(bio)), t.get("likeCount"), t.get("retweetCount"), t.get("replyCount"), t.get("viewCount"),
                         (t.get("text") or "").replace("\n", " ").replace("\r", " ")[:400], about[:200]])
        if not body.get("has_next_page") or not body.get("tweets"):
            break
        cursor = body.get("next_cursor", "")
        complete = page < pages - 1
    return rows, complete


def fetch(args):
    done = pd.read_csv(POSTS) if os.path.exists(POSTS) else pd.DataFrame(columns=COLUMNS)
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    weeks = [w for w in pd.date_range(args.start, today, freq="W-SUN") if w + pd.Timedelta(days=7) <= today]
    have = set(done["week"].astype(str))
    session = requests.Session()
    session.headers["X-API-Key"] = os.environ["TWITTERAPI_IO_SECRET"]
    for week in weeks:
        key = week.date().isoformat()
        if key in have:
            continue
        rows, _ = fetch_week(session, key, (week + pd.Timedelta(days=7)).date().isoformat(), args.pages)
        if not rows:                                           # remember empty weeks too
            rows = [[key, None, None, None, None, None, None, 0, 0, 0, 0, "", ""]]
        done = pd.concat([done, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
        done.to_csv(POSTS, index=False)
        print(key, len(rows), flush=True)
    print("weeks stored:", done["week"].nunique(), "posts:", int(done["id"].notna().sum()))


def weekly_table():
    posts = pd.read_csv(POSTS, parse_dates=["week"])
    posts = posts[posts["id"].notna()].drop_duplicates("id")
    posts["specialist"] = posts["specialist"].astype(str).eq("True")
    posts = posts[posts["text"].map(is_relevant)]               # drop keyword coincidences
    grouped = posts.groupby("week")
    table = pd.DataFrame({
        "posts": grouped.size(),
        "heat": grouped["likes"].sum(),
        "public_reach": posts[~posts.specialist].groupby("week")["likes"].sum(),
        "views": grouped["views"].sum(),
    }).fillna(0)
    all_weeks = pd.read_csv(POSTS, parse_dates=["week"])["week"].drop_duplicates().sort_values()
    table = table.reindex(all_weeks, fill_value=0)
    table["public_share"] = (table["public_reach"] / table["heat"]).where(table["heat"] > 0) * 100
    return table, posts


def spike(series, window=26):
    logged = np.log1p(series)
    prior = logged.shift(1)
    return (logged - prior.rolling(window, min_periods=12).mean()) / prior.rolling(window, min_periods=12).std()


def rank_corr(x, y, step=1):
    df = pd.concat([x, y], axis=1).dropna().iloc[::step]
    return df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank()) if len(df) >= 12 else np.nan


def analyze(args):
    from data import load_bars
    table, posts = weekly_table()
    if args.since:                                             # work on one continuous stretch of weeks
        table, posts = table[table.index >= args.since], posts[posts.week >= args.since]
    close = load_bars(["CIBR", "QQQ"])["close"]
    weekly = close.resample("W-FRI").last()
    weekly.index = weekly.index - pd.Timedelta(days=5)          # label each Friday close by its week's Sunday
    px = weekly["CIBR"].reindex(table.index).dropna()
    fwd = {h: px.shift(-h) / px - 1 for h in (1, 4, 12)}
    past4 = px / px.shift(4) - 1
    signals = {"heat (all likes)": spike(table["heat"]), "public reach (likes on general accounts)": spike(table["public_reach"]),
               "specialist likes": spike(table["heat"] - table["public_reach"]), "public share": table["public_share"]}
    pd.set_option("display.width", 230, "display.float_format", "{:.2f}".format)
    print(f"{len(table)} weeks, {len(posts)} posts with 1,000+ likes; {posts.specialist.mean() * 100:.0f}% by specialist accounts\n")
    rows = []
    for name, sig in signals.items():
        hot = sig >= (2 if name != "public share" else sig.quantile(0.9))
        rows.append({"signal": name, "lead 1w": rank_corr(sig, fwd[1]), "lead 4w": rank_corr(sig, fwd[4], 4), "lead 12w": rank_corr(sig, fwd[12], 12),
                     "follows past 4w": rank_corr(sig, past4), "spike weeks": int(hot.sum()),
                     "after spike 4w%": fwd[4][hot].mean() * 100, "after spike 12w%": fwd[12][hot].mean() * 100})
    print(pd.DataFrame(rows).set_index("signal").to_string())
    print(f"\nAll weeks, for comparison: next 4w {fwd[4].mean() * 100:.2f}%, next 12w {fwd[12].mean() * 100:.2f}%")
    n4, n12 = len(px) // 4, len(px) // 12
    print(f"Rough noise level for a correlation of zero: +/-{2 / np.sqrt(n4):.2f} at 4 weeks, +/-{2 / np.sqrt(n12):.2f} at 12 weeks\n")

    trends_path = os.path.join(HERE, "trends_spikes.csv")
    if os.path.exists(trends_path):
        trends = pd.read_csv(trends_path, index_col=0, parse_dates=True)
        for col in ("[public avg]", "[specialist avg]", "[investor avg]"):
            print(f"X public-reach spike vs Google Trends {col}: {rank_corr(signals['public reach (likes on general accounts)'], trends[col]):.2f}")
    print("\nBiggest public-reach weeks and what followed:")
    reach = signals["public reach (likes on general accounts)"]
    for week in reach.dropna().nlargest(8).sort_index().index:
        top = posts[(posts.week == week) & ~posts.specialist].nlargest(1, "likes")
        text = top["text"].iloc[0][:70] if len(top) else ""
        print(f"  {week.date()}  z={reach[week]:4.1f}  share {table.loc[week, 'public_share']:3.0f}%  CIBR next 4w {fwd[4].get(week, np.nan) * 100:+5.1f}%"
              f"  12w {fwd[12].get(week, np.nan) * 100:+5.1f}%  | {text}")
    recent = table.tail(6).assign(heat_z=signals["heat (all likes)"].tail(6), public_z=reach.tail(6))
    print("\nLast six weeks:"); print(recent.to_string())
    table.assign(heat_z=signals["heat (all likes)"], public_z=reach).round(3).to_csv(os.path.join(HERE, "x_weekly.csv"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["fetch", "analyze"])
    parser.add_argument("--start", default="2022-01-30")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--since", help="analyze only weeks on or after this date")
    args = parser.parse_args()
    (fetch if args.command == "fetch" else analyze)(args)


if __name__ == "__main__":
    main()
