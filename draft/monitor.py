"""Hourly watch during the US session. Prints today's moves and guardrail hits. Places no orders."""
import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from plan_live import CORE, fresh_bars, latest_prices
from plan_strategy import load_per_share, trailing_rank, as_of
from universe import UNIVERSE

SEC = [s for s, sector, *_ in UNIVERSE if sector == "security"]


def main():
    data = DataClient(make_client())
    bars = fresh_bars(data, SEC)
    close = bars["close"]
    now, days = latest_prices(data, SEC)
    now = now.reindex(SEC)
    today = max(days)
    hist = close[close.index < pd.Timestamp(today)] if pd.Timestamp(today) in close.index else close
    prev = hist.iloc[-1]
    live = hist.copy()
    live.loc[pd.Timestamp(today)] = now
    per_share = {}
    for s in SEC:                      # some names have no published financials here
        try:
            per_share.update(load_per_share([s]))
        except Exception:
            pass
    t = pd.DataFrame({"now": now, "day%": (now / prev - 1) * 100, "5d%": (now / live.iloc[-6] - 1) * 100})
    t["above+1s"] = now.values > (live.rolling(20).mean() + live.rolling(20).std()).iloc[-1].reindex(SEC).values
    t["ps_rank"] = [trailing_rank(live[s].dropna() / as_of(per_share[s]["sps"], live[s].dropna().index)).iloc[-1] * 100 if s in per_share else np.nan for s in SEC]
    t = t.sort_values("day%", ascending=False)
    print(f"prices as of {today}  (prev close {hist.index[-1].date()})")
    print(t.round(1).to_string())
    print(f"\nequal-weight day move {t['day%'].mean():+.2f}%   up {int((t['day%'] > 0).sum())} / down {int((t['day%'] < 0).sum())}")
    hits = []
    for s, r in t.iterrows():
        if r["5d%"] >= 15: hits.append(f"{s}: 5d jump {r['5d%']:+.1f}%")
        if r["ps_rank"] >= 95: hits.append(f"{s}: P/S rank {r['ps_rank']:.0f}")
        if s in CORE and abs(r["day%"]) > 5: hits.append(f"{s}: core day move {r['day%']:+.1f}%")
        if s in CORE and r["above+1s"]: hits.append(f"{s}: core above +1 sigma band")
    print("guardrails:", "; ".join(hits) if hits else "none")


if __name__ == "__main__":
    main()
