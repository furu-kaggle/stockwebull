"""What happened after the core names were rich?

Webull's 1,200 daily bars hold only one spell with the core rich (the present one), so this uses the longer
history in `long_history.py`: Qualys since 2013, Tenable since 2021. For every day, take the state of the core
(two-year P/S rank at that day's close; the average of the two names once both exist) and look at the return
over the next 20 / 60 / 120 / 250 trading days of the core, the security fund, the Nasdaq 100 and each group
of candidates (dividends included). Days in one state are not independent (the windows overlap), so the number
of separate spells is printed too: that is the real sample size.

Usage: python draft/diversify_rich.py [--refresh]
"""
import os
import sys

import numpy as np
import pandas as pd

from long_history import prices, ps_rank

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = ["QLYS", "TENB"]
STATES = [("very rich (95+)", 95, 101), ("rich (80-95)", 80, 95), ("normal (20-80)", 20, 80), ("cheap (under 20)", -1, 20)]
GROUPS = {"security fund": ["CIBR"], "QQQ": ["QQQ"], "S&P 500": ["SPY"], "defense": ["NOC", "LMT", "GD", "RTX"], "staples": ["KO", "PG", "PEP", "WMT", "CL"],
          "health": ["LLY", "AMGN", "MRK", "JNJ", "ABBV"], "energy": ["XOM", "CVX"], "insurers": ["CB", "TRV", "PGR"], "power": ["DUK", "SO", "NEE"],
          "T-bills": ["BIL"], "DG": ["DG"], "CBOE": ["CBOE"], "low-vol": ["USMV"], "gold": ["GLD"], "long bonds": ["TLT"], "UI": ["UI"], "AXON": ["AXON"]}
SYMBOLS = sorted(set(CORE + ["HACK"] + [s for names in GROUPS.values() for s in names]))


def spells(mask, gap=20):
    """Start and end positions of the runs of True, joining runs less than `gap` days apart."""
    days = np.flatnonzero(mask.values)
    if len(days) == 0:
        return []
    cuts = np.flatnonzero(np.diff(days) > gap)
    return list(zip(days[np.r_[0, cuts + 1]], days[np.r_[cuts, len(days) - 1]]))


def load(refresh=False):
    p = prices(SYMBOLS, refresh=refresh)
    ranks = pd.DataFrame({s: ps_rank(s, p["close"][s]) for s in CORE})
    return p["adj"], ranks


def forward_table(adj, state, horizon):
    series = {"core": adj[CORE]}
    series.update({g: adj[names] for g, names in GROUPS.items()})
    fwd = pd.DataFrame({name: (c.shift(-horizon) / c - 1).mean(axis=1) * 100 for name, c in series.items()}).loc[state.index].dropna(subset=["core"])
    rows = {}
    for label, lo, hi in STATES:
        mask = (state.loc[fwd.index] >= lo) & (state.loc[fwd.index] < hi)
        row = fwd[mask].mean()
        row["days"], row["spells"], row["core down %"] = mask.sum(), len(spells(mask)), (fwd.core[mask] < 0).mean() * 100
        row["core vs QQQ"] = (fwd.core[mask] - fwd.QQQ[mask]).mean()
        rows[label] = row
    rows["all days"] = fwd.mean().reindex(row.index)
    rows["all days"]["days"], rows["all days"]["core down %"] = len(fwd), (fwd.core < 0).mean() * 100
    return pd.DataFrame(rows).T[["days", "spells", "core down %", "core", "core vs QQQ"] + list(GROUPS)]


def main():
    adj, ranks = load("--refresh" in sys.argv)
    pd.set_option("display.width", 280, "display.float_format", "{:+.1f}".format)
    print(f"P/S rank: QLYS from {ranks.QLYS.dropna().index[0].date()}, TENB from {ranks.TENB.dropna().index[0].date()}; latest QLYS {ranks.QLYS.iloc[-1]:.0f}, TENB {ranks.TENB.iloc[-1]:.0f}\n")
    state = ranks.mean(axis=1).dropna()                               # Qualys alone until Tenable has a rank
    out = []
    for horizon in (20, 60, 120, 250):
        t = forward_table(adj, state, horizon)
        print(f"--- return over the next {horizon} trading days (%), by the state of the core")
        print(t.to_string(), "\n")
        out.append(t.assign(horizon=horizon))
    pd.concat(out).to_csv(os.path.join(HERE, "cache", "div_rich_forward.csv"))

    print("--- each spell with the core rich (rank 80+): what the core did afterwards, and the candidates over the same 250 days")
    rows = []
    for a, b in spells(state >= 80):
        first, last = state.index[a], state.index[b]
        i = adj.index.get_loc(first)
        path = (adj[CORE].iloc[i:i + 251] / adj[CORE].iloc[i]).mean(axis=1)
        j = min(i + 250, len(adj) - 1)
        chg = lambda cols: (adj[cols].iloc[j] / adj[cols].iloc[i] - 1).mean() * 100
        rows.append(dict(first=first.date(), last=last.date(), days=b - a + 1, peak_rank=state.iloc[a:b + 1].max(), after=j - i,
                         core=(path.iloc[-1] - 1) * 100, core_high=(path.max() - 1) * 100, core_low=(path.min() - 1) * 100,
                         **{g: chg(names) for g, names in GROUPS.items() if g in ("security fund", "QQQ", "defense", "staples", "health", "energy", "insurers", "T-bills", "DG", "gold")}))
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv(os.path.join(HERE, "cache", "div_rich_spells.csv"), index=False)


if __name__ == "__main__":
    main()
