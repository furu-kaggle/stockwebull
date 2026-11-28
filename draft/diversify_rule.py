"""Does the proposed rule depend on the numbers picked for it?

The rule: on each buying day, look at the core's average two-year P/S rank at the previous close; if it is at
or above a first level, send a share of the day outside the sector, and a larger share above a second level.
Here every 23-day plan since 2013 is run (one start every five trading days, held to 250 days after the
start) for a grid of levels and shares, so that the rule is judged over all conditions, not only the rich
ones. Outside = half SHV (0-1 year Treasuries), half the four sector funds that can be bought at Webull Japan
(ITA, XLV, XLP, XLU): funds, so that no stock is picked with hindsight.

Usage: python draft/diversify_rule.py
"""
import os

import numpy as np
import pandas as pd

from diversify_rich import CORE, load
from long_history import prices

HERE = os.path.dirname(os.path.abspath(__file__))
FUNDS = ["ITA", "XLV", "XLP", "XLU"]
BUY_DAYS, HOLD = 23, 250
RULES = {"never outside": {}, "always 30%": {0: 0.3}, "always 50%": {0: 0.5},
         "80+: 30%": {80: 0.3}, "80+: 50%": {80: 0.5}, "80+: 70%": {80: 0.7}, "80+: 100%": {80: 1.0},
         "80+: 30%, 95+: 50%": {80: 0.3, 95: 0.5}, "80+: 50%, 95+: 70% (proposed)": {80: 0.5, 95: 0.7}, "80+: 50%, 95+: 100%": {80: 0.5, 95: 1.0},
         "70+: 50%, 95+: 70%": {70: 0.5, 95: 0.7}, "90+: 50%, 95+: 70%": {90: 0.5, 95: 0.7}, "95+: 70% only": {95: 0.7},
         "60+: 50%": {60: 0.5}, "opposite: 50% outside when under 50": {-1: 0.5, 50: 0.0}}


def share_for(level, rule):
    """Share sent outside for each day's rank level (NaN: none)."""
    out = np.zeros(len(level))
    for k in sorted(rule):
        out = np.where(level >= k, rule[k], out)
    return out


def run(adj, state, starts, rule):
    """Value / money put in at the end and at the lowest point, for each plan start."""
    core = adj[CORE].values
    outside = np.column_stack([adj["SHV"].values] + [adj[f].values for f in FUNDS])
    weights = np.array([0.5] + [0.5 / len(FUNDS)] * len(FUNDS))
    known = state.shift(1).reindex(adj.index).values               # the rank known before each day's purchase
    share = share_for(known, rule)
    ends, lows = [], []
    for i in starts:
        days = slice(i, i + BUY_DAYS)
        have = ~np.isnan(core[i])                                   # Tenable is not listed in the early years
        s = share[days][:, None]
        units_core = ((1 - s) / have.sum() / BUY_DAYS / core[days][:, have])
        units_out = (s * weights / BUY_DAYS / outside[days])
        path_core = np.cumsum(units_core, axis=0)
        path_out = np.cumsum(units_out, axis=0)
        window = slice(i, i + HOLD + 1)
        held_core = np.vstack([path_core, np.repeat(path_core[-1:], HOLD + 1 - BUY_DAYS, axis=0)])
        held_out = np.vstack([path_out, np.repeat(path_out[-1:], HOLD + 1 - BUY_DAYS, axis=0)])
        value = (held_core * core[window][:, have]).sum(axis=1) + (held_out * outside[window]).sum(axis=1)
        paid = np.minimum(np.arange(HOLD + 1) + 1, BUY_DAYS) / BUY_DAYS
        path = value / paid
        ends.append(path[-1] - 1)
        lows.append(path.min() - 1)
    return np.array(ends) * 100, np.array(lows) * 100


def main():
    adj, ranks = load()
    adj = adj.join(prices([s for s in ["SHV"] + FUNDS if s not in adj.columns])["adj"])
    state = ranks.mean(axis=1).dropna()
    first = adj.index.get_loc(state.index[0]) + 1
    starts = list(range(first, len(adj) - HOLD - 1, 5))
    rich_start = np.array([state.reindex(adj.index).iloc[i - 1] >= 80 for i in starts])
    rows = []
    for name, rule in RULES.items():
        end, low = run(adj, state, starts, rule)
        rows.append(dict(rule=name, end_mean=end.mean(), end_median=np.median(end), end_worst=end.min(), lost_money=(end < 0).mean() * 100, low_mean=low.mean(), low_worst=low.min(),
                         end_mean_rich=end[rich_start].mean(), end_worst_rich=end[rich_start].min(), end_mean_other=end[~rich_start].mean()))
    t = pd.DataFrame(rows).set_index("rule")
    pd.set_option("display.width", 240, "display.float_format", "{:+.1f}".format)
    print(f"{len(starts)} plans from {adj.index[starts[0]].date()} to {adj.index[starts[-1]].date()}; {rich_start.sum()} of them start with the core rich\n")
    print(t.to_string())
    t.to_csv(os.path.join(HERE, "cache", "div_rule.csv"))


if __name__ == "__main__":
    main()
