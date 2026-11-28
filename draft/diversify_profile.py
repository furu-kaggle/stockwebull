"""What the candidates look like today: are the places to move to themselves stretched?

For each stock: where the price stands (one-year return, gap to the one-year high, the plan's band check),
valuation against its own two years (P/S and P/E rank, the yardstick the plan uses for the core), growth and
margin from the last four quarters, what analysts expect, the last five days of large orders, and the next
earnings date. Funds get the price columns only.

Usage: python draft/diversify_profile.py [--refresh]
"""
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from diversify import fetch
from indicator_compare import as_of, trailing_rank

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "div_profile.pkl")
STOCKS = {"defense": ["NOC", "LMT", "GD", "RTX"], "health": ["LLY", "AMGN", "MRK", "JNJ", "ABBV", "UNH"], "insurers": ["CB", "TRV", "PGR"],
          "staples": ["DG", "WMT", "COST", "KO", "PEP", "PG", "CL", "MO", "MCD"], "exchanges": ["CBOE", "CME"], "energy": ["XOM", "CVX"],
          "power": ["DUK", "SO", "NEE"], "waste": ["WM"], "now in the plan": ["UI", "AXON"], "core": ["QLYS", "TENB"]}
FUNDS = {"SHV": "0-1 year Treasuries", "VGSH": "1-3 year Treasuries", "ITA": "defense fund", "XLV": "health fund", "XLP": "staples fund", "XLU": "utilities fund",
         "XLE": "energy fund", "HDV": "high-dividend fund", "VYM": "high-dividend fund", "GLD": "gold", "SPY": "S&P 500", "QQQ": "Nasdaq 100"}


def number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def pull(data, symbols):
    """Quarterly income, analyst view, large-order flow and earnings calendar for each stock."""
    out = {}
    for sym in symbols:
        item = {}
        for key, call in (("income", lambda: data.fundamentals.get_financials_income(sym, type="QUARTERLY", count=20).json()),
                          ("rating", lambda: data.instrument.get_analyst_rating(sym).json()),
                          ("target", lambda: data.instrument.get_analyst_target_price(sym).json()),
                          ("flow", lambda: data.fundamentals.get_capital_flow(sym, count=5).json()),
                          ("calendar", lambda: data.fundamentals.get_earnings_calendar(sym).json())):
            for attempt in range(3):
                try:
                    item[key] = call()
                    break
                except Exception as err:
                    item[key] = None
                    if "429" not in str(err) and "TOO_MANY" not in str(err):
                        break
                    time.sleep(4 * (attempt + 1))
            time.sleep(0.25)
        out[sym] = item
    return out


