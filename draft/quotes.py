"""Print a snapshot and recent bars for US stocks / ETFs.

Usage: python draft/quotes.py [SYMBOL ...] [--timespan M5] [--count 5] [--sessions PRE RTH ATH]
Sessions: PRE (pre-market), RTH (regular), ATH (after-hours). OVN (overnight) needs a separate subscription.
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from webull.data.data_client import DataClient

from _client import make_client

JST = ZoneInfo("Asia/Tokyo")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", default=["AAPL"])
    parser.add_argument("--category", default="US_STOCK")
    parser.add_argument("--timespan", default="M5", help="M1, M5, M15, M30, M60, D, W, M ...")
    parser.add_argument("--count", default="5")
    parser.add_argument("--sessions", nargs="*", default=["PRE", "RTH", "ATH"])
    args = parser.parse_args()

    data = DataClient(make_client())
    for symbol in args.symbols:
        snap = data.market_data.get_snapshot(symbol, args.category).json()[0]
        print(f"{symbol}  status={snap.get('trade_status')}  last close {snap.get('price')}"
              f"  change {snap.get('change')} ({float(snap.get('change_ratio', 0)) * 100:.2f}%)"
              f"  bid {snap.get('bid')} / ask {snap.get('ask')}")

        bars = data.market_data.get_history_bar(symbol, args.category, args.timespan, count=args.count,
                                                trading_sessions=args.sessions).json()
        for bar in bars["result"][0]["result"]:
            when = datetime.fromisoformat(bar["time"]).astimezone(JST).strftime("%m/%d %H:%M JST")
            print(f"  {when}  {bar.get('trading_session') or '-':4}  O {bar['open']}  H {bar['high']}"
                  f"  L {bar['low']}  C {bar['close']}  V {bar['volume']}")


if __name__ == "__main__":
    main()
