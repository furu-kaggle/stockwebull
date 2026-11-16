"""Security-sector strategy backtest built on three views.

  bird  (macro regime)  : how much capital to deploy at all
  fish  (flow / trend)  : which names the money is moving into
  insect (company)      : earnings reaction and point-in-time fundamentals

Long-only (cash account), weekly rebalance: signals use data up to the last close of the week,
orders fill at the next session's open, and every trade pays `--cost` per side.

Usage: python draft/backtest_security.py [--top 5] [--cost 0.003] [--sensitivity]
"""
import argparse

import numpy as np
import pandas as pd

from data import load_bars, load_income
from universe import UNIVERSE

BENCH = ["QQQ", "CIBR", "IEF"]
WARMUP = 200  # trading days needed before the first signal (200-day average)


def zscore(row):
    sd = row.std()
    return (row - row.mean()) / sd if sd and not np.isnan(sd) else row * 0


# ---------- signals (each returns a DataFrame/Series indexed by date; value at date t uses data <= close t) ----------

def bird_exposure(close):
    """0, 0.5 or 1: half for the market trend, half for rates not spiking."""
    market_ok = close["QQQ"] > close["QQQ"].rolling(200).mean()
    rates_ok = close["IEF"].pct_change(63) > -0.03          # 7-10y Treasuries not down >3% in 3 months
    return 0.5 * market_ok.astype(float) + 0.5 * rates_ok.astype(float)


def fish_score(close, symbols):
    """Cross-sectional 6-month momentum (skipping the latest week); only names above their 100-day average."""
    px = close[symbols]
    momentum = px.shift(5) / px.shift(126) - 1
    uptrend = px > px.rolling(100).mean()
    return momentum.apply(zscore, axis=1), uptrend


def insect_score(close, income, symbols):
    """Latest earnings reaction + revenue growth + operating-margin change, known as of each date."""
    px = close[symbols]
    cols = {k: pd.DataFrame(np.nan, index=px.index, columns=symbols) for k in ("reaction", "growth", "margin")}
    for sym in symbols:
        q = income[(income.symbol == sym) & income.publish_date.notna()].sort_values("end_date").copy()
        if q.empty:
            continue
        q["growth"] = q.revenue / q.revenue.shift(4) - 1
        q["margin"] = q.op_income / q.revenue - (q.op_income.shift(4) / q.revenue.shift(4))
        s = px[sym].dropna()
        for _, r in q.iterrows():
            pos = s.index.searchsorted(r.publish_date)      # first session on/after the announcement
            if pos < 1 or pos + 1 >= len(s):
                continue
            known = s.index[pos + 1]                         # reaction is complete at this close
            # close before the report -> close of the next session covers pre- and post-market reporters
            cols["reaction"].loc[known, sym] = s.iloc[pos + 1] / s.iloc[pos - 1] - 1
            cols["growth"].loc[known, sym] = r.growth
            cols["margin"].loc[known, sym] = r.margin
    parts = [cols[k].ffill(limit=100).apply(zscore, axis=1) for k in cols]   # stale after ~5 months
    return pd.concat(parts).groupby(level=0).mean(), cols["reaction"].ffill(limit=100)


# ---------- engine ----------

def run(bars, target_weights, cost):
    """target_weights: DataFrame on rebalance dates (decided at that close, filled next open)."""
    close, open_ = bars["close"].ffill(), bars["open"]
    symbols = list(target_weights.columns)
    shares, cash, pending = pd.Series(0.0, index=symbols), 1.0, None
    equity, turnover = {}, 0.0
    for day in close.index:
        if pending is not None:
            px = open_.loc[day, symbols].fillna(close.loc[day, symbols])
            value = cash + (shares * px).sum()
            target = (pending * value / px).fillna(0.0)
            traded = ((target - shares).abs() * px).sum()
            cash = value - (target * px).sum() - traded * cost
            turnover += traded / value
            shares, pending = target, None
        equity[day] = cash + (shares * close.loc[day, symbols].fillna(0)).sum()
        if day in target_weights.index:
            pending = target_weights.loc[day]
    return pd.Series(equity), turnover


def stats(equity, turnover=None):
    r = equity.pct_change().dropna()
    years = len(r) / 252
    out = {
        "CAGR%": (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) * 100 - 100,
        "Vol%": r.std() * np.sqrt(252) * 100,
        "Sharpe": r.mean() / r.std() * np.sqrt(252) if r.std() else np.nan,
        "MaxDD%": (equity / equity.cummax() - 1).min() * 100,
    }
    if turnover is not None:
        out["Turnover/yr"] = turnover / years
    return out


