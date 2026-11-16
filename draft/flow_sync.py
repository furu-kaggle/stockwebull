"""Store the daily large / medium / small order flow for the security universe in D1 (table capital_flow).

Webull only returns the last five trading days, so history exists only for the days this script has
captured: run it at least once every five trading days to keep the record unbroken.
Values are dollars bought (in) and sold (out) by order size, as Webull classifies them.

Usage: python draft/flow_sync.py [SYMBOL ...]
"""
import sys

import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from d1_sync import lit, run
from data import load_bars
from universe import UNIVERSE


def main():
    symbols = sys.argv[1:] or [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")] + ["CIBR"]
    data, rows = DataClient(make_client()), []
    for sym in symbols:
        try:
            flow = data.fundamentals.get_capital_flow(sym, count=5).json() or []
        except Exception as err:
            print(f"{sym}: {str(err)[:80]}")
            continue
        for f in flow:
            day = f"{f['date'][:4]}-{f['date'][4:6]}-{f['date'][6:]}"
            rows.append([sym, day] + [float(f[k]) for k in ("large_in", "large_out", "medium_in", "medium_out", "small_in", "small_out")])
    table = pd.DataFrame(rows, columns=["symbol", "date", "large_in", "large_out", "medium_in", "medium_out", "small_in", "small_out"])
    values = ",".join("(" + ",".join([lit(r.symbol), lit(r.date)] + [f"{v:.2f}" for v in r[3:]]) + ")" for r in table.itertuples())
    run("INSERT INTO capital_flow (symbol, date, large_in, large_out, medium_in, medium_out, small_in, small_out) "
        f"VALUES {values} ON CONFLICT(symbol, date) DO UPDATE SET large_in=excluded.large_in, large_out=excluded.large_out, "
        "medium_in=excluded.medium_in, medium_out=excluded.medium_out, small_in=excluded.small_in, small_out=excluded.small_out, "
        "fetched_at=datetime('now')")
    stored = run("SELECT COUNT(*) AS rows_, COUNT(DISTINCT symbol) AS symbols, MIN(date) AS first_day, MAX(date) AS last_day FROM capital_flow")["results"][0]
    print("in D1:", stored)

    table["large_net"] = table.large_in - table.large_out
    table["all_net"] = table.large_net + table.medium_in - table.medium_out + table.small_in - table.small_out
    summary = table.groupby("symbol").agg(large_in=("large_in", "sum"), large_out=("large_out", "sum"), large_net=("large_net", "sum"), all_net=("all_net", "sum"))
    summary["large_net_%"] = summary.large_net / (summary.large_in + summary.large_out) * 100
    pd.set_option("display.width", 200, "display.float_format", "{:,.1f}".format)
    print(f"\nLast five trading days ({table.date.min()} to {table.date.max()}), $ millions:")
    print((summary[["large_in", "large_out", "large_net", "all_net"]] / 1e6).join(summary["large_net_%"]).sort_values("large_net_%", ascending=False).to_string())


if __name__ == "__main__":
    main()
