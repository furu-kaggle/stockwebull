"""The next trading day's orders under the owner's shape: half in security, five other slots of 10% each. Sends nothing.

How the shape would run (research/diversification.md, "追加6" and "追加7"):
  the cash left in the plan is divided once into six pots: security 50%, and 10% for each slot
  every day each pot spends its own cash / days left
  security pot   the live rules decide where it goes (core, then the names to move to); one name outside the
                 core takes at most a third of the whole day; what cannot be bought stays in the security pot
  slot pots      one company or fund each, bought every day; a slot waits only after a 15% jump in five days

The live runner (plan_live.py) now does the same thing; this stays as the stand-alone preview.

Usage: python draft/lineup_preview.py
"""
import json

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient
from webull.trade.trade_client import TradeClient

from _client import make_client
from plan_live import CORE, DAILY_CAP_YEN, EXTRA, PREFER, SECURITY_SHARE, SLOTS, STATE, fresh_bars
from plan_strategy import CFG, build_panels, decide
from universe import UNIVERSE

DROP = ["AXON"]                      # no longer a place to move to (already out of plan_live.EXTRA)


def main():
    client = make_client()
    data, trade = DataClient(client), TradeClient(client)
    state = json.load(open(STATE))
    sector = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    inside = sector + [s for s in EXTRA if s not in DROP]
    slots = list(SLOTS)
    bars = fresh_bars(data, inside + slots)
    day = bars["close"].index[-1] + pd.offsets.BDay(1)             # the next trading day, decided on the latest close
    for f in bars:
        bars[f].loc[day] = np.nan
    panels = build_panels(inside, bars={f: bars[f][inside] for f in bars})
    close = bars["close"][slots]
    blocked = (close / close.shift(5) - 1 >= CFG["jump"]).shift(1).loc[day]      # a slot waits only after a 15% jump in five days (see plan_live.py)

    account = trade.account_v2.get_account_list().json()[0]["account_id"]
    cur = {c["currency"]: c for c in trade.account_v2.get_account_balance(account).json().get("account_currency_assets", [])}
    rate = state["yen_per_dollar"]
    cash = float(cur.get("USD", {}).get("cash_balance", 0)) + float(cur.get("JPY", {}).get("cash_balance", 0)) / rate
    shares = pd.Series(0.0, index=inside)
    for pos in trade.account_v2.get_account_position(account).json() or []:
        if pos.get("symbol") in shares.index:
            shares[pos["symbol"]] = float(pos.get("quantity", pos.get("qty", 0)) or 0)
    days_left = state["days"] - len(state["done_days"])
    plain_daily = min((cash + (shares * panels["prev_close"].loc[day]).sum()) / state["days"], DAILY_CAP_YEN / 2 / rate)

    pots = {"security": cash * SECURITY_SHARE, **{s: cash * (1 - SECURITY_SHARE) / len(slots) for s in slots}}
    print(f"orders for {day.date()} decided on the close of {bars['close'].dropna(how='all').index[-1].date()}; cash ${cash:.2f}, {days_left} days left")
    print("pots: " + ", ".join(f"{k} ${v:.2f}" for k, v in pots.items()) + "\n")

    others = [s for s in inside if s not in CORE]
    cfg = dict(CFG, prefer=[s for s in PREFER if s not in DROP], cap_other=(1 / 3) / SECURITY_SHARE)      # a third of the whole day
    info = {}
    orders = decide(day, pots["security"], shares, days_left, plain_daily * SECURITY_SHARE, panels, CORE, others, cfg, info)
    for s in slots:
        if not blocked[s]:
            orders[s] = pots[s] / days_left
    budget = cash / days_left
    total = sum(orders.values())
    view = pd.DataFrame({"P/S rank": panels["rank"].loc[day], "above band": panels["above_band"].loc[day], "5d move%": panels["jump"].loc[day] * 100}).loc[CORE + cfg["prefer"] + ["FFIV"]]
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(view.to_string())
    print("slots waiting today:", [s for s in slots if blocked[s]] or "none", "\n")
    for s, v in sorted(orders.items(), key=lambda kv: -kv[1]):
        print(f"  BUY {s:5} ${v:6.2f}  ({v / budget * 100:4.1f}% of the day)   {SLOTS.get(s, 'security')}")
    sec = sum(v for s, v in orders.items() if s not in SLOTS)
    print(f"  total ${total:.2f} of ${budget:.2f}; security ${sec:.2f}, slots ${total - sec:.2f}; {len(orders)} orders")
    print(f"  waiting in the security pot ${budget * SECURITY_SHARE - sec:.2f}, in slot pots ${sum(pots[s] / days_left for s in slots if blocked[s]):.2f}")


if __name__ == "__main__":
    main()