def build_weights(close, income, symbols, top, use_bird=True, use_fish=True, use_insect=True):
    fish, uptrend = fish_score(close, symbols)
    insect, reaction = insect_score(close, income, symbols)
    exposure = bird_exposure(close)
    days = close.index[WARMUP:]
    rebalance = days[pd.Series(days.isocalendar().week.values, index=days).shift(-1).ne(
        pd.Series(days.isocalendar().week.values, index=days)).values]      # last session of each week
    weights = pd.DataFrame(0.0, index=rebalance, columns=symbols)
    for day in rebalance:
        tradable = close.loc[day, symbols].notna() & close[symbols].shift(126).loc[day].notna()
        score = pd.Series(0.0, index=symbols)
        if use_fish:
            score += fish.loc[day].fillna(0)
            tradable &= uptrend.loc[day]
        if use_insect:
            score += insect.loc[day].fillna(0)
            tradable &= ~(reaction.loc[day] < -0.10)        # skip names whose last report was sold >10%
        picks = score[tradable].nlargest(top).index if (use_fish or use_insect) else score[tradable].index
        if len(picks):
            weights.loc[day, picks] = (exposure.loc[day] if use_bird else 1.0) / max(len(picks), top if (use_fish or use_insect) else 1)
    return weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--cost", type=float, default=0.003, help="cost per side (commission + spread)")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()

    symbols = [u[0] for u in UNIVERSE if u[1] == "security" and u[2] in ("pure", "mixed")]
    bars = load_bars(symbols + BENCH)
    close, income = bars["close"], load_income(symbols)
    start = close.index[WARMUP]
    print(f"Universe: {len(symbols)} names   Period: {start.date()} -> {close.index[-1].date()}"
          f"   top {args.top}, cost {args.cost:.2%}/side\n")

    variants = {
        "all security, equal weight": dict(use_bird=False, use_fish=False, use_insect=False),
        "bird only (EW + regime)": dict(use_bird=True, use_fish=False, use_insect=False),
        "fish only": dict(use_bird=False, use_fish=True, use_insect=False),
        "insect only": dict(use_bird=False, use_fish=False, use_insect=True),
        "fish + insect": dict(use_bird=False, use_fish=True, use_insect=True),
        "bird + fish + insect": dict(use_bird=True, use_fish=True, use_insect=True),
    }
    rows, curves = {}, {}
    for name, flags in variants.items():
        equity, turnover = run(bars, build_weights(close, income, symbols, args.top, **flags), args.cost)
        curves[name] = equity[start:]
        rows[name] = stats(curves[name], turnover)
    for b in ("CIBR", "QQQ"):
        curves[b] = close[b][start:] / close[b][start]
        rows[f"{b} buy & hold"] = stats(curves[b])
    pd.set_option("display.width", 200, "display.float_format", "{:.2f}".format)
    print(pd.DataFrame(rows).T.to_string(), "\n")

    yearly = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda s: (s.iloc[-1] / s.iloc[0] - 1) * 100) for k, v in curves.items()})
    print("Return by calendar year (%)"); print(yearly.T.to_string(), "\n")

    full = build_weights(close, income, symbols, args.top)
    print(f"Average capital deployed: {full.sum(axis=1).mean():.0%}   weeks fully in cash: {(full.sum(axis=1) == 0).mean():.0%}")
    print("Current picks:", ", ".join(f"{s} {w:.0%}" for s, w in full.iloc[-1][full.iloc[-1] > 0].items()) or "none (cash)",
          f"  exposure {bird_exposure(close).iloc[-1]:.0%}")
    print("Most held:", ", ".join(f"{s} {v:.0%}" for s, v in (full > 0).mean().nlargest(8).items()))

    if args.sensitivity:
        print("\nSensitivity of bird + fish + insect (Sharpe / CAGR%)")
        for top in (3, 5, 8):
            for cost in (0.001, 0.003, 0.006):
                eq, _ = run(bars, build_weights(close, income, symbols, top), cost)
                s = stats(eq[start:])
                print(f"  top {top}  cost {cost:.1%}: Sharpe {s['Sharpe']:.2f}  CAGR {s['CAGR%']:.1f}%  MaxDD {s['MaxDD%']:.1f}%")


if __name__ == "__main__":
    main()
