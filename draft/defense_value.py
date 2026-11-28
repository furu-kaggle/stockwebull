"""Are the US defense contractors cheap? Two checks.

  1  Each company's price against its own trailing-twelve-month earnings and sales, compared with where
     those multiples stood over the last ten years (SEC filings for the figures, Yahoo for prices), plus
     cash left after capital spending (Webull's cash-flow statements) and the dividend.
  2  What followed earlier times when one of them fell 25% or more below its one-year high: the return over
     the next one and three years, against the S&P 500 over the same days. And the same for the defense
     industry as a whole since 1963 (Kenneth French's "Guns" industry, monthly).

Usage: python draft/defense_value.py
"""
import os

import numpy as np
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from diversify_longrun import table
from indicator_compare import as_of
from long_history import earnings_per_share, prices, sales_per_share

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"NOC": "Northrop Grumman", "LMT": "Lockheed Martin", "GD": "General Dynamics", "RTX": "RTX", "LHX": "L3Harris", "HII": "Huntington Ingalls"}


def cash_yield(data, sym, price):
    """Cash from operations minus capital spending over the last four quarters, per dollar of market value."""
    try:
        cf = pd.DataFrame(data.fundamentals.get_financials_cashflow(sym, type="QUARTERLY", count=8).json()).sort_values("end_date").tail(4)
        inc = pd.DataFrame(data.fundamentals.get_financials_income(sym, type="QUARTERLY", count=2).json()).sort_values("end_date")
        free = pd.to_numeric(cf.cfo).sum() + pd.to_numeric(cf.capex).sum()
        paid = -pd.to_numeric(cf.total_cash_dividends_paid).sum() - pd.to_numeric(cf.net_stock_iss_ret).sum()
        cap = price * float(inc.diluted_avg_shares.iloc[-1])
        return free / cap * 100, paid / cap * 100
    except Exception:
        return np.nan, np.nan


def multiples(data):
    p = prices(list(NAMES) + ["SPY"], refresh=True)
    rows = {}
    for sym in NAMES:
        px = p["close"][sym].dropna()
        pe = (px / as_of(earnings_per_share(sym), px.index)).where(lambda v: v > 0)
        ps = px / as_of(sales_per_share(sym), px.index)
        ten = slice(px.index[-1] - pd.DateOffset(years=10), None)
        adj = p["adj"][sym].dropna()
        year = px.index[-1] - pd.DateOffset(years=1)
        free, paid = cash_yield(data, sym, px.iloc[-1])
        eps = earnings_per_share(sym)
        since = pe.loc["2011":].dropna()                                # as far back as the filings data goes for all six
        rows[sym] = dict(price=px.iloc[-1], pe=pe.iloc[-1], pe_at_1y_high=pe.loc[px.loc[year:].idxmax()], pe_place_since_2011=(since <= pe.iloc[-1]).mean() * 100,
                         eps_growth=(eps.iloc[-1] / eps[eps.index <= eps.index[-1] - pd.Timedelta(days=330)].iloc[-1] - 1) * 100,
                         price_at_low_band=pe[ten].quantile(0.05) * eps.iloc[-1],
                         pe_median_10y=pe[ten].median(), pe_place_10y=(pe[ten].dropna() <= pe.iloc[-1]).mean() * 100,
                         pe_low_10y=pe[ten].quantile(0.05), pe_high_10y=pe[ten].quantile(0.95),
                         ps=ps.iloc[-1], ps_median_10y=ps[ten].median(), ps_place_10y=(ps[ten].dropna() <= ps.iloc[-1]).mean() * 100,
                         cash_yield=free, paid_out=paid, dividend=((adj.iloc[-1] / adj.loc[year:].iloc[0]) / (px.iloc[-1] / px.loc[year:].iloc[0]) - 1) * 100,
                         ret_1y=(adj.iloc[-1] / adj.loc[year:].iloc[0] - 1) * 100, ret_3y=(adj.iloc[-1] / adj.loc[px.index[-1] - pd.DateOffset(years=3):].iloc[0] - 1) * 100,
                         from_high=(px.iloc[-1] / px.loc[year:].max() - 1) * 100)
    spy = p["adj"]["SPY"].dropna()
    print(f"prices to {p['close'].index[-1].date()}; S&P 500 over one year {(spy.iloc[-1] / spy.loc[spy.index[-1] - pd.DateOffset(years=1):].iloc[0] - 1) * 100:+.1f}%, "
          f"three years {(spy.iloc[-1] / spy.loc[spy.index[-1] - pd.DateOffset(years=3):].iloc[0] - 1) * 100:+.1f}%\n")
    return pd.DataFrame(rows).T, p


def after_falls(adj, symbols, fall=-0.25):
    """Each first day a stock stood 25% or more below its one-year high (at most one per 250 days), and what followed."""
    rows = []
    for sym in symbols:
        px = adj[sym].dropna()
        down = px / px.rolling(252, min_periods=200).max() - 1
        last = -10_000
        for i in np.flatnonzero((down <= fall).values):
            if i - last < 250:
                continue
            last = i
            row = dict(stock=sym, day=px.index[i].date(), fall=down.iloc[i] * 100)
            for label, n in (("1y", 250), ("3y", 750)):
                if i + n < len(px):
                    j = px.index[i + n]
                    row[label] = (px.iloc[i + n] / px.iloc[i] - 1) * 100
                    row[f"{label}_vs_spy"] = row[label] - (adj["SPY"].asof(j) / adj["SPY"].asof(px.index[i]) - 1) * 100
            rows.append(row)
    return pd.DataFrame(rows)


