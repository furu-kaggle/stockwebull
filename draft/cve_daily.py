"""Daily counts of published CVEs from the NVD API for the last N days (default 35).

Pages through the publications in the window and counts them by UTC publication date.
The last day or two are incomplete: NVD publishes with a lag. Output: draft/cve_daily.csv.

Usage: python draft/cve_daily.py [--days 35]
"""
import argparse
import os
import time

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def page(start, end, index):
    params = {"pubStartDate": start, "pubEndDate": end, "resultsPerPage": 2000, "startIndex": index}
    for attempt in range(6):
        try:
            resp = requests.get(API, params=params, timeout=120)
            if resp.status_code == 200:
                time.sleep(6.5)                              # 5 requests per 30 seconds without a key
                return resp.json()
        except requests.RequestException:
            pass
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"NVD failed at index {index}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=35)
    args = parser.parse_args()
    end = pd.Timestamp.now(tz="UTC")
    start = (end - pd.Timedelta(days=args.days)).normalize()
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    rows, index, total = [], 0, None
    while total is None or index < total:
        data = page(start.strftime(fmt), end.strftime(fmt), index)
        total = data["totalResults"]
        for item in data["vulnerabilities"]:
            cve = item["cve"]
            sev = None
            for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
                m = cve.get("metrics", {}).get(key)
                if m:
                    sev = m[0]["cvssData"].get("baseSeverity")
                    break
            rows.append((cve["published"][:10], cve.get("sourceIdentifier", ""), sev))
        index += len(data["vulnerabilities"]) or 2000
    df = pd.DataFrame(rows, columns=["date", "source", "severity"])
    daily = df.groupby("date").agg(total=("date", "size"), critical=("severity", lambda s: (s == "CRITICAL").sum()),
                                   high=("severity", lambda s: (s == "HIGH").sum()), scored=("severity", lambda s: s.notna().sum()))
    daily.to_csv(os.path.join(HERE, "cve_daily.csv"))
    df.to_csv(os.path.join(HERE, "cache", "cve_daily_raw.csv"), index=False)
    print(daily.to_string())
    print("total", total, "top sources", df.source.value_counts().head(8).to_dict())


if __name__ == "__main__":
    main()
