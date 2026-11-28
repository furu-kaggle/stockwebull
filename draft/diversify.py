"""Research on where to put money outside the security sector.

`load()` returns daily closes for the candidates and the reference series (cached in draft/cache).
Run as a script for the first screen: how each candidate behaves against the security names.

Usage: python draft/diversify.py [--refresh]
"""
import os
import sys
import time

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from universe import UNIVERSE

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "div_bars.pkl")
SEC = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
CORE = ["QLYS", "TENB"]
REF = ["QQQ", "SPY", "IWM", "CIBR", "IGV"]

CANDIDATES = {
    # sector funds
    "XLP": ("sector", "consumer staples"), "XLU": ("sector", "utilities"), "XLV": ("sector", "health care"), "XLE": ("sector", "energy"),
    "XLF": ("sector", "financials"), "XLI": ("sector", "industrials"), "XLB": ("sector", "materials"), "XLRE": ("sector", "real estate"),
    "XLY": ("sector", "consumer discretionary"), "XLC": ("sector", "communication"), "XLK": ("sector", "technology"), "ITA": ("sector", "aerospace & defense"),
    # style funds
    "USMV": ("style", "low volatility"), "SPLV": ("style", "low volatility S&P"), "QUAL": ("style", "quality"), "VTV": ("style", "value"),
    "SCHD": ("style", "dividend"), "NOBL": ("style", "dividend growers"), "RSP": ("style", "equal-weight S&P"), "COWZ": ("style", "cash-flow yield"), "MTUM": ("style", "momentum"),
    # bonds and cash
    "SGOV": ("bond", "0-3 month Treasuries"), "BIL": ("bond", "1-3 month Treasuries"), "SHY": ("bond", "1-3 year Treasuries"), "IEF": ("bond", "7-10 year Treasuries"),
    "TLT": ("bond", "20+ year Treasuries"), "TIP": ("bond", "inflation-linked"), "LQD": ("bond", "investment-grade credit"), "HYG": ("bond", "high yield"), "FLOT": ("bond", "floating rate"),
    # commodities, currency, trend
    "GLD": ("real", "gold"), "SLV": ("real", "silver"), "DBC": ("real", "commodity basket"), "USO": ("real", "oil"), "URA": ("real", "uranium"), "CPER": ("real", "copper"),
    "UUP": ("real", "US dollar"), "DBMF": ("trend", "managed futures"), "KMLM": ("trend", "managed futures"),
    # other regions
    "EFA": ("region", "developed ex-US"), "EEM": ("region", "emerging"), "EWJ": ("region", "Japan"), "FXI": ("region", "China"), "INDA": ("region", "India"), "EWU": ("region", "UK"),
    # defensive retailers and staples
    "WMT": ("staple", "Walmart"), "COST": ("staple", "Costco"), "DG": ("staple", "Dollar General"), "DLTR": ("staple", "Dollar Tree"), "KR": ("staple", "Kroger"),
    "KO": ("staple", "Coca-Cola"), "PEP": ("staple", "PepsiCo"), "PG": ("staple", "Procter & Gamble"), "CL": ("staple", "Colgate"), "MCD": ("staple", "McDonald's"),
    "PM": ("staple", "Philip Morris"), "MO": ("staple", "Altria"), "CPB": ("staple", "Campbell's"), "GIS": ("staple", "General Mills"),
    # health care
    "JNJ": ("health", "Johnson & Johnson"), "LLY": ("health", "Eli Lilly"), "UNH": ("health", "UnitedHealth"), "MRK": ("health", "Merck"), "ABBV": ("health", "AbbVie"), "AMGN": ("health", "Amgen"),
    # defense and physical security
    "LMT": ("defense", "Lockheed Martin"), "NOC": ("defense", "Northrop Grumman"), "RTX": ("defense", "RTX"), "GD": ("defense", "General Dynamics"),
    "MSI": ("physical", "Motorola Solutions"), "ALLE": ("physical", "Allegion"), "AXON": ("physical", "Axon"), "UI": ("physical", "Ubiquiti"),
    # exchanges, insurers, payments
    "CBOE": ("finance", "Cboe (volatility trading)"), "CME": ("finance", "CME (futures exchange)"), "ICE": ("finance", "ICE (exchange)"), "PGR": ("finance", "Progressive"),
    "CB": ("finance", "Chubb"), "TRV": ("finance", "Travelers"), "JPM": ("finance", "JPMorgan"), "V": ("finance", "Visa"),
    # energy, power, waste
    "XOM": ("energy", "Exxon"), "CVX": ("energy", "Chevron"), "NEE": ("power", "NextEra"), "SO": ("power", "Southern"), "DUK": ("power", "Duke"),
    "WM": ("waste", "Waste Management"), "RSG": ("waste", "Republic Services"),
}


