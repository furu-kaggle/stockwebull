"""Backtest of the savings plan with a destination outside the security sector.

The plan rules are the live ones (`plan_strategy.decide`); what changes between runs is
  outside     the names that receive money when the sector has nowhere left to go
  cap_other   the largest share of a day that one name outside the core may take
Each variant runs the same plans (one starting every five trading days since 2024-01-02).

The destinations were picked after looking at how they did in past sell-offs, so the comparison between
them is hindsight. What the backtest does show honestly: how often money leaves the sector, how much,
and how large the effect on the plan can be.

Usage: python draft/diversify_backtest.py [--refresh] [--days 23]
"""
import argparse
import os

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from diversify import SEC
from plan_live import fresh_bars
from plan_strategy import CFG, build_panels, run_plan

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "div_ohlc.pkl")
CORE = ["QLYS", "TENB"]
BASKETS = {
    "UI (live now)": ["UI"],
    "T-bills": ["SGOV"],
    "defense": ["NOC", "LMT", "GD"],
    "Dollar General": ["DG"],
    "staples": ["KO", "PG", "PEP", "WMT"],
    "health": ["LLY", "AMGN", "MRK"],
    "energy": ["XOM", "CVX"],
    "insurers+Cboe": ["CB", "TRV", "CBOE"],
    "low-vol fund": ["USMV"],
    "S&P 500": ["SPY"],
    "Nasdaq 100": ["QQQ"],
    "mix A": ["NOC", "LMT", "DG", "SGOV"],
    "mix B": ["NOC", "DG", "CBOE", "AMGN", "SGOV"],
}
NO_BLOCK = ["SGOV", "BIL"]          # always above their band; the technical check makes no sense for them


def load(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return pd.read_pickle(CACHE)
    symbols = sorted(set(SEC + [s for names in BASKETS.values() for s in names]))
    bars = fresh_bars(DataClient(make_client()), symbols, count=1200)
    pd.to_pickle(bars, CACHE)
    return bars


def panels_with(bars, extra):
    """Panels for the security names, plus price-only columns for the names in `extra`."""
    panels = build_panels(SEC, bars={f: bars[f][SEC] for f in bars})
    close, open_ = bars["close"][extra], bars["open"][extra]
    logp = np.log(close)
    add = dict(close=close, open=open_, rank=pd.DataFrame(np.nan, index=close.index, columns=extra),
               z50=((logp - logp.rolling(50).mean()) / logp.rolling(50).std()).shift(1),
               above_band=(close > close.rolling(20).mean() + close.rolling(20).std()).shift(1),
               jump=(close / close.shift(5) - 1).shift(1),
               earnings=pd.DataFrame(False, index=close.index, columns=extra),
               quality=pd.DataFrame(True, index=close.index, columns=extra), prev_close=close.shift(1))
    return {k: panels[k].join(add[k]) for k in panels}


def run_variant(panels, starts, days, cfg):
    others = [s for s in SEC if s not in CORE]
    rows = []
    for i in starts:
        r = run_plan(panels, CORE, others, i, days, cfg=cfg)
        spent = r["spent"]
        out = spent[cfg.get("outside", [])].sum() if cfg.get("outside") else 0.0
        rows.append(dict(start=panels["close"].index[i], end=r["end"], later=r["later"], dip=r["dip"], low=r["low"],
                         core=spent[CORE].sum() / spent.sum(), outside=out / spent.sum(), cash_end=r["cash_end"]))
    return pd.DataFrame(rows).set_index("start")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--days", type=int, default=23)
    args = parser.parse_args()
    bars = load(args.refresh)
    extra = sorted(set(s for names in BASKETS.values() for s in names))
    panels = panels_with(bars, extra)
    idx = panels["close"].index
    starts = list(range(idx.searchsorted(pd.Timestamp("2024-01-02")), len(idx) - args.days, 5))
    print(f"{len(starts)} plans of {args.days} trading days, starting {idx[starts[0]].date()} to {idx[starts[-1]].date()}; prices to {idx[-1].date()}\n")

    variants = {"no outside, no cap": dict(CFG), "no outside, cap 1/3": dict(CFG, cap_other=1 / 3)}
    for name, names in BASKETS.items():
        variants[f"{name}, no cap"] = dict(CFG, outside=names, unblocked=NO_BLOCK)
        variants[f"{name}, cap 1/3"] = dict(CFG, outside=names, unblocked=NO_BLOCK, cap_other=1 / 3)
    res = {name: run_variant(panels, starts, args.days, cfg) for name, cfg in variants.items()}
    base = res["no outside, no cap"]

    # Plans in which the cap or the outside names changed anything at all are the ones worth comparing.
    touched = (res["mix A, cap 1/3"].outside > 0.02)
    rows = []
    for name, t in res.items():
        d_end, d_later = (t.end - base.end) * 100, (t.later - base.later) * 100
        rows.append(dict(variant=name, end_med=(t.end.median() - 1) * 100, end_worst=(t.end.min() - 1) * 100, later_med=(t.later.median() - 1) * 100,
                         later_worst=(t.later.min() - 1) * 100, dip_med=t.dip.median() * 100, dip_worst=t.dip.min() * 100,
                         outside_avg=t.outside.mean() * 100, plans_out=(t.outside > 0.02).mean() * 100,
                         d_end_touched=d_end[touched].mean(), d_later_touched=d_later[touched].mean(), later_better=(d_later[touched].dropna() > 0).mean() * 100))
    table = pd.DataFrame(rows).set_index("variant")
    pd.set_option("display.width", 250, "display.float_format", "{:.1f}".format)
    print(f"plans touched by 'mix A, cap 1/3': {touched.sum()} of {len(touched)}")
    print(table.to_string())
    table.to_csv(os.path.join(HERE, "cache", f"div_backtest_{args.days}.csv"))
    pd.to_pickle(res, os.path.join(HERE, "cache", f"div_backtest_{args.days}.pkl"))


if __name__ == "__main__":
    main()
