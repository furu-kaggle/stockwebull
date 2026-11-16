"""Rich / cheap design for security stocks: bubble gauges tested on quantum names, plus security factors.

Layer 1  bubble gauges (per stock)
    P/S rank    today's price-to-sales against the stock's own last two years (0-100)   <- main gauge
    50-day z    how far the price sits from its 50-day average, in units of its spread   <- short-term heat
Layer 2  security factors (shift the thresholds, they do not replace the gauges)
    demand      CVEs published last full month vs a year earlier (sector-wide)
    delivery    is revenue growth speeding up or slowing (latest quarter yoy vs two quarters before)
Layer 3  bird's eye (sector-wide)
    rates       3-month return of 7-10 year Treasuries (falling prices = rising yields)
    market      Nasdaq-100 above or below its 200-day average
Layer 4  sentiment (read as a contrarian: fear and doubt leave room, euphoria does not)
    fear        1-month move of the volatility ETF (VIXY) against its own last two years (sector-wide)
    crowd       gap between the analysts' mean price target and the price (per stock)
    shown only  share of analysts rating buy, and the last five days' large-order money flow

Each factor scores -1, 0 or +1. The sum (clipped to -2..+2) moves the thresholds: a supportive
backdrop lets a stock run further before it counts as rich, a hostile one makes the plan stricter.
    pause buying   P/S rank >= 80 + 2.5 x score
    trim           P/S rank >= 95 + 1.5 x score (at most 99)
    buy more       P/S rank <= 20 + 2.5 x score
The threshold shifts are a design proposal and have not been backtested.

Usage: python draft/security_valuation.py [--export DIR]
"""
import argparse
import os

import numpy as np
import pandas as pd

from webull.data.data_client import DataClient

from _client import make_client
from data import CACHE, load_bars, load_income
from indicator_compare import as_of, load_per_share, trailing_rank
from tiers import ABOUT_JA, GROWTH_BAR, MARGIN_BAR
from universe import UNIVERSE

HERE = os.path.dirname(os.path.abspath(__file__))


def load_sentiment(symbols, refresh=False):
    """Analyst ratings, mean price target and five-day large-order flow (a snapshot: the API keeps no history)."""
    path = os.path.join(CACHE, "sentiment.pkl")
    if os.path.exists(path) and not refresh:
        return pd.read_pickle(path)
    data, rows = DataClient(make_client()), {}
    for sym in symbols:
        row = {}
        try:
            r = data.instrument.get_analyst_rating(sym).json()
            n = float(r.get("number") or 0)
            row["analysts"] = n
            row["buy_share"] = (float(r.get("strong_buy") or 0) + float(r.get("buy") or 0)) / n * 100 if n else np.nan
        except Exception:
            pass
        try:
            row["target"] = float(data.instrument.get_analyst_target_price(sym).json().get("mean"))
        except Exception:
            pass
        try:
            flow = data.fundamentals.get_capital_flow(sym, count=5).json()
            big_in, big_out = sum(float(f["large_in"]) for f in flow), sum(float(f["large_out"]) for f in flow)
            row["flow5"] = (big_in - big_out) / (big_in + big_out) * 100 if big_in + big_out else np.nan
        except Exception:
            pass
        rows[sym] = row
    table = pd.DataFrame(rows).T
    pd.to_pickle(table, path)
    return table


