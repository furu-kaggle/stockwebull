"""The savings-plan rules (MVP) and their backtest.

Plan: spend a fixed budget over `days` trading days, buying every day.
  budget today   cash left / days left, times 2 when the core is cheap, times 0.5 when nothing is attractive
                 (never more than twice the plain daily amount)
  where it goes  80% to the two core names, 20% to the best other name; when a core name is rich the core
                 share drops to 50% and up to three other names share the rest
  per name       cheap (P/S rank <= 20) counts 1.5, normal 1, rich (>= 80) 0.5, very rich (>= 95) 0;
                 nothing is bought in a name that is above its +1 sigma Bollinger band or jumped 15% in 5 days
  other names    must be growing and profitable where that is known; names in cfg["prefer"] first, then cheapest P/S rank
  outside        when the core is rich and no other security name qualifies, the rest goes to cfg["outside"]
                 (names from other sectors) at the full pace, instead of slowing down
  selling        only an unexplained spike: P/S rank >= 95 and 50-day z >= 2 with no earnings release in the
                 last five sessions. The holding above its target weight is sold; a name sold today is not
                 bought today; the cash goes back into the remaining days
Guardrails (small-order share, stock-talk posts on X) raise alerts for a person to read; they do not trade.

`decide` holds the rules and is shared by the backtest and the live runner.

Usage: python draft/plan_strategy.py [--universe security|quantum] [--days 60]
"""
import argparse

import numpy as np
import pandas as pd

from data import load_bars, load_income
from indicator_compare import as_of, load_per_share, trailing_rank
from universe import UNIVERSE

SLIP = 0.0005
CFG = dict(cheap=20, rich=80, very_rich=95, core_share=0.8, core_share_rich=0.5, max_others=3, jump=0.15, heat=2.0,
           min_order=1.0, max_orders=10)


def build_panels(symbols, with_quality=True, bars=None):
    bars = bars or load_bars(symbols)
    close, open_ = bars["close"][symbols], bars["open"][symbols]
    per_share = load_per_share(symbols)
    rank = pd.DataFrame({s: trailing_rank(close[s].dropna() / as_of(per_share[s]["sps"], close[s].dropna().index)) * 100 for s in symbols}).reindex(close.index)
    logp = np.log(close)
    z50 = (logp - logp.rolling(50).mean()) / logp.rolling(50).std()
    band = close.rolling(20).mean() + close.rolling(20).std()
    jump = close / close.shift(5) - 1
    income = load_income(symbols)
    recent_earnings = pd.DataFrame(False, index=close.index, columns=symbols)
    quality = pd.DataFrame(True, index=close.index, columns=symbols)
    for s in symbols:
        q = income[(income.symbol == s) & income.publish_date.notna()].sort_values("end_date")
        for pub in q.publish_date:
            pos = close.index.searchsorted(pub)
            recent_earnings.iloc[pos:pos + 6, recent_earnings.columns.get_loc(s)] = True
        if with_quality and len(q) >= 8:
            q = q[~q.publish_date.duplicated(keep="last")]
            rev, op = q.revenue.rolling(4).sum(), q.op_income.rolling(4).sum()
            ok = pd.Series(((rev / rev.shift(4) - 1 >= 0.08) & (op > 0)).values, index=q.publish_date.values).sort_index()
            quality[s] = ok.reindex(close.index.union(ok.index)).ffill().shift(1).reindex(close.index).fillna(False).astype(bool)
    # Everything a decision uses is known at the previous close.
    known = lambda df: df.shift(1)
    return dict(close=close, open=open_, rank=known(rank), z50=known(z50), above_band=known(close > band), jump=known(jump),
                earnings=known(recent_earnings).fillna(False).astype(bool), quality=known(quality).fillna(False).astype(bool), prev_close=known(close))


