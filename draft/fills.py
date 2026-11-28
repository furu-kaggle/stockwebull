"""Every filled order in the account, saved to draft/fills.csv (the order history is paged by day ranges)."""
import os
import time

import pandas as pd
from webull.trade.trade_client import TradeClient

from _client import make_client

HERE = os.path.dirname(os.path.abspath(__file__))


def load_fills(start="2026-11-16", refresh=True):
    path = os.path.join(HERE, "fills.csv")
    if not refresh and os.path.exists(path):
        return pd.read_csv(path, parse_dates=["time"])
    trade = TradeClient(make_client())
    account = trade.account_v2.get_account_list().json()[0]["account_id"]
    rows, seen = [], set()
    for day in pd.date_range(start, pd.Timestamp.now(tz="UTC").date()):
        fmt = "%Y-%m-%dT00:00:00.000Z"                          # the only time format the endpoint accepts
        for attempt in range(4):
            try:
                body = trade.order_v3.list_order_history(account, start_time=day.strftime(fmt), end_time=(day + pd.Timedelta(days=1)).strftime(fmt)).json()
                break
            except Exception:                                   # rate limit: wait and ask again
                time.sleep(10 * (attempt + 1))
                body = {}
        for item in (body.get("data", []) if isinstance(body, dict) else body) or []:
            for o in item.get("orders") or [item]:
                if o.get("status") == "FILLED" and o["order_id"] not in seen:
                    seen.add(o["order_id"])
                    rows.append(dict(time=pd.Timestamp(o["filled_time_at"]).tz_convert("America/New_York").tz_localize(None), symbol=o["symbol"], side=o["side"],
                                     qty=float(o["filled_quantity"]), price=float(o["filled_price"]), order_id=o["order_id"]))
        time.sleep(3)
    fills = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    fills["dollars"] = fills.qty * fills.price
    fills.to_csv(path, index=False)
    return fills


if __name__ == "__main__":
    f = load_fills()
    print(len(f), "fills")
    print(f.assign(day=f.time.dt.date).groupby("day").agg(n=("symbol", "count"), dollars=("dollars", "sum")).round(2).to_string())
