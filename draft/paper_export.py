"""Write draft/paper/holdings.csv (one row per holding) from the paper-trading state, for the dashboard.

Usage: python draft/paper_export.py
"""
import csv
import json
import os

from paper import DIR, STATE


def main():
    state = json.load(open(STATE))
    path = os.path.join(DIR, "holdings.csv")
    with open(path, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["portfolio", "symbol", "weight_pct", "entry", "last", "return_pct"])
        for name, pf in state.items():
            last = pf.get("last", pf["entry"])
            total = sum(q * last[s] for s, q in pf["shares"].items())
            for sym, qty in pf["shares"].items():
                out.writerow([name, sym, f"{qty * last[sym] / total * 100:.2f}", f"{pf['entry'][sym]:.4f}",
                              f"{last[sym]:.4f}", f"{(last[sym] / pf['entry'][sym] - 1) * 100:.2f}"])
    print(path)


if __name__ == "__main__":
    main()
