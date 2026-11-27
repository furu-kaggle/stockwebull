"""How closely the security ETF (CIBR) moves with the Nasdaq-100 ETF (QQQ), on up days and down days."""
import os
import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from plan_live import fresh_bars

HERE = os.path.dirname(os.path.abspath(__file__))


def stats(x, m):
    up, dn = m > 0, m < 0
    return dict(days=len(m), corr=x.corr(m), r2=x.corr(m) ** 2, beta=x.cov(m) / m.var(),
                up_days=int(up.sum()), up_capture=x[up].mean() / m[up].mean(), up_same_dir=(x[up] > 0).mean() * 100,
                down_days=int(dn.sum()), down_capture=x[dn].mean() / m[dn].mean(), down_same_dir=(x[dn] < 0).mean() * 100,
                etf_total=((1 + x).prod() - 1) * 100, qqq_total=((1 + m).prod() - 1) * 100)


def main():
    close = fresh_bars(DataClient(make_client()), ["CIBR", "HACK", "BUG", "QQQ", "QLYS", "TENB"], count=600)["close"]
    r = close.pct_change().dropna()
    core = r[["QLYS", "TENB"]].mean(axis=1)
    rows = {}
    for name, n in (("2 years", 500), ("1 year", 250), ("6 months", 125), ("3 months", 63), ("1 month", 21)):
        rows[name] = stats(r["CIBR"].iloc[-n:], r["QQQ"].iloc[-n:])
    pd.set_option("display.width", 220)
    print("CIBR vs QQQ, through", close.index[-1].date())
    print(pd.DataFrame(rows).T.round(2).to_string())
    print("\n1 year, other series vs QQQ")
    print(pd.DataFrame({k: stats(v.iloc[-250:], r["QQQ"].iloc[-250:]) for k, v in (("HACK", r["HACK"]), ("BUG", r["BUG"]), ("core pair", core))}).T.round(2).to_string())
    big = r.iloc[-250:]
    q = big["QQQ"]
    for label, mask in (("QQQ up 2%+", q >= 0.02), ("QQQ up 1-2%", (q >= 0.01) & (q < 0.02)), ("QQQ up 0-1%", (q > 0) & (q < 0.01)),
                        ("QQQ down 0-1%", (q < 0) & (q > -0.01)), ("QQQ down 1-2%", (q <= -0.01) & (q > -0.02)), ("QQQ down 2%+", q <= -0.02)):
        d = big[mask]
        print(f"{label:14s} days {len(d):3d}  QQQ {d.QQQ.mean() * 100:+.2f}%  CIBR {d.CIBR.mean() * 100:+.2f}%  core {core[d.index].mean() * 100:+.2f}%  CIBR same direction {((np.sign(d.CIBR) == np.sign(d.QQQ)).mean() * 100):.0f}%")
    print("\nlast 10 days %"); print((r[["QQQ", "CIBR"]].iloc[-10:] * 100).round(1).assign(core=(core.iloc[-10:] * 100).round(1)).to_string())
    r[["QQQ", "CIBR"]].iloc[-250:].assign(core=core.iloc[-250:]).to_csv(os.path.join(HERE, "cache", "etf_vs_nasdaq.csv"))


if __name__ == "__main__":
    main()