def decide(day, cash, shares, days_left, plain_daily, panels, core, others, cfg=CFG):
    """Return {symbol: dollars} to buy (+) or sell (-) at today's open."""
    rank, z50, prev = panels["rank"].loc[day], panels["z50"].loc[day], panels["prev_close"].loc[day]
    blocked = panels["above_band"].loc[day].fillna(False) | (panels["jump"].loc[day] >= cfg["jump"])
    value = shares * prev
    orders = {}

    # Sell only an unexplained spike, back to the target weight.
    held = value[value > 0]
    for sym in held.index:
        if rank.get(sym, np.nan) >= cfg["very_rich"] and z50.get(sym, 0) >= cfg["heat"] and not panels["earnings"].loc[day, sym]:
            target = value.sum() * (cfg["core_share"] / len(core) if sym in core else (1 - cfg["core_share"]))
            excess = value[sym] - target
            if excess >= cfg["min_order"]:
                orders[sym] = -excess

    def factor(sym):
        r = rank.get(sym, np.nan)
        if sym in orders or blocked.get(sym, False) or np.isnan(prev.get(sym, np.nan)):
            return 0.0
        if np.isnan(r):
            return 1.0
        return 0.0 if r >= cfg["very_rich"] else 0.5 if r >= cfg["rich"] else 1.5 if r <= cfg["cheap"] else 1.0

    core_f = {s: factor(s) for s in core}
    core_rich = any(f < 1 for f in core_f.values())
    pool = [s for s in others if factor(s) >= 1 and panels["quality"].loc[day, s]]
    prefer = cfg.get("prefer", [])                              # names a person judged to be the better places to move to
    pool = sorted(pool, key=lambda s: (s not in prefer, rank.get(s, 50) if not np.isnan(rank.get(s, np.nan)) else 50))[:cfg["max_others"] if core_rich else 1]
    weights = {}
    core_share = cfg["core_share_rich"] if core_rich else cfg["core_share"]
    if sum(core_f.values()) > 0:
        for s, f in core_f.items():
            weights[s] = core_share * f / sum(core_f.values())
    if pool:
        for s in pool:
            weights[s] = (1 - sum(weights.values())) / len(pool) if s == pool[0] else 0
        rest = 1 - sum(weights.get(s, 0) for s in core)
        for s in pool:
            weights[s] = rest / len(pool)
    if not pool:                                               # nowhere left inside the sector: the rest goes outside it
        outside = [s for s in cfg.get("outside", []) if factor(s) > 0]
        rest = 1 - sum(weights.values())
        for s in outside:
            weights[s] = rest / len(outside)
    total_w = sum(weights.values())
    if total_w <= 0:                                           # nothing attractive: buy the least stretched core name at half pace
        fallback = min(core, key=lambda s: rank.get(s, 50) if not np.isnan(rank.get(s, np.nan)) else 50)
        weights, total_w, pace = {fallback: 1.0}, 1.0, 0.5
    else:
        cheap_core = np.mean([f for f in core_f.values()]) >= 1.25
        went_outside = any(s in weights for s in cfg.get("outside", []))
        pace = 2.0 if cheap_core else 0.5 if (core_rich and not pool and not went_outside) else 1.0
    budget = min(cash / max(days_left, 1) * pace, 2 * plain_daily, cash)
    buys = {s: budget * w / total_w for s, w in weights.items() if budget * w / total_w >= cfg["min_order"]}
    for s, amount in sorted(buys.items(), key=lambda kv: -kv[1])[:cfg["max_orders"] - len(orders)]:
        orders[s] = amount
    return orders


CAPITAL = 645.0   # dollars: about 100,000 yen, so that the $1 minimum order bites as it would for real


