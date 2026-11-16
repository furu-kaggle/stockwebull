"""Compare security names with access to restricted frontier cyber models against the rest.

Baskets are equal-weight, rebalanced daily, no costs: a descriptive comparison, not a backtest
(the grouping uses information that only became public from April 2026).

Usage: python draft/ai_basket.py
"""
import numpy as np
import pandas as pd

from data import load_bars
from universe import AI_ACCESS, UNIVERSE

EVENT = "2026-04-07"   # Project Glasswing launch (early April 2026)


def main():
    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    close = load_bars(symbols + ["QQQ", "CIBR"])["close"]
    rets = close.pct_change()
    direct = [s for s in symbols if set(AI_ACCESS.get(s, [])) & {"glasswing", "tac"}]
    groups = {
        "all 22 equal weight": symbols,
        "model access (direct)": direct,
        "  both labs (CRWD, PANW)": [s for s in symbols if {"glasswing", "tac"} <= set(AI_ACCESS.get(s, []))],
        "listed partner only": [s for s in symbols if s in AI_ACCESS and s not in direct],
        "no evidence": [s for s in symbols if s not in AI_ACCESS],
    }
    curves = {name: (1 + rets[members].mean(axis=1).fillna(0)).cumprod() for name, members in groups.items()}
    curves["CIBR"], curves["QQQ"] = close["CIBR"] / close["CIBR"].iloc[0], close["QQQ"] / close["QQQ"].iloc[0]
    last = close.index[-1]
    rows = {}
    for name, c in curves.items():
        since = c[c.index >= EVENT]
        r = c.pct_change().dropna()
        rows[name] = {
            "n": len(groups.get(name, [])) or np.nan,
            "1M%": (c.iloc[-1] / c.iloc[-22] - 1) * 100, "3M%": (c.iloc[-1] / c.iloc[-64] - 1) * 100,
            f"since {EVENT}%": (since.iloc[-1] / since.iloc[0] - 1) * 100,
            "1Y%": (c.iloc[-1] / c.iloc[-253] - 1) * 100,
            "vol 1Y%": r.tail(252).std() * np.sqrt(252) * 100,
            "maxDD since%": (since / since.cummax() - 1).min() * 100,
        }
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(f"As of {last.date()}\n"); print(pd.DataFrame(rows).T.to_string(), "\n")
    for name, members in groups.items():
        print(f"{name.strip()}: {', '.join(members)}")
    per = pd.DataFrame({"access": {s: "+".join(AI_ACCESS.get(s, ["-"])) for s in symbols},
                        "since%": {s: (close[s].dropna().iloc[-1] / close[s][close.index >= EVENT].dropna().iloc[0] - 1) * 100 for s in symbols},
                        "1M%": {s: (close[s].iloc[-1] / close[s].iloc[-22] - 1) * 100 for s in symbols}})
    print("\n", per.sort_values("since%", ascending=False).to_string())


if __name__ == "__main__":
    main()
