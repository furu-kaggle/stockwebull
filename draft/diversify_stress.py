"""How the candidates did in past sell-offs and rallies, and whether their link to security stocks is stable.

Windows are found from the data: the deepest falls of the security basket and of the Nasdaq-100 ETF since 2022.

Usage: python draft/diversify_stress.py
"""
import os

import numpy as np
import pandas as pd

from diversify import CANDIDATES, CORE, HERE, load, reference


def episodes(series, n=4, min_gap=40):
    """The n deepest peak-to-trough falls of a price index, without overlap."""
    out, s = [], series.copy()
    dd = s / s.cummax() - 1
    used = pd.Series(False, index=s.index)
    for _ in range(12):
        cand = dd[~used]
        if cand.empty:
            break
        trough = cand.idxmin()
        peak = s[:trough].idxmax()
        out.append((peak, trough, dd[trough] * 100))
        lo, hi = s.index.get_loc(peak), s.index.get_loc(trough)
        used.iloc[max(lo - min_gap, 0):hi + min_gap] = True
        if len(out) == n:
            break
    return sorted(out)


def main():
    close = load()
    ret = close.pct_change()
    ref = reference(ret)
    idx = (1 + ref.fillna(0)).cumprod()
    cands = [s for s in CANDIDATES if s in close and close[s].count() > 1100]
    windows = {"2022 rate-hike bear 22-03-29..22-11-03": ("2022-03-29", "2022-11-03"),
               "2025 tariff crash 25-02-19..25-04-08": ("2025-02-19", "2025-04-08"),
               "security-only bear 25-07-09..26-04-10": ("2025-07-09", "2026-04-10"),
               "AI rout 26-10-06..26-11-20": ("2026-10-06", "2026-11-20"),
               "security rally 26-04-10..26-10-29": ("2026-04-10", "2026-10-29")}
    windows = {k: (pd.Timestamp(a), pd.Timestamp(b)) for k, (a, b) in windows.items()}
    found = {name: episodes(idx[col]) for name, col in (("sector", "sector"), ("QQQ", "QQQ"))}
    print("deepest falls found in the data:", {k: [(f"{p:%y-%m-%d}", f"{t:%y-%m-%d}", round(d)) for p, t, d in v] for k, v in found.items()})
    table = pd.DataFrame({w: close.loc[b, cands] / close.loc[a, cands] - 1 for w, (a, b) in windows.items()}) * 100
    refs = pd.DataFrame({w: idx.loc[b] / idx.loc[a] - 1 for w, (a, b) in windows.items()}) * 100
    pd.set_option("display.width", 320, "display.max_rows", 200, "display.max_columns", 30)
    short = {w: f"W{i + 1}" for i, w in enumerate(windows)}
    for w, k in short.items():
        print(k, "=", w, " sector %.0f%% core %.0f%% QQQ %.0f%%" % (refs.loc["sector", w], refs.loc["core", w], refs.loc["QQQ", w]))
    t = table.rename(columns=short)
    falls = [k for w, k in short.items() if "rally" not in w]
    t["avg_in_falls"] = t[falls].mean(axis=1)
    t["worst_fall"] = t[falls].min(axis=1)
    t["up_in_falls"] = (t[falls] > 0).sum(axis=1)
    t.insert(0, "group", [CANDIDATES[s][0] for s in t.index])
    print(t.sort_values("avg_in_falls", ascending=False).round(0).to_string())
    t.to_csv(os.path.join(HERE, "cache", "div_stress.csv"))

    # is the link to security stocks stable from year to year?
    years = sorted(set(ret.index.year))
    cy = pd.DataFrame({y: ret.loc[str(y), cands].corrwith(ref.sector.loc[str(y)]) for y in years})
    cy["min"], cy["max"] = cy.min(axis=1), cy[years].max(axis=1)
    cy.insert(0, "group", [CANDIDATES[s][0] for s in cy.index])
    print("\ncorrelation with the security basket by calendar year")
    print(cy.sort_values("max").round(2).to_string())
    cy.to_csv(os.path.join(HERE, "cache", "div_corr_by_year.csv"))
    print("\nby group, average correlation by year"); print(cy.groupby("group")[years].mean().round(2).to_string())
    print("\nby group, average return in each window"); print(t.groupby("group")[list(short.values())].mean().round(0).to_string())


if __name__ == "__main__":
    main()