def run_plan(panels, core, others, start, days, hold_after=126, cfg=CFG, plain=False):
    idx = panels["close"].index
    symbols = list(panels["close"].columns)
    shares, cash = pd.Series(0.0, index=symbols), CAPITAL
    plain_daily = CAPITAL / days
    wealth, n_orders, n_sells = [], 0, 0
    for k in range(days + hold_after):
        if start + k >= len(idx):
            break
        day = idx[start + k]
        if k < days:
            if plain:
                orders = {s: plain_daily / len(core) for s in core}
            else:
                orders = decide(day, cash, shares, days - k, plain_daily, panels, core, others, cfg)
            for sym, amount in orders.items():
                px = panels["open"].loc[day, sym]
                if np.isnan(px):
                    continue
                if amount > 0:
                    amount = min(amount, cash)
                    shares[sym] += amount / (px * (1 + SLIP))
                    cash -= amount
                else:
                    qty = min(-amount / px, shares[sym])
                    shares[sym] -= qty
                    cash += qty * px * (1 - SLIP)
                    n_sells += 1
                n_orders += 1
        elif k == days and cash > 1e-6 and not plain:              # anything left on the last day goes to the core
            for s in core:
                shares[s] += cash / len(core) / (panels["close"].loc[day, s] * (1 + SLIP))
            cash = 0.0
        wealth.append(cash + (shares * panels["close"].loc[day].ffill()).sum())
    w = pd.Series(wealth) / CAPITAL
    return dict(end=w.iloc[min(days, len(w)) - 1], later=w.iloc[-1] if len(w) >= days + hold_after else np.nan,
                dip=(w / w.cummax() - 1).min(), low=w.min(), orders=n_orders / days, sells=n_sells,
                names=int((shares > 1e-9).sum()), cash_end=cash / CAPITAL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["security", "quantum"], default="security")
    parser.add_argument("--days", type=int, default=60)
    args = parser.parse_args()
    if args.universe == "security":
        symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
        core, first, quality = ["QLYS", "TENB"], "2024-01-02", True
    else:
        symbols, core, first, quality = ["IONQ", "RGTI", "QBTS", "QUBT"], ["IONQ", "RGTI"], "2024-06-03", False
    others = [s for s in symbols if s not in core]
    panels = build_panels(symbols, with_quality=quality)
    idx = panels["close"].index
    starts = [i for i in range(idx.searchsorted(pd.Timestamp(first)), len(idx) - args.days, 5)]
    rows = []
    for i in starts:
        a, b = run_plan(panels, core, others, i, args.days), run_plan(panels, core, others, i, args.days, plain=True)
        rows.append(dict(start=idx[i], rule_end=a["end"], plain_end=b["end"], rule_later=a["later"], plain_later=b["later"], rule_dip=a["dip"],
                         plain_dip=b["dip"], rule_low=a["low"], plain_low=b["low"], orders=a["orders"], sells=a["sells"], names=a["names"]))
    t = pd.DataFrame(rows).set_index("start")
    pd.set_option("display.width", 220, "display.float_format", "{:.2f}".format)
    print(f"{args.universe}: core {core}, {len(others)} other names; {len(t)} plans of {args.days} trading days starting {t.index[0].date()} to {t.index[-1].date()}\n")
    def line(label, rule, base, pct=True):
        d = (t[rule] - t[base]).dropna()
        f = (lambda v: f"{(v - 1) * 100:+6.1f}%") if pct else (lambda v: f"{v * 100:+6.1f}%")
        print(f"{label:34} rules {f(t[rule].median())}   plain {f(t[base].median())}   rules better in {np.mean(d > 0) * 100:3.0f}% of plans"
              f"   worst: rules {f(t[rule].min())} / plain {f(t[base].min())}")
    line("value when the plan ends", "rule_end", "plain_end")
    line("value six months after", "rule_later", "plain_later")
    line("deepest fall from a peak", "rule_dip", "plain_dip", pct=False)
    line("lowest value vs money put in", "rule_low", "plain_low")
    print(f"\norders per day {t.orders.mean():.1f}, plans with a sale {np.mean(t.sells > 0) * 100:.0f}%, names held at the end {t.names.median():.0f}")
    t["gap"] = (t.rule_end - t.plain_end) * 100
    by_year = t.groupby(t.index.year).agg(plans=("gap", "size"), rule_end=("rule_end", lambda s: (s.median() - 1) * 100), plain_end=("plain_end", lambda s: (s.median() - 1) * 100),
                                           better=("gap", lambda s: (s > 0).mean() * 100))
    print("\nby start year (median value at plan end, %):"); print(by_year.to_string())
    print("\nbiggest gaps (rules minus plain, points):")
    print(t.assign(rule=(t.rule_end - 1) * 100, plain=(t.plain_end - 1) * 100)[["rule", "plain", "gap", "sells", "names"]].sort_values("gap").iloc[[0, 1, 2, -3, -2, -1]].to_string())


if __name__ == "__main__":
    main()
