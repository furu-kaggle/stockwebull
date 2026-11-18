"""Run the savings plan for today: work out the orders from fresh prices and, with --live, send them.

Without --live nothing is sent: the script prints what it would do (a dry run).
State (start date, plan length, yen-to-dollar assumption) lives in draft/plan_state.json.
Buys are market orders for a fractional quantity, which only fill in the regular session.

Usage: python draft/plan_live.py [--live] [--status]
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
EXTRA = ["AXON"]                      # outside the 22 security names; added 2026-11-19 as a place to move to
OUTSIDE = ["UI"]                      # other sectors; used only when nothing in the list above qualifies
PREFER = ["GEN", "FTNT", "AXON"]      # where to go first when the core is rich (results improving, multiple still low)
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


def latest_prices(data, symbols):
    """Latest regular-session trade price per symbol and the New York date it belongs to."""
    prices, days = {}, set()
    for i in range(0, len(symbols), 10):
        resp = data.market_data.get_batch_history_bar(symbols[i:i + 10], "US_STOCK", "M1", count="1").json()
        for item in resp["result"]:
            bars = item.get("result") or []
            if bars:
                prices[item["symbol"]] = float(bars[0]["close"])
                days.add(pd.Timestamp(bars[0]["time"]).tz_convert("America/New_York").date())
    return pd.Series(prices), days


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="send the orders (default: dry run)")
    parser.add_argument("--status", action="store_true", help="show today's orders, positions and cash, then stop")
    parser.add_argument("--anytime", action="store_true", help="allow --live outside the regular US session")
    args = parser.parse_args()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"start": None, "days": 60, "yen_per_dollar": 155.0, "done_days": []}
    client = make_client()
    data, trade = DataClient(client), TradeClient(client)
    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")] + EXTRA + OUTSIDE
    others = [s for s in symbols if s not in CORE + OUTSIDE]

    account = trade.account_v2.get_account_list().json()[0]["account_id"]
    now_et = pd.Timestamp.now(tz="America/New_York")
    today = now_et.normalize().tz_localize(None)                 # the US trading date
    in_session = now_et.weekday() < 5 and (9, 35) <= (now_et.hour, now_et.minute) < (15, 55)
    if args.status:
        show_status(trade, account)
        return
    if args.live and today.date().isoformat() in state["done_days"]:
        print(f"{today.date()}: orders were already sent today; nothing more is sent.")
        return
    if args.live and not in_session and not args.anytime:
        print(f"It is {now_et:%Y-%m-%d %H:%M} in New York: outside the regular session, so nothing is sent.")
        return

    bars = fresh_bars(data, symbols)
    for f in bars:                                             # add a row for today so that "known at the previous close" lines up
        if bars[f].index[-1] < today:
            bars[f].loc[today] = np.nan
    panels = build_panels(symbols, bars=bars)

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
    orders = decide(today, cash, shares, days_left, plain_daily, panels, CORE, others, dict(CFG, prefer=PREFER, outside=OUTSIDE))

    # Size orders with the price trading right now; if the market has not traded today, it is closed.
    now_px, traded_days = latest_prices(data, CORE + [s for s in orders if s not in CORE])
    if args.live and today.date() not in traded_days:
        print(f"No trades today ({today.date()}) in {', '.join(CORE)}: the market looks closed, so nothing is sent.")
        return
    last = now_px.reindex(symbols).fillna(panels["prev_close"].loc[today])
    print(f"{today.date()}  day {len(state['done_days']) + 1} of {state['days']}   cash ${cash:,.2f} (yen at {rate:.0f}/$)   plain daily ${plain_daily:.2f}"
          f"   prices as of {bars['close'].dropna(how='all').index[-1].date()}")
    view = pd.DataFrame({"P/S rank": panels["rank"].loc[today], "50d z": panels["z50"].loc[today], "above band": panels["above_band"].loc[today],
                         "5d move%": panels["jump"].loc[today] * 100, "quality ok": panels["quality"].loc[today]})
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(view.loc[CORE + [s for s in orders if s not in CORE]].to_string())
    total, sent, failed = 0.0, [], []
    for sym, amount in sorted(orders.items(), key=lambda kv: kv[1]):      # sells first
        side = "BUY" if amount > 0 else "SELL"
        qty = round(abs(amount) / last[sym], 5)
        if side == "SELL":
            qty = min(qty, round(float(shares[sym]), 5))
        total += amount
        print(f"  {side} {sym}  ${abs(amount):.2f}  ~{qty} shares at about ${last[sym]:.2f}")
        if args.live and qty > 0:
            order = {"client_order_id": uuid.uuid4().hex, "symbol": sym, "instrument_type": "EQUITY", "market": "US", "side": side,
                     "order_type": "MARKET", "entrust_type": "QTY", "quantity": f"{qty:.5f}", "time_in_force": "DAY",
                     "support_trading_session": "N", "account_tax_type": "SPECIFIC"}
            try:
                resp = trade.order_v3.place_order(account, [order])
                print("    sent:", resp.status_code, json.dumps(resp.json(), ensure_ascii=False)[:200])
                sent.append({"symbol": sym, "side": side, "qty": qty, "client_order_id": order["client_order_id"]})
            except Exception as err:                              # one refusal must not stop the other orders
                print("    REFUSED:", str(err).split("RequestID")[0][:240])
                failed.append(sym)
    print(f"  total ${total:.2f} (about {total * rate:,.0f} yen)" + ("" if args.live else "   [dry run: nothing sent]"))
    if args.live:
        print(f"  sent {len(sent)}, refused {len(failed)}" + (f" ({', '.join(failed)})" if failed else ""))
        if sent:                                                  # a day counts only if something actually went out
            state["start"] = state["start"] or today.date().isoformat()
            state["done_days"].append(today.date().isoformat())
            state.setdefault("orders", {})[today.date().isoformat()] = sent
            json.dump(state, open(STATE, "w"), indent=1)


def show_status(trade, account):
    balance = trade.account_v2.get_account_balance(account).json()
    for c in balance.get("account_currency_assets", []):
        print(f"  {c['currency']}: cash {c['cash_balance']}  market value {c['market_value']}  buying power {c['buying_power']}")
    positions = trade.account_v2.get_account_position(account).json() or []
    print(f"  positions: {len(positions)}")
    for pos in positions:
        print("   ", {k: pos.get(k) for k in ("symbol", "quantity", "cost_price", "last_price", "market_value", "unrealized_profit_loss") if k in pos} or pos)
    for label, fn in (("open orders", lambda: trade.order_v3.list_order_open(account)), ("order history", lambda: trade.order_v3.list_order_history(account))):
        try:
            body = fn().json()
            items = body.get("orders", body.get("data", body)) if isinstance(body, dict) else body
            print(f"  {label}: {len(items) if hasattr(items, '__len__') else '?'}")
            for item in (items or [])[:12]:
                order = (item.get("orders") or [item])[0] if isinstance(item, dict) else item
                print("   ", {k: order.get(k) for k in ("symbol", "side", "status", "order_type", "total_quantity", "filled_quantity", "filled_price", "place_time_at") if k in order} or str(order)[:200])
        except Exception as err:
            print(f"  {label}: could not be read ({str(err).split('RequestID')[0][:120]})")


if __name__ == "__main__":
    main()
