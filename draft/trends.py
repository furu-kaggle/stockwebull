"""Does public search interest (Google Trends, US, weekly) say anything about security stocks?

Terms are fetched one at a time so that each is scaled 0-100 against its own five-year history,
then grouped: what specialists search, what the general public searches, and what investors search.
For each term and group the script measures

  spike      this week's interest against the previous 52 weeks (z-score), known by the weekend
  lead       rank correlation between the spike and the sector's return over the next 1 / 4 / 12 weeks
  follow     the same against the return over the previous 4 weeks (is search just reacting to price?)
  events     what the sector did after the weeks with the biggest spikes (z >= 2)

Usage: python draft/trends.py [--refresh] [--target CIBR]
"""
import argparse
import os
import time

import numpy as np
import pandas as pd

from data import load_bars
from universe import UNIVERSE

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "trends_weekly.csv")
GROUPS = {
    "specialist": ["CVE", "zero day", "vulnerability", "patch tuesday"],
    "public": ["data breach", "ransomware", "hacked", "cyber attack", "cybersecurity"],
    "investor": ["cybersecurity stocks", "CrowdStrike stock", "Palo Alto Networks stock"],
}


def fetch(terms, refresh=False):
    cached = pd.read_csv(CSV, index_col=0, parse_dates=True) if os.path.exists(CSV) and not refresh else pd.DataFrame()
    missing = [t for t in terms if t not in cached.columns]
    if missing:
        from pytrends.request import TrendReq
        py = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
        for term in missing:
            for attempt in range(4):
                try:
                    py.build_payload([term], timeframe="today 5-y", geo="US")
                    frame = py.interest_over_time()
                    cached[term] = frame[term]
                    cached.to_csv(CSV)
                    print("fetched", term, flush=True)
                    break
                except Exception as err:
                    print("retry", term, type(err).__name__, flush=True)
                    time.sleep(30 * (attempt + 1))
            time.sleep(6)
    return cached[[t for t in terms if t in cached.columns]]


def spike(series, window=52):
    prior = series.shift(1)
    return (series - prior.rolling(window).mean()) / prior.rolling(window).std()


def rank_corr(x, y, step=1):
    df = pd.concat([x, y], axis=1).dropna().iloc[::step]
    if len(df) < 12:
        return np.nan, 0
    r = df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank())
    return r, len(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--target", default="CIBR")
    args = parser.parse_args()
    terms = [t for group in GROUPS.values() for t in group]
    trends = fetch(terms, args.refresh)

    security = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    close = load_bars(security + ["CIBR", "QQQ"])["close"]
    close["EW22"] = (1 + close[security].pct_change().mean(axis=1).fillna(0)).cumprod()
    # Trends weeks start on Sunday; the week's value is known by the following weekend, so pair it with that Friday's close.
    weekly = close.resample("W-FRI").last()
    weekly.index = weekly.index - pd.Timedelta(days=5)          # label each Friday close by its week's Sunday
    px = weekly[args.target].reindex(trends.index).dropna()
    rel = (weekly[args.target] / weekly["QQQ"]).reindex(trends.index).dropna()
    fwd = {h: px.shift(-h) / px - 1 for h in (1, 4, 12)}
    fwd_rel = {h: rel.shift(-h) / rel - 1 for h in (4, 12)}
    past4 = px / px.shift(4) - 1

    z = trends.apply(spike)
    for group, members in GROUPS.items():
        z[f"[{group} avg]"] = z[[m for m in members if m in z]].mean(axis=1)
    z["[public minus specialist]"] = z["[public avg]"] - z["[specialist avg]"]

    print(f"Weeks with prices and search data: {len(px)}  ({px.index[0].date()} -> {px.index[-1].date()}), target {args.target}\n")
    rows = []
    for name in z.columns:
        row = {"signal": name}
        for h in (1, 4, 12):
            row[f"lead {h}w"], _ = rank_corr(z[name], fwd[h], step=h)
        row["lead 4w vs QQQ"], _ = rank_corr(z[name], fwd_rel[4], step=4)
        row["lead 12w vs QQQ"], _ = rank_corr(z[name], fwd_rel[12], step=12)
        row["follows past 4w"], _ = rank_corr(z[name], past4, step=1)
        hot = z[name] >= 2
        row["spike weeks"] = int(hot.sum())
        row["after spike 4w%"] = fwd[4][hot].mean() * 100
        row["after spike 12w%"] = fwd[12][hot].mean() * 100
        rows.append(row)
    table = pd.DataFrame(rows).set_index("signal")
    pd.set_option("display.width", 230, "display.float_format", "{:.2f}".format)
    print(table.to_string())
    print(f"\nAll weeks, for comparison: next 4w {fwd[4].mean() * 100:.2f}%, next 12w {fwd[12].mean() * 100:.2f}%")
    n4, n12 = len(px) // 4, len(px) // 12
    print(f"Rough noise level for a correlation of zero: +/-{2 / np.sqrt(n4):.2f} at 4 weeks ({n4} separate samples), "
          f"+/-{2 / np.sqrt(n12):.2f} at 12 weeks ({n12})\n")

    print("Biggest public-interest spikes and what followed:")
    top = z["[public avg]"].dropna().nlargest(8).sort_index()
    for week, value in top.items():
        lead = max(GROUPS["public"], key=lambda t: z.loc[week, t] if t in z and not np.isnan(z.loc[week, t]) else -9)
        f4 = fwd[4].get(week, np.nan); f12 = fwd[12].get(week, np.nan)
        print(f"  {week.date()}  z={value:4.1f}  led by '{lead}'  specialist z={z.loc[week, '[specialist avg]']:4.1f}"
              f"   {args.target} next 4w {f4 * 100:+5.1f}%  next 12w {f12 * 100:+5.1f}%")
    latest = z.dropna(how="all").iloc[-2]                        # last complete week
    print(f"\nLatest complete week ({z.dropna(how='all').index[-2].date()}): specialist z={latest['[specialist avg]']:.2f}, "
          f"public z={latest['[public avg]']:.2f}, investor z={latest['[investor avg]']:.2f}")
    z.round(3).to_csv(os.path.join(HERE, "trends_spikes.csv"))


if __name__ == "__main__":
    main()
