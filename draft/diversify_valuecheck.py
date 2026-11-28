"""Does the plan's yardstick also work on the names outside the sector?

The plan calls a name rich when its price-to-sales is high against its own trailing two years. Here the same
rank is built for about 35 defensive large companies from SEC filings and Yahoo prices, and once a month each
name's return over the next 60 / 120 / 250 trading days is compared with the average of the group on that
day. If rich defensive names go on to lag the group, the places to move to should be screened the same way.

Usage: python draft/diversify_valuecheck.py
"""
import os

import numpy as np
import pandas as pd

from long_history import prices, ps_rank

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE = {"defense": ["NOC", "LMT", "GD", "RTX"], "staples": ["KO", "PEP", "PG", "CL", "WMT", "COST", "DG", "MO", "MCD", "GIS", "KR", "PM"],
            "health": ["JNJ", "MRK", "AMGN", "ABBV", "LLY", "UNH"], "insurers": ["CB", "TRV", "PGR"], "power": ["DUK", "SO", "NEE"],
            "exchanges": ["CBOE", "CME", "ICE"], "waste": ["WM", "RSG"], "energy": ["XOM", "CVX"]}
BUCKETS = [("under 20", -1, 20), ("20-50", 20, 50), ("50-80", 50, 80), ("80-95", 80, 95), ("95+", 95, 101)]


def build():
    symbols = [s for names in UNIVERSE.values() for s in names]
    p = prices(symbols + ["SPY"])
    ranks, failed = {}, []
    for s in symbols:
        try:
            ranks[s] = ps_rank(s, p["close"][s])
        except Exception as err:
            failed.append((s, str(err)[:60]))
    return p["adj"], pd.DataFrame(ranks), failed


def main():
    adj, ranks, failed = build()
    print(f"{ranks.shape[1]} names with a rank; first full year {ranks.dropna(how='all').index[0].date()}; no data: {failed}")
    check = os.path.join(HERE, "cache", "div_profile.csv")
    if os.path.exists(check):                                        # the same rank from Webull's figures, as of today
        webull = pd.read_csv(check, index_col=0).ps_rank
        both = pd.DataFrame({"sec": ranks.iloc[-1], "webull": webull}).dropna()
        print(f"latest rank against the Webull-based one, {len(both)} names: correlation {both.corr().iloc[0, 1]:.2f}, average gap {(both.sec - both.webull).abs().mean():.1f} points")
        print("  largest gaps:", (both.sec - both.webull).abs().sort_values(ascending=False).head(5).round(0).to_dict())
    days = ranks.dropna(how="all").index[::21]
    pd.set_option("display.width", 220, "display.float_format", "{:+.1f}".format)
    out = []
    for horizon in (60, 120, 250):
        fwd = (adj.shift(-horizon) / adj - 1).loc[days, ranks.columns] * 100
        low = pd.DataFrame({s: (adj[s][::-1].rolling(horizon, min_periods=horizon).min()[::-1].shift(-1) / adj[s] - 1) for s in ranks.columns}).loc[days] * 100
        r = ranks.loc[days]
        ok = r.notna() & fwd.notna()
        excess = fwd.where(ok).sub(fwd.where(ok).mean(axis=1), axis=0)
        rows = []
        for label, lo, hi in BUCKETS:
            m = ok & (r >= lo) & (r < hi)
            f, e = fwd.where(m).stack().dropna(), excess.where(m).stack().dropna()
            rows.append(dict(rank=label, cases=len(f), ret=f.mean(), vs_group=e.mean(), beat_group=(e > 0).mean() * 100, lost_money=(f < 0).mean() * 100,
                             lowest_point=low.where(m).stack().mean()))
        t = pd.DataFrame(rows).set_index("rank")
        print(f"\n--- next {horizon} trading days, by the name's own two-year P/S rank ({len(days)} monthly dates, {int(ok.sum().sum())} cases)")
        print(t.to_string())
        out.append(t.assign(horizon=horizon))
        if horizon == 250:                                          # is the pattern there in each half of the history?
            for era, a, b in (("2013-2019", "2013", "2019"), ("2020-2025", "2020", "2025")):
                e, rr = excess.loc[a:b], r.loc[a:b]
                print(f"   {era}: vs group  " + "   ".join(f"{label} {e.where((rr >= lo) & (rr < hi)).stack().mean():+.1f}" for label, lo, hi in BUCKETS))
            by_group = {g: "   ".join(f"{label} {excess[names].where((r[names] >= lo) & (r[names] < hi)).stack().mean():+.1f}" for label, lo, hi in BUCKETS)
                        for g, names in ((g, [s for s in names if s in ranks]) for g, names in UNIVERSE.items())}
            for g, line in by_group.items():
                print(f"   {g:10} vs group  {line}")
    # The whole group at once: when defensive names are rich together, what did the group do next?
    level = ranks.loc[days].mean(axis=1)
    print(f"\n--- the group as a whole, by its average rank on the day (today {ranks.iloc[-1].mean():.0f}; share of names at 80+ today {(ranks.iloc[-1] >= 80).mean() * 100:.0f}%)")
    rows = []
    for label, lo, hi in (("under 35", -1, 35), ("35-50", 35, 50), ("50-65", 50, 65), ("65-80", 65, 80), ("80+", 80, 101)):
        m = (level >= lo) & (level < hi)
        row = dict(average_rank=label, dates=int(m.sum()))
        for horizon in (60, 120, 250):
            g = ((adj.shift(-horizon) / adj - 1).loc[days, ranks.columns] * 100).mean(axis=1)
            spy = (adj["SPY"].shift(-horizon) / adj["SPY"] - 1).loc[days] * 100
            row[f"group_{horizon}"], row[f"vs_spy_{horizon}"] = g[m].mean(), (g - spy)[m].mean()
        row["lost_250"] = (g[m].dropna() < 0).mean() * 100
        rows.append(row)
    print(pd.DataFrame(rows).set_index("average_rank").to_string())
    top = level.sort_values(ascending=False).head(12)
    print("   dates with the highest average rank:", ", ".join(f"{d.date()} ({v:.0f})" for d, v in top.sort_index().items()))
    pd.concat(out).to_csv(os.path.join(HERE, "cache", "div_valuecheck.csv"))
    ranks.iloc[[-1]].T.round(0).to_csv(os.path.join(HERE, "cache", "div_valuecheck_latest.csv"))


if __name__ == "__main__":
    main()
