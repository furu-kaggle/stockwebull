"""How much should go outside the sector when the core is rich?

A simple experiment on the long history (Qualys since 2013, Tenable since 2021): start a 23-day savings plan
on a day when the core is rich (two-year P/S rank 80+), put a fixed share of every day's money into a basket
outside the sector and the rest into the core, then hold until 250 trading days after the start. One plan
starts every five trading days. Reported per basket and share: the value against the money put in at the end,
and the lowest point on the way (dividends included, no costs).

This leaves out the plan's other rules (moving to cheaper security names, the band check), so it measures one
thing only: what the outside share does. The baskets were chosen for how they did in 2022-2026; the spells
before 2022 are the part of this test they were not chosen on.

Usage: python draft/diversify_share.py
"""
import os

import numpy as np
import pandas as pd

from diversify_rich import CORE, load
from long_history import prices

HERE = os.path.dirname(os.path.abspath(__file__))
BASKETS = {"defense": ["NOC", "LMT", "GD"], "health": ["LLY", "AMGN", "MRK", "JNJ"], "staples": ["KO", "PG", "PEP", "WMT"], "insurers": ["CB", "TRV", "PGR"],
           "DG": ["DG"], "T-bills": ["BIL"], "low-vol": ["USMV"], "S&P 500": ["SPY"], "QQQ": ["QQQ"], "gold": ["GLD"],
           "mix (defense, health, insurers, DG, T-bills)": ["NOC", "LMT", "AMGN", "MRK", "CB", "TRV", "DG", "BIL"],
           # sector funds: the same idea without picking the stocks that turned out to be winners
           "fund: defense": ["ITA"], "fund: health": ["XLV"], "fund: staples": ["XLP"], "fund: insurers": ["KIE"], "fund: utilities": ["XLU"],
           "fund mix (defense, health, staples, insurers, T-bills)": ["ITA", "XLV", "XLP", "KIE", "BIL"],
           # what can be bought at Webull Japan today (stage 4): defensive names that are not stretched, tradable funds, and SHV for T-bills
           "plan A: NOC, GD, PEP, MCD, PGR": ["NOC", "GD", "PEP", "MCD", "PGR"], "plan B: funds ITA, XLV, XLP, XLU": ["ITA", "XLV", "XLP", "XLU"], "plan C: SHV": ["SHV"],
           "plan D: A and SHV half each": ["NOC", "GD", "PEP", "MCD", "PGR", "SHV", "SHV", "SHV", "SHV", "SHV"]}
SHARES = [0.0, 0.3, 0.5, 0.7, 1.0]
BUY_DAYS, HOLD = 23, 250


def paths(prices, starts):
    """Value / money put in, day by day, for plans in one asset that start at each position (plans x days)."""
    win = np.array([prices[i:i + HOLD + 1] for i in starts])
    units = np.cumsum(1 / BUY_DAYS / win[:, :BUY_DAYS], axis=1)
    units = np.concatenate([units, np.repeat(units[:, -1:], HOLD + 1 - BUY_DAYS, axis=1)], axis=1)
    paid = np.minimum(np.arange(HOLD + 1) + 1, BUY_DAYS) / BUY_DAYS
    return units * win / paid


def basket_paths(adj, names, starts):
    """Equal dollars in each name that already trades on the start day."""
    each = np.array([paths(adj[s].values, starts) for s in names])
    return np.nanmean(each, axis=0)


def main():
    adj, ranks = load()
    more = sorted(set(s for names in BASKETS.values() for s in names) - set(adj.columns))
    adj = adj.join(prices(more)["adj"])
    state = ranks.mean(axis=1).dropna()
    pos = {d: adj.index.get_loc(d) for d in state.index}
    last_start = len(adj) - HOLD - 1
    groups = {"core rich (80+)": state[state >= 80].index, "core very rich (95+)": state[state >= 95].index,
              "rich, starts 2013-2019": state[(state >= 80) & (state.index < "2020")].index, "rich, starts 2020-2022": state[(state >= 80) & (state.index >= "2020")].index,
              "any day": state.index}
    pd.set_option("display.width", 250, "display.float_format", "{:+.1f}".format)
    out = []
    for label, days in groups.items():
        starts = [pos[d] for d in days if pos[d] <= last_start][::5]
        core = basket_paths(adj, CORE, starts)
        rows = []
        for basket, names in BASKETS.items():
            ok = ~adj[names].iloc[starts].isna().any(axis=1).values
            outside = basket_paths(adj, names, starts)
            for share in SHARES:
                if share == 0 and basket != "defense":
                    continue
                mix = (1 - share) * core[ok] + share * outside[ok]       # dollars add up, so a mixed plan is the weighted sum of the two
                end, low = (mix[:, -1] - 1) * 100, (mix.min(axis=1) - 1) * 100
                rows.append(dict(basket="core only" if share == 0 else basket, outside=f"{share * 100:.0f}%", plans=int(ok.sum()), end_mean=end.mean(), end_median=np.median(end),
                                 end_worst=end.min(), lost_money=(end < 0).mean() * 100, low_mean=low.mean(), low_worst=low.min()))
        t = pd.DataFrame(rows)
        print(f"--- plans starting when: {label} ({len(starts)} plans, one every five trading days)")
        print(t.to_string(index=False), "\n")
        out.append(t.assign(group=label))
    pd.concat(out).to_csv(os.path.join(HERE, "cache", "div_share.csv"), index=False)


if __name__ == "__main__":
    main()
