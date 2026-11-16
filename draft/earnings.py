"""Earnings calendar for the security / quantum universe: next report date and estimates,
plus how the last report came in against estimates.

Usage: python draft/earnings.py [SYMBOL ...]     (defaults to every stock in universe.py)
"""
import sys
from datetime import date

import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from universe import UNIVERSE


def pct(actual, est):
    try:
        actual, est = float(actual), float(est)
        return (actual - est) / abs(est) * 100 if est else None
    except (TypeError, ValueError):
        return None


def main():
    meta = {u[0]: u for u in UNIVERSE if u[2] not in ("etf", "bench")}
    symbols = sys.argv[1:] or list(meta)
    data = DataClient(make_client())
    today = date.today().isoformat()
    rows = []
    for sym in symbols:
        try:
            cal = data.fundamentals.get_earnings_calendar(sym).json() or []
        except Exception as err:  # keep going if one symbol has no data
            print(f"{sym}: {str(err)[:100]}", file=sys.stderr)
            continue
        reported = [c for c in cal if c.get("eps_actual") is not None or c.get("rev_actual") is not None]
        upcoming = [c for c in cal if c not in reported and (c.get("expected_publish_date") or "") >= today]
        nxt = min(upcoming, key=lambda c: c.get("expected_publish_date") or "9999") if upcoming else {}
        last = max(reported, key=lambda c: c.get("expected_publish_date") or "") if reported else {}
        nxt_date = nxt.get("expected_publish_date")
        rows.append({
            "symbol": sym, "sector": meta.get(sym, ("", "?"))[1], "group": meta.get(sym, ("", "", "?"))[2],
            "next": nxt_date, "days": (date.fromisoformat(nxt_date) - date.fromisoformat(today)).days if nxt_date else None,
            "eps_est": nxt.get("eps_est"), "rev_est_$M": float(nxt["rev_est"]) / 1e6 if nxt.get("rev_est") else None,
            "last": last.get("expected_publish_date"),
            "last_eps_surprise%": pct(last.get("eps_actual"), last.get("eps_est")),
            "last_rev_surprise%": pct(last.get("rev_actual"), last.get("rev_est")),
        })
    table = pd.DataFrame(rows).sort_values("next", na_position="last")
    pd.set_option("display.width", 250, "display.max_rows", 200, "display.float_format", "{:.1f}".format)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
