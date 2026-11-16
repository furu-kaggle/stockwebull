"""Tier the security universe by business quality: is it growing, and does it make money?

  Tier 1  growing (TTM revenue >= +8% yoy) with a solid operating margin (>= 15%)
  Tier 2  growing with a thin but positive operating margin
  Tier 3  growing but loss-making
  Tier 4  not growing (profitable or not)

Operating margin is GAAP, from Webull's income statements. Valuation (P/S, P/E) is shown beside the
tier but does not decide it.

Usage: python draft/tiers.py [--csv out.csv]
"""
import argparse

import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from data import load_income
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


def tier(row):
    if row["growth%"] < GROWTH_BAR:
        return 4
    return 1 if row["op_margin%"] >= MARGIN_BAR else 2 if row["op_margin%"] > 0 else 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv")
    args = parser.parse_args()
    meta = {u[0]: u for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")}
    table = fundamentals(list(meta)).join(valuation(list(meta)))
    table["tier"] = table.apply(tier, axis=1)
    table["rule40"] = table["growth%"] + table["op_margin%"]
    table["kind"] = [meta[s][2] for s in table.index]
    cols = ["tier", "growth%", "growth_prev%", "op_margin%", "op_margin_prev%", "rule40", "P/S", "P/E", "cap_$B", "kind", "last_quarter"]
    table = table[cols].sort_values(["tier", "rule40"], ascending=[True, False])
    pd.set_option("display.width", 250, "display.float_format", "{:.1f}".format)
    print(table.to_string())
    if args.csv:
        table.to_csv(args.csv)


if __name__ == "__main__":
    main()