def sector_factors(close):
    cve = pd.read_csv(os.path.join(HERE, "cve_monthly.csv"), index_col="month")
    full = cve[[int(t) >= 28 for t in cve["through"]]]
    last = full.index[-1]
    prior = f"{int(last[:4]) - 1}{last[4:]}"
    cve_ratio = full.loc[last, "total"] / full.loc[prior, "total"]
    ief = close["IEF"].iloc[-1] / close["IEF"].iloc[-64] - 1
    qqq_gap = close["QQQ"].iloc[-1] / close["QQQ"].rolling(200).mean().iloc[-1] - 1
    vixy = close["VIXY"].pct_change(21)
    fear_rank = (vixy.tail(500) <= vixy.iloc[-1]).mean() * 100
    rows = [
        {"factor": "demand", "label": "需要：脆弱性の公表件数（前年同月比）", "reading": f"{cve_ratio:.1f}倍", "value": round(cve_ratio, 2),
         "score": 1 if cve_ratio >= 2 else -1 if cve_ratio < 1 else 0, "rule": "2倍以上で +1、前年割れで -1", "detail": f"{last} と {prior} の比較"},
        {"factor": "rates", "label": "金利：中期国債の3か月騰落率", "reading": f"{ief * 100:+.2f}%", "value": round(ief * 100, 2),
         "score": 1 if ief >= 0.02 else -1 if ief <= -0.02 else 0, "rule": "+2%以上（金利低下）で +1、-2%以下（金利上昇）で -1", "detail": "IEF の63営業日の騰落率"},
        {"factor": "market", "label": "市場：NASDAQ100 と200日平均の差", "reading": f"{qqq_gap * 100:+.2f}%", "value": round(qqq_gap * 100, 2),
         "score": 0 if qqq_gap >= 0 else -1, "rule": "200日平均より下で -1", "detail": "QQQ の終値と200日平均"},
        {"factor": "fear", "label": "心理：恐怖の強さ（変動率ETFの1か月の動き、過去2年での位置）", "reading": f"{fear_rank:.0f}%", "value": round(fear_rank, 1),
         "score": 1 if fear_rank >= 90 else -1 if fear_rank <= 10 else 0, "rule": "90%以上（恐怖）で +1、10%以下（楽観）で -1",
         "detail": f"VIXY の21営業日の騰落率 {vixy.iloc[-1] * 100:+.1f}%"},
    ]
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export")
    args = parser.parse_args()
    meta = {u[0]: u for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")}
    symbols = list(meta)
    close = load_bars(symbols + ["QQQ", "IEF", "CIBR", "VIXY"])["close"]
    per_share, income = load_per_share(symbols), load_income(symbols)
    sentiment = load_sentiment(symbols)
    sector = sector_factors(close)
    shared = int(sector["score"].sum())

    rows = []
    for sym in symbols:
        px = close[sym].dropna()
        sps = as_of(per_share[sym]["sps"], px.index)
        ps = px / sps
        rank = trailing_rank(ps).iloc[-1] * 100
        logp = np.log(px)
        z50 = ((logp - logp.rolling(50).mean()) / logp.rolling(50).std()).iloc[-1]
        q = income[income.symbol == sym].sort_values("end_date")
        yoy = (q.revenue / q.revenue.shift(4) - 1) * 100
        accel = yoy.iloc[-1] - yoy.iloc[-3] if len(yoy.dropna()) >= 3 else np.nan
        delivery = 0 if np.isnan(accel) else 1 if accel >= 1 else -1 if accel <= -1 else 0
        ttm_rev, ttm_op = q.revenue.tail(4).sum(), q.op_income.tail(4).sum()
        growth = (ttm_rev / q.revenue.iloc[-8:-4].sum() - 1) * 100 if len(q) >= 8 else np.nan
        margin = ttm_op / ttm_rev * 100
        tier = 4 if growth < GROWTH_BAR else 1 if margin >= MARGIN_BAR else 2 if margin > 0 else 3
        target = sentiment.loc[sym].get("target", np.nan) if sym in sentiment.index else np.nan
        upside = (target / px.iloc[-1] - 1) * 100 if target and not np.isnan(target) else np.nan
        crowd = 0 if np.isnan(upside) else -1 if upside <= 0 else 1 if upside >= 30 else 0
        score = int(np.clip(shared + delivery + crowd, -2, 2))
        pause, trim, cheap = 80 + 2.5 * score, min(95 + 1.5 * score, 99), 20 + 2.5 * score
        if np.isnan(rank):
            state = "判定不可"
        elif rank >= trim:
            state = "上げすぎ"
        elif rank >= pause:
            state = "割高"
        elif rank <= cheap:
            state = "割安"
        else:
            state = "通常"
        action = {"上げすぎ": "一部を売る", "割高": "買いを止める", "通常": "通常どおり買う", "割安": "多めに買う", "判定不可": "履歴不足"}[state]
        rows.append({"symbol": sym, "about": ABOUT_JA.get(sym, ""), "tier": tier, "ps": round(ps.iloc[-1], 1),
                     "ps_rank": None if np.isnan(rank) else int(round(rank)), "z50": round(z50, 2),
                     "yoy": round(yoy.iloc[-1], 1), "accel": None if np.isnan(accel) else round(accel, 1), "delivery": delivery,
                     "upside": None if np.isnan(upside) else round(upside, 1), "crowd": crowd,
                     "buy_share": None if np.isnan(sentiment.loc[sym].get("buy_share", np.nan)) else int(round(sentiment.loc[sym]["buy_share"])),
                     "flow5": None if np.isnan(sentiment.loc[sym].get("flow5", np.nan)) else round(sentiment.loc[sym]["flow5"], 1),
                     "score": score, "pause_at": pause, "trim_at": trim, "cheap_at": cheap, "state": state, "action": action,
                     "heat": "短期過熱" if z50 >= 2 else "短期売られすぎ" if z50 <= -2 else "—"})
    order = {"割安": 0, "通常": 1, "割高": 2, "上げすぎ": 3, "判定不可": 4}
    table = pd.DataFrame(rows).sort_values(["state", "ps_rank"], key=lambda c: c.map(order) if c.name == "state" else c).reset_index(drop=True)
    table.insert(0, "order", range(1, len(table) + 1))
    pd.set_option("display.width", 250, "display.float_format", "{:.1f}".format)
    print(sector.drop(columns=["label", "rule"]).to_string(index=False), f"\nshared score: {shared:+d}\n")
    print(table.drop(columns=["about"]).to_string(index=False))

    if args.export:
        os.makedirs(args.export, exist_ok=True)
        table["as_of"] = close.index[-1].date().isoformat()
        table.to_csv(os.path.join(args.export, "valuation.csv"), index=False)
        sector.to_csv(os.path.join(args.export, "factors.csv"), index=False)
        ja = {"P/S": "PSR", "P/B": "PBR", "RSI (14 days)": "RSI（14日）", "3-month return": "3か月の上昇率"}
        for n in (50, 100, 200):
            ja[f"z-score vs {n}-day avg"] = f"{n}日平均からの乖離（ばらつき換算）"
            ja[f"% above {n}-day avg"] = f"{n}日平均からの上方乖離率"
        parts = []
        for key in ("quantum", "security"):
            t = pd.read_csv(os.path.join(HERE, f"indicator_{key}.csv"))
            g = t.assign(beat=t.multiple > t.plain).groupby("indicator").agg(avg=("multiple", "mean"), beats=("beat", "mean"),
                                                                             fall=("max fall%", "mean"), plain=("plain", "mean"))
            parts.append(g.add_prefix(f"{key}_"))
        tests = pd.concat(parts, axis=1)
        tests["quantum_beats"], tests["security_beats"] = (tests["quantum_beats"] * 100).round(0), (tests["security_beats"] * 100).round(0)
        tests = tests.round(2).sort_values("quantum_avg", ascending=False)
        tests.insert(0, "order", range(1, len(tests) + 1))
        tests.index = [ja.get(i, i) for i in tests.index]
        tests.to_csv(os.path.join(args.export, "indicator_tests.csv"), index_label="indicator")
        print("\nexported to", args.export)
        print(tests.to_string())


if __name__ == "__main__":
    main()
