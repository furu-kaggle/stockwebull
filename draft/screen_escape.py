"""Screen escape candidates across cyber, physical security and cryptography names.

Cheapness (P/S and P/B rank over two years), whether the multiple is turning up,
whether results are improving, correlation with the core pair, and X attention.
"""
import os, sys, time
import numpy as np, pandas as pd, requests
from webull.data.data_client import DataClient
from _client import make_client
from plan_live import fresh_bars, CORE
from indicator_compare import load_per_share, trailing_rank, as_of
from data import load_income
from universe import UNIVERSE

CYBER = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
PHYSICAL = ["MSI", "ALLE", "BCO", "REZI", "JCI", "NSSC", "AXON", "ADT"]
CRYPTO = ["ARQQ", "LAES", "BTQ"]
GROUP = {**{s: "cyber" for s in CYBER}, **{s: "physical" for s in PHYSICAL}, **{s: "crypto" for s in CRYPTO}}


def attention(symbols):
    """Views of the top cashtag posts in the last 7 days against the 7 days before."""
    key = os.environ.get("TWITTERAPI_IO_SECRET")
    out = {}
    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    for s in symbols:
        v = []
        for a, b in ((14, 7), (7, 0)):
            q = f"${s} min_faves:5 lang:en since:{(today - pd.Timedelta(days=a)).date()} until:{(today - pd.Timedelta(days=b) + pd.Timedelta(days=1 if b == 0 else 0)).date()}"
            t = []
            for _ in range(3):
                try:
                    t = requests.get("https://api.twitterapi.io/twitter/tweet/advanced_search", headers={"X-API-Key": key},
                                     params={"query": q, "queryType": "Top"}, timeout=60).json().get("tweets", [])
                    break
                except Exception:
                    time.sleep(2)
            v.append(sum(x.get("viewCount") or 0 for x in t))
            time.sleep(0.2)
        out[s] = v
    return out


def main():
    syms = list(GROUP)
    d = DataClient(make_client())
    close = fresh_bars(d, syms)["close"]
    ret = close.pct_change()
    core = ret[CORE].mean(axis=1)
    inc = load_income(syms)
    att = attention(syms) if "--x" in sys.argv else {}
    rows = []
    for s in syms:
        c = close[s].dropna()
        row = dict(sym=s, group=GROUP[s])
        try:
            ps = load_per_share([s])[s]
            psr = trailing_rank(c / as_of(ps["sps"], c.index)) * 100
            pbr = trailing_rank(c / as_of(ps["bps"], c.index)) * 100
            row.update(ps_rank=psr.iloc[-1], ps_rank_1m_ago=psr.iloc[-22], pb_rank=pbr.iloc[-1])
        except Exception:
            pass
        q = inc[inc.symbol == s].sort_values("end_date")
        q = q[~q.end_date.duplicated(keep="last")]
        rev, op = q.revenue.rolling(4).sum(), q.op_income.rolling(4).sum()
        if len(rev) > 9:
            g = rev / rev.shift(4) - 1
            m = op / rev
            row.update(growth=g.iloc[-1] * 100, growth_chg=(g.iloc[-1] - g.iloc[-3]) * 100,
                       margin=m.iloc[-1] * 100, margin_chg=(m.iloc[-1] - m.iloc[-5]) * 100)
        row.update(corr=ret[s].iloc[-252:].corr(core.iloc[-252:]), m1=(c.iloc[-1] / c.iloc[-22] - 1) * 100,
                   from_high=(c.iloc[-1] / c.iloc[-252:].max() - 1) * 100)
        if s in att:
            row.update(x_views_k=att[s][1] / 1e3, x_change=att[s][1] / att[s][0] if att[s][0] else np.nan)
        rows.append(row)
    t = pd.DataFrame(rows)
    t["profit"] = t.margin > 0
    t["improving"] = (t.growth_chg > 0) | (t.margin_chg > 0)
    t["multiple_up"] = t.ps_rank > t.ps_rank_1m_ago
    t.to_csv("screen_escape.csv", index=False)
    pd.set_option("display.width", 250)
    print(close.index[-1].date())
    print(t.sort_values(["group", "ps_rank"]).round(1).to_string(index=False))


if __name__ == "__main__":
    main()
