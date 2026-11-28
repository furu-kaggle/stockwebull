"""Which five slots best sit beside the security names?

The owner's shape: half in security, and five other slots of 10% each. Here each slot is a kind of business
(a small equal-weight group of large companies, or one fund), every choice of five out of the sixteen kinds is
tried, and each resulting portfolio (50% core, 10% x 5, rebalanced daily) is measured since 2013:
  growth per year, yearly swing, the deepest fall, the return in each of seven past sell-offs,
  and the average day when the core had one of its worst 5% of days.
Combinations are ranked on four measures at once (deepest fall, average over the sell-offs, swing, growth per
unit of swing). A kind that keeps showing up among the best combinations is a robust pick; one best
combination alone would be a fluke of this sample.

Usage: python draft/lineup.py
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

from long_history import prices

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = ["QLYS", "TENB"]
KINDS = {"defense": ["NOC", "LMT", "GD", "LHX", "HII", "RTX"], "drinks and food": ["PEP", "KO", "GIS"], "household goods": ["PG", "CL"], "restaurants": ["MCD"],
         "retail": ["WMT", "COST", "DG", "KR"], "drug makers": ["LLY", "MRK", "JNJ", "AMGN", "ABBV"], "health insurer": ["UNH"], "insurance": ["PGR", "CB", "TRV"],
         "power": ["SO", "DUK", "NEE"], "oil": ["XOM", "CVX"], "exchanges": ["CBOE", "CME", "ICE"], "tobacco": ["MO", "PM"], "waste": ["WM", "RSG"], "telecom": ["T", "VZ"],
         "gold": ["GLD"], "7-10 year Treasuries": ["IEF"]}
WINDOWS = {"2015-06..2016-02": ("2015-06-23", "2016-02-09"), "2018 autumn": ("2018-09-12", "2018-12-24"), "covid 2020": ("2020-02-19", "2020-03-23"),
           "2021-11..2022-11": ("2021-11-09", "2022-11-03"), "tariffs 2025": ("2025-02-19", "2025-04-08"), "2025-07..2026-04": ("2025-07-09", "2026-04-10"),
           "AI rout 2026": ("2026-10-06", "2026-11-20")}
START = "2013-01-02"


def load(refresh=False):
    symbols = sorted(set(CORE + [s for names in KINDS.values() for s in names] + ["SPY", "QQQ", "SHV"]))
    adj = prices(symbols, refresh=refresh)["adj"].loc[START:].ffill()
    ret = adj.pct_change()
    kinds = pd.DataFrame({k: ret[names].mean(axis=1) for k, names in KINDS.items()})    # equal weight within a kind, names not yet listed are skipped
    kinds["core"], kinds["S&P 500"], kinds["Nasdaq 100"], kinds["T-bills"] = ret[CORE].mean(axis=1), ret["SPY"], ret["QQQ"], ret["SHV"]
    return kinds.iloc[1:], ret.iloc[1:]


def measure(r, core):
    wealth = (1 + r).cumprod()
    years = len(r) / 252
    out = dict(growth=(wealth.iloc[-1] ** (1 / years) - 1) * 100, swing=r.std() * np.sqrt(252) * 100, deepest=(wealth / wealth.cummax() - 1).min() * 100)
    for k, (a, z) in WINDOWS.items():
        out[k] = ((1 + r.loc[a:z]).prod() - 1) * 100
    out["falls_avg"] = np.mean([out[k] for k in WINDOWS])
    out["falls_worst"] = min(out[k] for k in WINDOWS)
    out["core_bad_day"] = r[core <= core.quantile(0.05)].mean() * 100
    out["per_swing"] = out["growth"] / out["swing"]
    return out


def main():
    k, ret = load("--refresh" in sys.argv)
    core = k["core"]
    pd.set_option("display.width", 250, "display.float_format", "{:+.1f}".format)
    print(f"daily returns {k.index[0].date()} to {k.index[-1].date()}\n")

    alone = pd.DataFrame({name: measure(k[name], core) for name in list(KINDS) + ["core", "S&P 500", "Nasdaq 100", "T-bills"]}).T
    alone["corr_with_core"] = k.corrwith(core)
    print("--- each kind on its own")
    print(alone[["growth", "swing", "deepest", "falls_avg", "falls_worst", "core_bad_day", "corr_with_core"] + list(WINDOWS)].sort_values("falls_avg", ascending=False).to_string())

    rows = {}
    for five in itertools.combinations(KINDS, 5):
        rows[five] = measure(0.5 * core + 0.1 * k[list(five)].sum(axis=1), core)
    t = pd.DataFrame(rows).T
    score = (t.deepest.rank(ascending=False) + t.falls_avg.rank(ascending=False) + t.swing.rank() + t.per_swing.rank(ascending=False)) / 4
    t["score"] = score
    t = t.sort_values("score")
    base = {"core only": core, "half core, half S&P 500": 0.5 * core + 0.5 * k["S&P 500"], "half core, half T-bills": 0.5 * core + 0.5 * k["T-bills"],
            "half core, half spread over all sixteen kinds": 0.5 * core + 0.5 * k[list(KINDS)].mean(axis=1)}
    b = pd.DataFrame({name: measure(r, core) for name, r in base.items()}).T
    cols = ["growth", "swing", "deepest", "falls_avg", "falls_worst", "core_bad_day"] + list(WINDOWS)
    print(f"\n--- {len(t)} portfolios of 50% core and five kinds at 10% each; for comparison first")
    print(b[cols].to_string())
    print("\n   the 12 best by the combined rank")
    top = t.head(12).copy()
    top.index = [" + ".join(i) for i in top.index]
    print(top[cols].to_string())
    print("\n   middle and worst of all combinations:")
    print(t[cols].describe().loc[["min", "25%", "50%", "75%", "max"]].to_string())

    best = t.head(len(t) // 20)                                      # the best 5% of combinations
    freq = pd.Series({kind: np.mean([kind in five for five in best.index]) * 100 for kind in KINDS}).sort_values(ascending=False)
    each = pd.Series({kind: t.score[[kind in five for five in t.index]].mean() for kind in KINDS})
    print(f"\n--- how often each kind is in the best 5% of combinations ({len(best)} of them; by chance it would be {5 / len(KINDS) * 100:.0f}%)")
    print("  ".join(f"{kind} {v:.0f}%" for kind, v in freq.items()))
    by_measure = {}
    for name, order in (("deepest fall", t.deepest.rank(ascending=False)), ("sell-offs", t.falls_avg.rank(ascending=False)), ("swing", t.swing.rank()), ("growth per swing", t.per_swing.rank(ascending=False))):
        chosen = order.sort_values().index[:len(t) // 20]
        by_measure[name] = pd.Series({kind: np.mean([kind in five for five in chosen]) * 100 for kind in KINDS})
    print("\n   the same count, measure by measure (a robust kind is high on all four)")
    print(pd.DataFrame(by_measure).assign(combined=freq).sort_values("combined", ascending=False).round(0).to_string())
    # The owner wants defense as one of the five: the same count over the combinations that include it.
    with_defense = t[[("defense" in five) for five in t.index]]
    best_d = with_defense.head(len(with_defense) // 10)
    freq_d = pd.Series({kind: np.mean([kind in five for five in best_d.index]) * 100 for kind in KINDS if kind != "defense"}).sort_values(ascending=False)
    print(f"\n--- with defense as one of the five ({len(with_defense)} combinations): how often each other kind is in the best tenth (by chance {4 / 15 * 100:.0f}%)")
    print("  ".join(f"{kind} {v:.0f}%" for kind, v in freq_d.items()))
    top_d = with_defense.head(8).copy()
    top_d.index = [" + ".join(i) for i in top_d.index]
    print(top_d[cols].to_string())

    # Named lineups: one company (or fund) per slot.
    lineups = {"NOC, MCD, PEP, PGR, NEE": ["NOC", "MCD", "PEP", "PGR", "NEE"], "LHX, MCD, PEP, PGR, NEE": ["LHX", "MCD", "PEP", "PGR", "NEE"],
               "LHX, MCD, PEP, PGR, GLD": ["LHX", "MCD", "PEP", "PGR", "GLD"], "LHX, MCD, LLY, PGR, GLD": ["LHX", "MCD", "LLY", "PGR", "GLD"],
               "LHX, MCD, LLY, NEE, GLD": ["LHX", "MCD", "LLY", "NEE", "GLD"], "NOC, MCD, LLY, PGR, GLD": ["NOC", "MCD", "LLY", "PGR", "GLD"],
               "NOC, GD, PEP, MCD (the earlier four, 12.5% each)": ["NOC", "GD", "PEP", "MCD"]}
    rows = {name: measure(0.5 * core + 0.5 * ret[names].mean(axis=1), core) for name, names in lineups.items()}
    print("\n--- named lineups: 50% core and the rest split equally")
    print(pd.DataFrame(rows).T[cols].to_string())

    print("\n--- correlation between the kinds (daily, since 2013)")
    pd.set_option("display.float_format", "{:.2f}".format)
    print(k[list(KINDS)].corr().round(2).to_string())
    t.reset_index().to_csv(os.path.join(HERE, "cache", "lineup_all.csv"), index=False)
    alone.to_csv(os.path.join(HERE, "cache", "lineup_kinds.csv"))


if __name__ == "__main__":
    main()
