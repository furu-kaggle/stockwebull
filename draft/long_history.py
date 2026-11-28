"""Longer history than Webull gives (1,200 daily bars): daily prices from Yahoo and sales per share from SEC filings.

`prices(symbols)`  daily close and dividend-adjusted close since the first trade (cached per symbol in draft/cache/yahoo)
`sales_per_share(symbol)`  trailing-12-month revenue per diluted share, indexed by the day each filing became public
`ps_rank(symbol)`  where today's price-to-sales stands in its own trailing two years (0-100), as the plan defines it

Usage: python draft/long_history.py   (prints a check of the SEC-based rank against the Webull-based one)
"""
import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd

from indicator_compare import as_of, trailing_rank

HERE = os.path.dirname(os.path.abspath(__file__))
YDIR, SDIR = os.path.join(HERE, "cache", "yahoo"), os.path.join(HERE, "cache", "sec")
AGENT = {"User-Agent": "Mozilla/5.0 (research script)"}
CIK = {"QLYS": 1107843, "TENB": 1660280}                       # others are looked up in the SEC's ticker list
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
SHARE_TAGS = ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
              "WeightedAverageNumberOfShareOutstandingBasicAndDiluted", "WeightedAverageNumberOfSharesOutstandingBasic"]   # loss-making companies report only the later ones


def _get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=40) as r:
                return r.read()
        except Exception:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"could not read {url.split('?')[0]}")


def prices(symbols, refresh=False):
    """{'close': DataFrame, 'adj': DataFrame} of daily prices; 'adj' includes dividends."""
    os.makedirs(YDIR, exist_ok=True)
    close, adj = {}, {}
    for sym in symbols:
        path = os.path.join(YDIR, f"{sym}.csv")
        if refresh or not os.path.exists(path):
            raw = json.loads(_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2=4102444800&interval=1d&events=div%2Csplits"))
            res = raw["chart"]["result"][0]
            day = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
            t = pd.DataFrame({"close": res["indicators"]["quote"][0]["close"], "adj": res["indicators"]["adjclose"][0]["adjclose"]}, index=day).dropna()
            t[~t.index.duplicated(keep="last")].to_csv(path, index_label="date")
            time.sleep(0.4)
        t = pd.read_csv(path, index_col="date", parse_dates=True)
        close[sym], adj[sym] = t.close, t.adj
    return {"close": pd.DataFrame(close).sort_index(), "adj": pd.DataFrame(adj).sort_index()}


def _cik(symbol):
    if symbol in CIK:
        return CIK[symbol]
    path = os.path.join(SDIR, "_tickers.json")
    if not os.path.exists(path):
        open(path, "wb").write(_get("https://www.sec.gov/files/company_tickers.json"))
    table = {row["ticker"]: row["cik_str"] for row in json.load(open(path)).values()}
    return table[symbol.replace(" ", "-")]


def _facts(symbol):
    os.makedirs(SDIR, exist_ok=True)
    path = os.path.join(SDIR, f"{symbol}.json")
    if not os.path.exists(path):
        open(path, "wb").write(_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{_cik(symbol):010d}.json"))
        time.sleep(0.3)
    return json.load(open(path))["facts"]["us-gaap"]


def _periods(facts, tags, unit):
    """One row per reporting period: its value as first filed, and the day of that filing."""
    rows = []
    for prio, tag in enumerate(tags):
        for x in facts.get(tag, {}).get("units", {}).get(unit, []):
            if "start" in x:
                rows.append((pd.Timestamp(x["start"]), pd.Timestamp(x["end"]), float(x["val"]), pd.Timestamp(x["filed"]), prio))
    t = pd.DataFrame(rows, columns=["start", "end", "val", "filed", "prio"])
    # The first filing of each period is what was known at the time; later filings restate, and some carry a
    # wrong period. Within one filing, the earlier tag in `tags` wins.
    t = t.sort_values(["filed", "prio"]).groupby(["start", "end"], as_index=False).first()
    days = (t.end - t.start).dt.days                                   # quarters of 12 or 13 weeks, years of 52 or 53
    t["months"] = np.select([days.between(75, 105), days.between(160, 200), days.between(245, 290), days.between(350, 380)], [3, 6, 9, 12], 0)
    return t


def sales_per_share(symbol):
    facts = _facts(symbol)
    rev, shr = _periods(facts, REVENUE_TAGS, "USD"), _periods(facts, SHARE_TAGS, "shares")
    year = rev[rev.months == 12].set_index("end")
    out = {}
    for end, row in year.iterrows():                                   # a full year is the trailing 12 months as of its filing
        out[row.filed] = (row.val, end)
    cum = rev[rev.months.isin([3, 6, 9])]
    for _, row in cum.iterrows():                                      # year-to-date + last full year - the same year-to-date a year before
        prev_year = year[(year.index < row.end) & (year.index >= row.end - pd.Timedelta(days=330))]
        before = cum[(cum.months == row.months) & ((cum.end - (row.end - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=10))]
        ytd_now = cum[(cum.end == row.end)].sort_values("months").iloc[-1]
        if row.months != ytd_now.months or prev_year.empty:
            continue
        ytd_before = cum[(cum.months == ytd_now.months) & ((cum.end - (row.end - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=10))]
        if ytd_before.empty:
            continue
        out[row.filed] = (ytd_now.val + prev_year.val.iloc[-1] - ytd_before.val.iloc[0], row.end)
    ttm = pd.DataFrame(out, index=["rev", "end"]).T.sort_index()
    ttm = ttm[ttm.end == ttm.end.cummax()]                             # ignore a late restatement of an old period
    quarter_shares = shr.sort_values(["end", "months"]).groupby("end").first().val
    ttm["shares"] = [quarter_shares[quarter_shares.index <= e].iloc[-1] if (quarter_shares.index <= e).any() else np.nan for e in ttm.end]
    return (ttm.rev.astype(float) / ttm.shares).dropna()


SINCE = {"TENB": "2019-06-01"}      # share counts before then mix in the months before the listing (July 2018)


def ps_rank(symbol, close):
    px = close.dropna().loc[SINCE.get(symbol):]
    return trailing_rank(px / as_of(sales_per_share(symbol), px.index)) * 100


if __name__ == "__main__":
    from indicator_compare import load_per_share
    p = prices(["QLYS", "TENB"])
    webull = load_per_share(["QLYS", "TENB"])
    for sym in ("QLYS", "TENB"):
        sps = sales_per_share(sym)
        px = p["close"][sym].dropna()
        mine = ps_rank(sym, px)
        theirs = trailing_rank(px / as_of(webull[sym]["sps"], px.index)) * 100
        both = pd.DataFrame({"sec": mine, "webull": theirs}).dropna()
        print(f"{sym}: sales per share from {sps.index[0].date()} ({sps.iloc[0]:.2f}) to {sps.index[-1].date()} ({sps.iloc[-1]:.2f}); Webull's latest {webull[sym]['sps'].iloc[-1]:.2f}")
        print(f"   rank from {mine.dropna().index[0].date()}; latest {mine.iloc[-1]:.0f} (Webull-based {theirs.iloc[-1]:.0f}); over {len(both)} shared days: correlation {both.corr().iloc[0, 1]:.3f}, average gap {(both.sec - both.webull).abs().mean():.1f} points")
