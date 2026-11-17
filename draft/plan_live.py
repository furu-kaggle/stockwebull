"""Run the savings plan for today: work out the orders from fresh prices and, with --live, send them.

Without --live nothing is sent: the script prints what it would do (a dry run).
State (start date, plan length, yen-to-dollar assumption) lives in draft/plan_state.json.
Buys are market orders for a fractional quantity, which only fill in the regular session.

Usage: python draft/plan_live.py [--live]
"""
import argparse
import json
import os
import uuid
from datetime import date

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient
from webull.trade.trade_client import TradeClient

from _client import make_client
from plan_strategy import CFG, build_panels, decide
from universe import UNIVERSE

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "plan_state.json")
CORE = ["QLYS", "TENB"]
DAILY_CAP_YEN = 3300


def fresh_bars(data, symbols, count=600):
    rows = []
    for i in range(0, len(symbols), 5):
        resp = data.market_data.get_batch_history_bar(symbols[i:i + 5], "US_STOCK", "D", count=str(count)).json()
        for item in resp["result"]:
            for b in item.get("result") or []:
                day = pd.Timestamp(b["time"]).tz_convert("America/New_York").normalize().tz_localize(None)
                rows.append((day, item["symbol"], float(b["open"]), float(b["close"])))
    long = pd.DataFrame(rows, columns=["date", "symbol", "open", "close"])
    return {f: long.pivot(index="date", columns="symbol", values=f)[symbols].sort_index() for f in ("open", "close")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="send the orders (default: dry run)")
    args = parser.parse_args()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"start": None, "days": 60, "yen_per_dollar": 155.0, "done_days": []}
    client = make_client()
    data, trade = DataClient(client), TradeClient(client)
    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    others = [s for s in symbols if s not in CORE]

    bars = fresh_bars(data, symbols)
    today = pd.Timestamp(date.today())
    for f in bars:                                             # add a row for today so that "known at the previous close" lines up
        if bars[f].index[-1] < today:
            bars[f].loc[today] = np.nan
    panels = build_panels(symbols, bars=bars)

    account = trade.account_v2.get_account_list().json()[0]["account_id"]
    balance = trade.account_v2.get_account_balance(account).json()
    cur = {c["currency"]: c for c in balance.get("account_currency_assets", [])}
    rate = state["yen_per_dollar"]
    cash = float(cur.get("USD", {}).get("cash_balance", 0)) + float(cur.get("JPY", {}).get("cash_balance", 0)) / rate
    positions = trade.account_v2.get_account_position(account).json() or []
    shares = pd.Series(0.0, index=symbols)
    for pos in positions:
        if pos.get("symbol") in shares.index:
            shares[pos["symbol"]] = float(pos.get("quantity", pos.get("qty", 0)) or 0)

    days_left = state["days"] - len(state["done_days"])
    plain_daily = (cash + (shares * panels["prev_close"].loc[today]).sum()) / state["days"]
    plain_daily = min(plain_daily, DAILY_CAP_YEN / 2 / rate)
    orders = decide(today, cash, shares, days_left, plain_daily, panels, CORE, others, CFG)

    last = panels["prev_close"].loc[today]
    print(f"{today.date()}  day {len(state['done_days']) + 1} of {state['days']}   cash ${cash:,.2f} (yen at {rate:.0f}/$)   plain daily ${plain_daily:.2f}"
          f"   prices as of {bars['close'].dropna(how='all').index[-1].date()}")
    view = pd.DataFrame({"P/S rank": panels["rank"].loc[today], "50d z": panels["z50"].loc[today], "above band": panels["above_band"].loc[today],
                         "5d move%": panels["jump"].loc[today] * 100, "quality ok": panels["quality"].loc[today]})
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(view.loc[CORE + [s for s in orders if s not in CORE]].to_string())
    total = 0.0
    for sym, amount in orders.items():
        qty = round(abs(amount) / last[sym], 5)
        side = "BUY" if amount > 0 else "SELL"
        total += amount
        print(f"  {side} {sym}  ${abs(amount):.2f}  ~{qty} shares at about ${last[sym]:.2f}")
        if args.live:
            order = {"client_order_id": uuid.uuid4().hex, "symbol": sym, "instrument_type": "EQUITY", "market": "US", "side": side,
                     "order_type": "MARKET", "entrust_type": "QTY", "quantity": str(qty), "time_in_force": "DAY",
                     "support_trading_session": "N", "account_tax_type": "SPECIFIC"}
            resp = trade.order_v3.place_order(account, [order])
            print("    sent:", resp.status_code, json.dumps(resp.json(), ensure_ascii=False)[:200])
    print(f"  total ${total:.2f} (about {total * rate:,.0f} yen)" + ("" if args.live else "   [dry run: nothing sent]"))
    if args.live:
        state["start"] = state["start"] or today.date().isoformat()
        state["done_days"].append(today.date().isoformat())
        json.dump(state, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    main()
