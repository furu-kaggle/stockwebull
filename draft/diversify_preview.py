"""What the next trading day's orders would be under the live rules and under the proposed ones. Sends nothing.

The proposals (research/diversification.md, stage 5):
  cap        one name outside the core takes at most a third of the day; the part above it goes outside the sector
  share      while the core is rich (average two-year P/S rank 80+) half of every day goes outside the sector,
             70% at 95+
  basket     outside the sector = SHV (0-1 year Treasuries) for half, and NOC, GD, PEP, MCD for the other half;
             a stock that fails the band / jump check on the day passes its part to SHV

Usage: python draft/diversify_preview.py
"""
import json
import os

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient
from webull.trade.trade_client import TradeClient

from _client import make_client
from plan_live import CORE, DAILY_CAP_YEN, EXTRA, OUTSIDE, PREFER, STATE, fresh_bars
from plan_strategy import CFG, build_panels, decide
from universe import UNIVERSE

BASKET = {"SHV": 4.0, "NOC": 1.0, "GD": 1.0, "PEP": 1.0, "MCD": 1.0}
# second version (after the owner's "that is almost cash"): no SHV; a stock that fails the check has its part kept back in cash
STOCKS = ["NOC", "GD", "PEP", "MCD"]
SWAPS = ["HII", "LHX"]                 # candidates to take GD's place (GD is in the top tenth of its own ten-year earnings multiple)
SHARE = {80: 0.5, 95: 0.7}


def main():
    client = make_client()
    data, trade = DataClient(client), TradeClient(client)
    state = json.load(open(STATE))
    sector = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    with_figures, price_only = sector + EXTRA + OUTSIDE, list(BASKET) + SWAPS
    bars = fresh_bars(data, with_figures + price_only)
    day = bars["close"].index[-1] + pd.offsets.BDay(1)             # the next trading day: decided on the latest close
    for f in bars:
        bars[f].loc[day] = np.nan
    panels = build_panels(with_figures, bars={f: bars[f][with_figures] for f in bars})
    close = bars["close"][price_only]
    logp = np.log(close)
    add = dict(close=close, open=bars["open"][price_only], rank=pd.DataFrame(np.nan, index=close.index, columns=price_only),
               z50=((logp - logp.rolling(50).mean()) / logp.rolling(50).std()).shift(1),
               above_band=(close > close.rolling(20).mean() + close.rolling(20).std()).shift(1), jump=(close / close.shift(5) - 1).shift(1),
               earnings=pd.DataFrame(False, index=close.index, columns=price_only), quality=pd.DataFrame(True, index=close.index, columns=price_only),
               prev_close=close.shift(1))
    panels = {k: panels[k].join(add[k]) for k in panels}

    account = trade.account_v2.get_account_list().json()[0]["account_id"]
    cur = {c["currency"]: c for c in trade.account_v2.get_account_balance(account).json().get("account_currency_assets", [])}
    rate = state["yen_per_dollar"]
    cash = float(cur.get("USD", {}).get("cash_balance", 0)) + float(cur.get("JPY", {}).get("cash_balance", 0)) / rate
    shares = pd.Series(0.0, index=with_figures + price_only)
    for pos in trade.account_v2.get_account_position(account).json() or []:
        if pos.get("symbol") in shares.index:
            shares[pos["symbol"]] = float(pos.get("quantity", pos.get("qty", 0)) or 0)
    days_left = state["days"] - len(state["done_days"])
    plain_daily = min((cash + (shares * panels["prev_close"].loc[day]).sum()) / state["days"], DAILY_CAP_YEN / 2 / rate)

    others = [s for s in with_figures if s not in CORE + OUTSIDE]
    live = dict(CFG, prefer=PREFER, outside=OUTSIDE)
    basket = dict(outside=list(BASKET), outside_mix=BASKET, park="SHV", unblocked=["SHV"])
    variants = {
        "live rules today": (others, live),
        "live + cap 1/3 (rest to UI)": (others, dict(live, cap_other=1 / 3)),
        "proposal: half outside while rich, basket, cap 1/3": (others, dict(CFG, prefer=PREFER, cap_other=1 / 3, outside_share=SHARE, **basket)),
        "same, without AXON as a place to move to": ([s for s in others if s != "AXON"], dict(CFG, prefer=[s for s in PREFER if s != "AXON"], cap_other=1 / 3, outside_share=SHARE, **basket)),
    }
    no_axon, prefer = [s for s in others if s != "AXON"], [s for s in PREFER if s != "AXON"]
    for label, names in [("second version: NOC, GD, PEP, MCD, a blocked part kept back", STOCKS)] + [(f"second version with {x} in place of GD", [x if s == "GD" else s for s in STOCKS]) for x in SWAPS]:
        variants[label] = (no_axon, dict(CFG, prefer=prefer, cap_other=1 / 3, outside_share=SHARE, outside=names, set_aside=True))
    view = pd.DataFrame({"P/S rank": panels["rank"].loc[day], "above band": panels["above_band"].loc[day], "5d move%": panels["jump"].loc[day] * 100,
                         "quality ok": panels["quality"].loc[day]})
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(f"orders for {day.date()} decided on the close of {bars['close'].dropna(how='all').index[-1].date()}; cash ${cash:.2f}, {days_left} days left, plain daily ${plain_daily:.2f}")
    print(f"core average rank {panels['rank'].loc[day, CORE].mean():.1f}\n")
    print(view.loc[CORE + PREFER + ["FFIV", "UI"] + price_only].to_string(), "\n")
    for name, (pool, cfg) in variants.items():
        info = {}
        orders = decide(day, cash, shares, days_left, plain_daily, panels, CORE, pool, cfg, info)
        total = sum(orders.values())
        line = "  ".join(f"{s} ${v:.2f} ({v / total * 100:.0f}%)" for s, v in sorted(orders.items(), key=lambda kv: -kv[1]))
        inside = sum(v for s, v in orders.items() if s in sector + EXTRA)
        print(f"{name}\n   {line}\n   total ${total:.2f}; in the sector {inside / total * 100:.0f}%, outside {100 - inside / total * 100:.0f}%; {len(orders)} orders"
              + (f"; kept back in cash ${info['aside']:.2f}" if info.get("aside") else "") + "\n")


if __name__ == "__main__":
    main()
