"""Monthly counts of published CVEs from the NVD API, with a chart.

Counts every CVE by its NVD publication date, plus those NVD scores CRITICAL (CVSS v3).
The API allows 5 requests per 30 seconds without a key, so a full refresh takes several minutes;
finished months are cached in draft/cve_monthly.csv and only missing or recent months are fetched.

Usage: python draft/cve_counts.py [--start 2024-01] [--chart charts/cve_monthly.png]
"""
import argparse
import calendar
import os
import time
from datetime import date

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "cve_monthly.csv")
API = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def count(year, month, last_day, severity=None):
    params = {"pubStartDate": f"{year}-{month:02d}-01T00:00:00.000Z",
              "pubEndDate": f"{year}-{month:02d}-{last_day:02d}T23:59:59.999Z", "resultsPerPage": 1}
    if severity:
        params["cvssV3Severity"] = severity
    for attempt in range(4):
        resp = requests.get(API, params=params, timeout=40)
        if resp.status_code == 200:
            time.sleep(6.5)
            return resp.json()["totalResults"]
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"NVD returned {resp.status_code} for {year}-{month:02d}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01")
    parser.add_argument("--chart", default=os.path.join(HERE, "charts", "cve_monthly.png"))
    args = parser.parse_args()

    today = date.today()
    cached = pd.read_csv(CSV, index_col="month") if os.path.exists(CSV) else pd.DataFrame(columns=["total", "critical", "through"])
    months = pd.period_range(args.start, today.strftime("%Y-%m"), freq="M")
    for p in months:
        key = str(p)
        last = calendar.monthrange(p.year, p.month)[1]
        complete = (p.year, p.month) < (today.year, today.month)
        through = last if complete else today.day
        if key in cached.index and int(cached.loc[key, "through"]) == last:
            continue                                         # a finished month already fetched in full
        cached.loc[key] = [count(p.year, p.month, through), count(p.year, p.month, through, "CRITICAL"), through]
        cached.sort_index().to_csv(CSV, index_label="month")
        print(key, *cached.loc[key].tolist(), flush=True)
    table = cached.sort_index().astype(int)
    table.to_csv(CSV, index_label="month")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    full = table[[calendar.monthrange(int(m[:4]), int(m[5:]))[1] == t for m, t in zip(table.index, table["through"])]]
    partial = table.drop(full.index)
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=160)
    x = range(len(table))
    ax.bar([i for i, m in enumerate(table.index) if m in full.index], full["total"], color="#2563eb", width=0.75)
    ax.bar([i for i, m in enumerate(table.index) if m in partial.index], partial["total"], color="#93c5fd", width=0.75)
    ax.bar(list(x), table["critical"], color="#b91c1c", width=0.75)
    ax.set_xticks([i for i, m in enumerate(table.index) if m.endswith(("-01", "-04", "-07", "-10"))])
    ax.set_xticklabels([m for m in table.index if m.endswith(("-01", "-04", "-07", "-10"))], fontsize=9)
    if "2026-04" in table.index:
        i = list(table.index).index("2026-04")
        ax.axvline(i - 0.5, color="#6b7280", lw=1, ls="--")
        ax.text(i - 0.4, ax.get_ylim()[1] * 0.93, "Claude Mythos / Glasswing\n(Apr 2026)", fontsize=9, color="#374151", va="top")
    fig.text(0.075, 0.95, "CVEs published per month (NVD)", fontsize=13, fontweight="bold", va="top")
    fig.text(0.075, 0.90, "Blue: all CVEs (pale = month still in progress).  Red: scored CRITICAL by NVD.",
             fontsize=9, color="#6b7280", va="top")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.grid(axis="y", color="#e5e7eb", lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.subplots_adjust(left=0.075, right=0.97, top=0.84, bottom=0.08)
    os.makedirs(os.path.dirname(args.chart), exist_ok=True)
    fig.savefig(args.chart)
    print(table.to_string())
    print(args.chart)


if __name__ == "__main__":
    main()
