"""Tier the security universe by business quality: is it growing, and does it make money?

  Tier 1  growing (TTM revenue >= +8% yoy) with a solid operating margin (>= 15%)
  Tier 2  growing with a thin but positive operating margin
  Tier 3  growing but loss-making
  Tier 4  not growing (profitable or not)

Operating margin is GAAP, from Webull's income statements. Valuation does not decide the tier; a
second axis says how much is already priced in:

  ps_pctile   where today's P/S sits in the stock's own history since 2023 (100 = most expensive ever)
  vs_peers    today's P/S divided by the P/S its growth and margin would earn among these peers
  priced_in   "high" if both say expensive, "low" if both say cheap, else "mid"

Usage: python draft/tiers.py [--csv out.csv]
"""
import argparse

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from data import load_bars, load_income
from universe import UNIVERSE

GROWTH_BAR = 8.0   # % TTM revenue growth that counts as "growing"
MARGIN_BAR = 15.0  # % TTM operating margin that counts as "solid"


def fundamentals(symbols):
    income = load_income(symbols)
    rows = {}
    for sym in symbols:
        q = income[income.symbol == sym].sort_values("end_date")
        if len(q) < 8:
            continue
        ttm_rev = q.revenue.rolling(4).sum()
        ttm_op = q.op_income.rolling(4).sum()
        rows[sym] = {
            "rev_ttm_$M": ttm_rev.iloc[-1] / 1e6,
            "growth%": (ttm_rev.iloc[-1] / ttm_rev.iloc[-5] - 1) * 100,
            "growth_prev%": (ttm_rev.iloc[-5] / ttm_rev.iloc[-9] - 1) * 100 if len(q) >= 12 else float("nan"),
            "op_margin%": ttm_op.iloc[-1] / ttm_rev.iloc[-1] * 100,
            "op_margin_prev%": ttm_op.iloc[-5] / ttm_rev.iloc[-5] * 100,
            "last_quarter": q.end_date.iloc[-1].date(),
        }
    return pd.DataFrame(rows).T


def valuation(symbols):
    data, rows = DataClient(make_client()), {}
    for i in range(0, len(symbols), 10):
        for r in data.market_data.get_snapshot(",".join(symbols[i:i + 10]), "US_STOCK").json():
            rows[r["symbol"]] = {"P/S": float(r.get("ps_ratio") or "nan"), "P/E": float(r.get("pe_ratio") or "nan"),
                                 "cap_$B": float(r.get("market_value") or 0) / 1e9}
    return pd.DataFrame(rows).T


def ps_history_percentile(symbols, val):
    """Percentile of today's P/S within each stock's own daily P/S history (share count held at today's)."""
    close, income, out = load_bars(symbols)["close"], load_income(symbols), {}
    for sym in symbols:
        q = income[(income.symbol == sym) & income.publish_date.notna()].sort_values("end_date")
        ttm = q.revenue.rolling(4).sum()
        ttm.index = q.publish_date.values
        ttm = ttm.dropna()
        ttm = ttm[~ttm.index.duplicated(keep="last")].sort_index()   # some filings share a publish date
        px = close[sym].dropna()
        if ttm.empty or sym not in val.index:
            continue
        rev = ttm.reindex(px.index.union(ttm.index)).ffill().reindex(px.index)
        shares = val.loc[sym, "cap_$B"] * 1e9 / px.iloc[-1]
        ps = (px * shares / rev).dropna()
        if len(ps) > 250:
            out[sym] = {"ps_pctile": (ps <= ps.iloc[-1]).mean() * 100, "ps_low": ps.min(), "ps_high": ps.max(),
                        "from_high%": (px.iloc[-1] / px.tail(252).max() - 1) * 100}
    return pd.DataFrame(out).T


def peer_relative(table):
    """Actual P/S over the P/S fitted from growth and margin across the universe (log-linear)."""
    ok = table["P/S"] > 0
    X = np.column_stack([np.ones(ok.sum()), table.loc[ok, "growth%"].astype(float),
                         table.loc[ok, "op_margin%"].astype(float).clip(-40, 50)])
    beta, *_ = np.linalg.lstsq(X, np.log(table.loc[ok, "P/S"].astype(float)), rcond=None)
    return pd.Series(table.loc[ok, "P/S"].astype(float).values / np.exp(X @ beta), index=table.index[ok])


def priced_in(row):
    expensive = (row["ps_pctile"] >= 70) + (row["vs_peers"] >= 1.25)
    cheap = (row["ps_pctile"] <= 40) + (row["vs_peers"] <= 0.8)
    return "high" if expensive == 2 else "low" if cheap == 2 else "mid"


def tier(row):
    if row["growth%"] < GROWTH_BAR:
        return 4
    return 1 if row["op_margin%"] >= MARGIN_BAR else 2 if row["op_margin%"] > 0 else 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv")
    args = parser.parse_args()
    meta = {u[0]: u for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")}
    val = valuation(list(meta))
    table = fundamentals(list(meta)).join(val).join(ps_history_percentile(list(meta), val))
    numeric = [c for c in table.columns if c != "last_quarter"]
    table[numeric] = table[numeric].apply(pd.to_numeric, errors="coerce")
    table["vs_peers"] = peer_relative(table)
    table["priced_in"] = table.apply(priced_in, axis=1)
    table["tier"] = table.apply(tier, axis=1)
    table["rule40"] = table["growth%"] + table["op_margin%"]
    table["kind"] = [meta[s][2] for s in table.index]
    cols = ["tier", "priced_in", "growth%", "op_margin%", "P/S", "ps_low", "ps_high", "ps_pctile", "vs_peers", "from_high%",
            "P/E", "growth_prev%", "op_margin_prev%", "rule40", "cap_$B", "kind", "last_quarter"]
    table = table[cols].sort_values(["tier", "rule40"], ascending=[True, False])
    pd.set_option("display.width", 250, "display.float_format", "{:.1f}".format)
    print(table.to_string())
    if args.csv:
        table.to_csv(args.csv)


if __name__ == "__main__":
    main()