def industry():
    """The defense industry as a whole, monthly since 1963: the 12 and 36 months after it stood 25% below its one-year high."""
    ind, fac = table("ind49.zip", "Agric"), table("ff3.zip", "Mkt-RF")
    guns, market = ind["Guns"].dropna(), (fac["Mkt-RF"] + fac.RF)
    wealth, m = (1 + guns).cumprod(), (1 + market.reindex(guns.index)).cumprod()
    down = wealth / wealth.rolling(12, min_periods=6).max() - 1
    rows, last = [], -100
    for i in np.flatnonzero((down <= -0.25).values):
        if i - last < 12:
            continue
        last = i
        row = dict(month=str(wealth.index[i]), fall=down.iloc[i] * 100)
        for label, n in (("1y", 12), ("3y", 36)):
            if i + n < len(wealth):
                row[label] = (wealth.iloc[i + n] / wealth.iloc[i] - 1) * 100
                row[f"{label}_vs_market"] = row[label] - (m.iloc[i + n] / m.iloc[i] - 1) * 100
        rows.append(row)
    usual = {"1y": ((wealth.shift(-12) / wealth - 1) * 100).mean(), "3y": ((wealth.shift(-36) / wealth - 1) * 100).mean()}
    return pd.DataFrame(rows), usual


def main():
    data = DataClient(make_client())
    t, p = multiples(data)
    pd.set_option("display.width", 250, "display.float_format", "{:.1f}".format)
    print("--- 1. multiples today against each company's own last ten years")
    print(t.to_string())
    t.to_csv(os.path.join(HERE, "cache", "defense_value.csv"))

    falls = after_falls(p["adj"], list(NAMES))
    pd.set_option("display.float_format", "{:+.0f}".format)
    print("\n--- 2. each time one of them first stood 25% or more below its one-year high (dividends included)")
    print(falls.to_string(index=False))
    done = falls.dropna(subset=["1y"])
    print(f"\n   after such a fall, {len(done)} cases: next year {done['1y'].mean():+.0f}% on average (median {done['1y'].median():+.0f}%), up in {(done['1y'] > 0).mean() * 100:.0f}%, "
          f"ahead of the S&P 500 in {(done['1y_vs_spy'].dropna() > 0).mean() * 100:.0f}% of the {done['1y_vs_spy'].notna().sum()} cases since 1993 (average gap {done['1y_vs_spy'].mean():+.0f})")
    done3 = falls.dropna(subset=["3y"])
    print(f"   {len(done3)} cases with three years of data: {done3['3y'].mean():+.0f}% on average (median {done3['3y'].median():+.0f}%), up in {(done3['3y'] > 0).mean() * 100:.0f}%, "
          f"ahead of the S&P 500 in {(done3['3y_vs_spy'].dropna() > 0).mean() * 100:.0f}% of the {done3['3y_vs_spy'].notna().sum()} cases since 1993 (average gap {done3['3y_vs_spy'].mean():+.0f})")
    recent = falls[pd.to_datetime(falls.day) >= "1993-02-01"]
    r1, r3 = recent.dropna(subset=["1y"]), recent.dropna(subset=["3y"])
    print(f"   since 1993 only: next year {r1['1y'].mean():+.0f}% (median {r1['1y'].median():+.0f}%, up in {(r1['1y'] > 0).mean() * 100:.0f}% of {len(r1)}); "
          f"three years {r3['3y'].mean():+.0f}% (median {r3['3y'].median():+.0f}%, up in {(r3['3y'] > 0).mean() * 100:.0f}% of {len(r3)})")
    usual = {n: np.mean([((p["adj"][s].shift(-d) / p["adj"][s] - 1) * 100).mean() for s in NAMES]) for n, d in (("1y", 250), ("3y", 750))}
    print(f"   for comparison, any day: next year {usual['1y']:+.0f}%, three years {usual['3y']:+.0f}%")
    falls.to_csv(os.path.join(HERE, "cache", "defense_falls.csv"), index=False)

    g, usual = industry()
    print("\n--- 3. the defense industry as a whole (monthly since 1963), each time it stood 25% below its one-year high")
    print(g.to_string(index=False))
    d1, d3 = g.dropna(subset=["1y"]), g.dropna(subset=["3y"])
    print(f"\n   next 12 months {d1['1y'].mean():+.0f}% on average (up in {(d1['1y'] > 0).mean() * 100:.0f}%, ahead of the market in {(d1['1y_vs_market'] > 0).mean() * 100:.0f}%); "
          f"next 36 months {d3['3y'].mean():+.0f}% (up in {(d3['3y'] > 0).mean() * 100:.0f}%, ahead of the market in {(d3['3y_vs_market'] > 0).mean() * 100:.0f}%)")
    print(f"   for comparison, any month: next 12 months {usual['1y']:+.0f}%, next 36 months {usual['3y']:+.0f}%")


if __name__ == "__main__":
    main()
