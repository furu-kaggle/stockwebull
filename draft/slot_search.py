"""Candidates for the two slots now held by power and gold.

About ninety large companies and funds outside technology, grouped by kind of business. For each: how it did in
seven past sell-offs, how closely it moves with the security core and with the three slots that stay (NOC, MCD,
PEP), how much it swings, what it returned, and how far it stands below its one-year high. Valuation and results
come in a second step (diversify_profile.py) for the names that pass.

Usage: python draft/slot_search.py
"""
import os

import numpy as np
import pandas as pd

from lineup import WINDOWS
from long_history import prices

HERE = os.path.dirname(os.path.abspath(__file__))
CORE, KEPT = ["QLYS", "TENB"], ["NOC", "MCD", "PEP"]
KINDS = {
    "health services": ["UNH", "ELV", "CI", "CVS", "HUM", "CNC"], "medical devices and tools": ["MDT", "ABT", "SYK", "BDX", "TMO", "DHR"],
    "drug makers": ["LLY", "MRK", "JNJ", "PFE", "ABBV", "AMGN", "BMY", "GILD", "VRTX", "REGN", "NVO"],
    "insurance": ["PGR", "CB", "TRV", "ALL", "AIG", "MMC", "AON", "AJG", "BRK-B", "MKL"], "exchanges and data": ["ICE", "CME", "CBOE", "NDAQ", "SPGI", "MCO", "MSCI", "FICO"],
    "telecom": ["T", "VZ", "TMUS", "CMCSA"], "food and household": ["GIS", "KHC", "MDLZ", "HSY", "KMB", "CLX", "STZ", "KDP", "MNST", "SYY", "ADM", "TSN", "KR", "CL", "PG", "KO", "COST", "WMT", "DG"],
    "tobacco": ["PM", "MO"], "property": ["O", "AMT", "PLD", "PSA", "WELL"], "pipelines": ["KMI", "WMB", "OKE", "ENB"], "oil": ["XOM", "CVX"],
    "transport": ["UNP", "CSX", "UPS", "FDX"], "business services": ["WM", "RSG", "ROL", "CTAS", "ADP", "PAYX"], "home improvement": ["HD", "LOW"], "payments": ["V", "MA"],
    "water": ["AWK"], "bonds": ["IEF", "TLT", "TIP", "BND", "SHV"], "other regions": ["EWJ", "EFA", "EEM"], "dividend funds": ["VYM", "HDV", "SPYD", "VTV"],
    "metals": ["GLD", "SLV"], "power": ["NEE", "AEP", "SO", "DUK", "XEL", "D"],
}


def main():
    names, missing = [], []
    for s in [s for v in KINDS.values() for s in v]:           # a ticker that no longer exists is skipped
        try:
            prices([s])
            names.append(s)
        except Exception:
            missing.append(s)
    if missing:
        print("no prices for:", missing)
    adj = prices(sorted(set(names + CORE + KEPT + ["SPY"])))["adj"].loc["2013-01-02":].ffill()
    ret = adj.pct_change().iloc[1:]
    core, kept = ret[CORE].mean(axis=1), ret[KEPT].mean(axis=1)
    last = adj.index[-1]
    rows = []
    for kind, members in KINDS.items():
        for s in [m for m in members if m in names]:
            r, a = ret[s], adj[s].dropna()
            wins = {k: ((1 + r.loc[x:y]).prod() - 1) * 100 if not np.isnan(adj[s].loc[:x].iloc[-1] if len(adj[s].loc[:x]) else np.nan) else np.nan for k, (x, y) in WINDOWS.items()}
            vals = [v for v in wins.values() if not np.isnan(v)]
            ago = lambda y: a.loc[a.index >= last - pd.DateOffset(years=y)].iloc[0]
            rows.append(dict(kind=kind, ticker=s, rose=sum(v > 0 for v in vals), of=len(vals), falls_avg=np.mean(vals), worst=min(vals), core_bad_day=r[core <= core.quantile(0.05)].mean() * 100,
                             corr_core=r.iloc[-750:].corr(core.iloc[-750:]), corr_kept=r.iloc[-750:].corr(kept.iloc[-750:]), swing=r.iloc[-750:].std() * np.sqrt(252) * 100,
                             ret_1y=(a.iloc[-1] / ago(1) - 1) * 100, ret_3y=((a.iloc[-1] / ago(3)) ** (1 / 3) - 1) * 100, ret_5y=((a.iloc[-1] / ago(5)) ** 0.2 - 1) * 100,
                             from_high=(a.iloc[-1] / a.iloc[-252:].max() - 1) * 100, **{k: v for k, v in wins.items()}))
    t = pd.DataFrame(rows).set_index("ticker")
    t.to_csv(os.path.join(HERE, "cache", "slot_search.csv"))
    pd.set_option("display.width", 250, "display.max_rows", 200, "display.float_format", "{:+.1f}".format)
    show = ["kind", "rose", "of", "falls_avg", "worst", "core_bad_day", "corr_core", "corr_kept", "swing", "ret_1y", "ret_3y", "ret_5y", "from_high"]
    print(t[show].to_string())


if __name__ == "__main__":
    main()