def fetch(data, symbols, count=1200):
    rows, missing = [], []
    for i in range(0, len(symbols), 5):
        chunk = symbols[i:i + 5]
        for attempt in range(4):
            try:
                resp = data.market_data.get_batch_history_bar(chunk, "US_STOCK", "D", count=str(count)).json()
                break
            except Exception as err:
                if "INVALID_SYMBOL" in str(err) or "not exist" in str(err):          # find the bad one by asking one at a time
                    resp = {"result": []}
                    for s in chunk:
                        try:
                            resp["result"] += data.market_data.get_batch_history_bar([s], "US_STOCK", "D", count=str(count)).json()["result"]
                        except Exception:
                            missing.append(s)
                        time.sleep(0.5)
                    break
                time.sleep(5 * (attempt + 1))
                resp = {"result": []}
        for item in resp["result"]:
            for b in item.get("result") or []:
                rows.append((pd.Timestamp(b["time"]).tz_convert("America/New_York").normalize().tz_localize(None), item["symbol"], float(b["close"])))
        time.sleep(0.4)
    long = pd.DataFrame(rows, columns=["date", "symbol", "close"]).drop_duplicates(["date", "symbol"])
    return long.pivot(index="date", columns="symbol", values="close").sort_index(), missing


def load(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return pd.read_pickle(CACHE)
    close, missing = fetch(DataClient(make_client()), sorted(set(SEC + REF + list(CANDIDATES))))
    if missing:
        print("no data for:", missing)
    close.to_pickle(CACHE)
    return close


def reference(ret):
    sec = ret[[s for s in SEC if s in ret.columns]]
    return pd.DataFrame({"sector": sec.mean(axis=1), "core": ret[CORE].mean(axis=1), "QQQ": ret["QQQ"]})


def screen(close, days=250):
    ret = close.pct_change()
    ref = reference(ret)
    r, f = ret.iloc[-days:], ref.iloc[-days:]
    bad_sector = f.sector[f.sector <= f.sector.quantile(0.1)].index
    bad_qqq = f.QQQ[f.QQQ <= f.QQQ.quantile(0.1)].index
    rows = []
    for sym, (group, what) in CANDIDATES.items():
        if sym not in r or r[sym].count() < days * 0.9:
            continue
        x = r[sym]
        c = close[sym].dropna()
        rows.append(dict(sym=sym, group=group, what=what, corr_sector=x.corr(f.sector), corr_core=x.corr(f.core), corr_qqq=x.corr(f.QQQ),
                         on_bad_sector=x[bad_sector].mean() * 100, on_bad_qqq=x[bad_qqq].mean() * 100,
                         vol=x.std() * np.sqrt(252) * 100, ret_1y=(c.iloc[-1] / c.iloc[-days] - 1) * 100,
                         dd_1y=((c.iloc[-days:] / c.iloc[-days:].cummax()) - 1).min() * 100))
    t = pd.DataFrame(rows).set_index("sym")
    print(f"sector on its worst 10% days {f.sector[bad_sector].mean() * 100:.2f}%   QQQ on its worst 10% days {f.QQQ[bad_qqq].mean() * 100:.2f}%   ({len(bad_sector)} days each)")
    return t


if __name__ == "__main__":
    close = load(refresh="--refresh" in sys.argv)
    print("symbols", close.shape[1], "from", close.index[0].date(), "to", close.index[-1].date())
    short = close.count()[close.count() < 1000]
    print("short histories:", short.to_dict())
    t = screen(close)
    pd.set_option("display.width", 250, "display.max_rows", 200)
    print(t.drop(columns="what").sort_values("corr_sector").round(2).to_string())
    t.to_csv(os.path.join(HERE, "cache", "div_screen_1y.csv"))
