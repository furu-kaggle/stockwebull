"""Forward test (paper trading): track model portfolios against live prices.

Each run polls the latest price (pre-market, regular and after-hours) for every holding, marks the
paper portfolios to market and appends one line per portfolio to draft/paper/equity.csv.
Portfolios are bought on the first run at that poll's prices, paying COST per side. No real orders.

Usage: python draft/paper.py              one poll
       python draft/paper.py --loop 600   poll every 10 minutes until stopped
       python draft/paper.py --reset      discard the paper portfolios and start again
"""
import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone

from webull.data.data_client import DataClient

from _client import make_client
from universe import PENTEST_AI_RANK, UNIVERSE

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper")
STATE, LOG = os.path.join(DIR, "state.json"), os.path.join(DIR, "equity.csv")
CAPITAL = 10_000.0   # USD per paper portfolio
COST = 0.003         # per side

SECURITY = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]


def equal(symbols):
    return {s: 1 / len(symbols) for s in symbols}


PORTFOLIOS = {
    "security_ew22": equal(SECURITY),                                   # the base case
    "pentest_ai_top3": equal([r[0] for r in PENTEST_AI_RANK[:3]]),      # CRWD, PANW, RPD
    "CIBR": {"CIBR": 1.0},
    "QQQ": {"QQQ": 1.0},
}


def latest_prices(data, symbols):
    prices = {}
    for i in range(0, len(symbols), 10):
        resp = data.market_data.get_batch_history_bar(symbols[i:i + 10], "US_STOCK", "M1", count="1",
                                                      trading_sessions=["PRE", "RTH", "ATH"]).json()
        for item in resp["result"]:
            bars = item.get("result") or []
            if bars:
                prices[item["symbol"]] = (float(bars[0]["close"]), bars[0]["time"], bars[0].get("trading_session") or "")
    return prices


def poll(data):
    os.makedirs(DIR, exist_ok=True)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    symbols = sorted({s for w in PORTFOLIOS.values() for s in w})
    prices = latest_prices(data, symbols)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_log = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        out = csv.writer(f)
        if new_log:
            out.writerow(["time_utc", "portfolio", "equity", "return_pct", "session", "priced", "holdings"])
        for name, weights in PORTFOLIOS.items():
            missing = [s for s in weights if s not in prices]
            if name not in state:
                if missing:
                    print(f"{name}: waiting for prices ({', '.join(missing)})")
                    continue
                invest = CAPITAL / (1 + COST)                   # entry cost comes out of the capital
                state[name] = {"opened": now, "cash": 0.0,
                               "shares": {s: invest * w / prices[s][0] for s, w in weights.items()},
                               "entry": {s: prices[s][0] for s in weights}}
            pf = state[name]
            last = pf.setdefault("last", {})
            last.update({s: prices[s][0] for s in pf["shares"] if s in prices})   # keep the previous price if one is missing
            equity = pf["cash"] + sum(q * last[s] for s, q in pf["shares"].items())
            session = max((prices[s][2] for s in pf["shares"] if s in prices), default="")
            out.writerow([now, name, f"{equity:.2f}", f"{(equity / CAPITAL - 1) * 100:.3f}", session,
                          len(pf["shares"]) - len(missing), len(pf["shares"])])
            print(f"{now}  {name:16} {equity:10.2f}  {(equity / CAPITAL - 1) * 100:+.2f}%  [{session or '-'}]"
                  + (f"  stale: {', '.join(missing)}" if missing else ""))
    json.dump(state, open(STATE, "w"), indent=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, help="seconds between polls")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        for path in (STATE, LOG):
            if os.path.exists(path):
                os.remove(path)
    data = DataClient(make_client())
    while True:
        try:
            poll(data)
        except Exception as err:                                # keep the loop alive through a bad poll
            print(f"poll failed: {str(err)[:200]}")
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