def profile(sym, raw, close):
    px = close[sym].dropna()
    row = dict(price=px.iloc[-1], ret_1y=(px.iloc[-1] / px.iloc[-251] - 1) * 100, from_high=(px.iloc[-1] / px.iloc[-250:].max() - 1) * 100,
               above_band=bool(px.iloc[-1] > px.iloc[-20:].mean() + px.iloc[-20:].std()),
               z50=(np.log(px.iloc[-1]) - np.log(px.iloc[-50:]).mean()) / np.log(px.iloc[-50:]).std())
    if raw is None:
        return row
    inc = pd.DataFrame(raw.get("income") or [])
    if len(inc) >= 8:
        inc = inc.assign(pub=pd.to_datetime(inc.publish_date), end=pd.to_datetime(inc.end_date)).sort_values("end")
        rev, net, op = (pd.to_numeric(inc[c], errors="coerce") for c in ("total_revenue", "net_income", "op_income"))
        shares = pd.to_numeric(inc.diluted_avg_shares, errors="coerce")
        sps = pd.Series((rev / shares).rolling(4).sum().values, index=inc.pub.values).dropna().groupby(level=0).last().sort_index()
        eps = pd.Series((net / shares).rolling(4).sum().values, index=inc.pub.values).dropna().groupby(level=0).last().sort_index()
        ps, pe = px / as_of(sps, px.index), (px / as_of(eps, px.index)).where(lambda v: v > 0)
        row.update(ps=ps.iloc[-1], ps_rank=trailing_rank(ps).iloc[-1] * 100, pe=pe.iloc[-1], pe_rank=trailing_rank(pe.dropna()).iloc[-1] * 100 if pe.notna().sum() > 250 else np.nan,
                   growth=(rev.iloc[-4:].sum() / rev.iloc[-8:-4].sum() - 1) * 100, growth_before=(rev.iloc[-8:-4].sum() / rev.iloc[-12:-8].sum() - 1) * 100 if len(inc) >= 12 else np.nan,
                   op_margin=op.iloc[-4:].sum() / rev.iloc[-4:].sum() * 100, net_margin=net.iloc[-4:].sum() / rev.iloc[-4:].sum() * 100,
                   shares_1y=(shares.iloc[-1] / shares.iloc[-5] - 1) * 100, last_report=inc.pub.iloc[-1].date())
    rating = raw.get("rating") or {}
    counts = {k: number(rating.get(k)) for k in ("strong_buy", "buy", "hold", "under_perform", "sell")}
    total = np.nansum(list(counts.values()))
    if total > 0:
        row.update(analysts=total, buy_share=np.nansum([counts["strong_buy"], counts["buy"]]) / total * 100)
    target = number((raw.get("target") or {}).get("mean"))
    if not np.isnan(target):
        row.update(target_gap=(target / px.iloc[-1] - 1) * 100)
    flow = raw.get("flow") or []
    if flow:
        net_large = sum(number(f.get("large_in")) - number(f.get("large_out")) for f in flow)
        small = sum(number(f.get("small_in")) - number(f.get("small_out")) for f in flow)
        row.update(large_5d=net_large / 1e6, small_5d=small / 1e6)
    last = [c for c in (raw.get("calendar") or []) if c.get("eps_actual") is not None and number(c.get("eps_est"))]
    if last:
        c = max(last, key=lambda c: c.get("expected_publish_date") or "")
        row.update(eps_surprise=(number(c["eps_actual"]) / number(c["eps_est"]) - 1) * 100)
    today = date.today().isoformat()
    coming = sorted(c.get("expected_publish_date") for c in (raw.get("calendar") or []) if c.get("eps_actual") is None and (c.get("expected_publish_date") or "") >= today)
    if coming:
        row.update(next_report=coming[0])
    return row


def main():
    refresh = "--refresh" in sys.argv
    stocks = [s for names in STOCKS.values() for s in names]
    if os.path.exists(CACHE) and not refresh:
        raw, close = pd.read_pickle(CACHE)
    else:
        data = DataClient(make_client())
        raw = pull(data, stocks)
        close, missing = fetch(data, sorted(set(stocks + list(FUNDS))))
        pd.to_pickle((raw, close), CACHE)
    group = {s: g for g, names in STOCKS.items() for s in names}
    rows = {s: dict(group=group[s], **profile(s, raw[s], close)) for s in stocks}
    rows.update({s: dict(group=what, **profile(s, None, close)) for s, what in FUNDS.items() if s in close})
    t = pd.DataFrame(rows).T
    pd.set_option("display.width", 280, "display.max_rows", 100, "display.float_format", "{:.1f}".format)
    cols = ["group", "price", "ret_1y", "from_high", "above_band", "z50", "ps_rank", "pe", "pe_rank", "growth", "growth_before", "op_margin", "net_margin", "shares_1y",
            "analysts", "buy_share", "target_gap", "large_5d", "small_5d", "eps_surprise", "last_report"]
    print(t[[c for c in cols if c in t]].to_string())
    t.to_csv(os.path.join(HERE, "cache", "div_profile.csv"))


if __name__ == "__main__":
    main()
