"""A century of industry returns: what held up when software fell, and when the Fed was raising rates?

Uses Kenneth French's 49 industry portfolios (monthly, value-weighted, since 1926; software since 1965) and the
one-month Treasury bill return from his factor file. "Softw" stands in for the security names: there is no
security industry in the data, and security stocks trade as software.

  1  every fall of 25% or more in software: the return of each defensive industry from the peak to the trough
  2  the months in which software did worst
  3  the twelve months after software had a very strong year (the closest thing here to "the core is rich")
  4  each Fed rate-raising cycle

Usage: python draft/diversify_longrun.py
"""
import io
import os
import re
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "cache", "ff")
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ind49.zip": "49_Industry_Portfolios_CSV.zip", "ff3.zip": "F-F_Research_Data_Factors_CSV.zip"}
SHOW = {"Softw": "software", "Guns": "defense", "Aero": "aircraft", "Food": "food", "Soda": "soft drinks", "Smoke": "tobacco", "Hshld": "household goods",
        "Drugs": "drugs", "MedEq": "medical equipment", "Insur": "insurance", "Util": "utilities", "Rtail": "retail", "Meals": "restaurants",
        "Oil": "oil", "Gold": "gold miners", "Chips": "chips", "Banks": "banks"}
HIKES = {"1972-02..1973-08": ("1972-02", "1973-08"), "1977-01..1980-03": ("1977-01", "1980-03"), "1983-05..1984-08": ("1983-05", "1984-08"),
         "1987-01..1989-05": ("1987-01", "1989-05"), "1994-02..1995-02": ("1994-02", "1995-02"), "1999-06..2000-05": ("1999-06", "2000-05"),
         "2004-06..2006-06": ("2004-06", "2006-06"), "2015-12..2018-12": ("2015-12", "2018-12"), "2022-03..2023-07": ("2022-03", "2023-07")}


def table(name, marker):
    """The first monthly table in one of French's CSV files (value-weighted returns), as fractions."""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, name)
    if not os.path.exists(path):
        body = urllib.request.urlopen(urllib.request.Request(BASE + FILES[name], headers={"User-Agent": "Mozilla/5.0 (research script)"}), timeout=60).read()
        open(path, "wb").write(body)
    z = zipfile.ZipFile(path)
    lines = z.read(z.namelist()[0]).decode("latin1").splitlines()
    start = next(i for i, line in enumerate(lines) if marker in line)
    cols, rows = [c.strip() for c in lines[start].split(",")][1:], []
    for line in lines[start + 1:]:
        parts = [c.strip() for c in line.split(",")]
        if not re.fullmatch(r"\d{6}", parts[0]):
            break
        rows.append(parts)
    t = pd.DataFrame(rows, columns=["month"] + cols)
    t.index = pd.PeriodIndex(t.month, freq="M")
    t = t[cols].astype(float) / 100
    return t.where(t > -0.99)                                       # -99.99 marks "no data"


def total(frame, a, b):
    return ((1 + frame.loc[a:b]).prod() - 1) * 100


def main():
    ind, fac = table("ind49.zip", "Agric"), table("ff3.zip", "Mkt-RF")
    d = ind[list(SHOW)].rename(columns=SHOW)
    d["T-bills"], d["market"] = fac.RF, fac["Mkt-RF"] + fac.RF
    d = d.loc[d.software.first_valid_index():]
    cols = [c for c in d.columns if c != "software"]
    pd.set_option("display.width", 260, "display.float_format", "{:+.0f}".format)
    print(f"software has data from {d.index[0]} to {d.index[-1]}\n")

    # 1. every fall of 25% or more in software, from the month after the peak to the trough. A fall ends once
    #    software has risen 25% off its low; the next peak is counted from there. The first ten years hold only a
    #    handful of small companies, so the count starts in 1975.
    wealth = (1 + d.software.loc["1975":]).cumprod()
    falls, values = [], wealth.values
    peak_i, low_i, falling = 0, 0, False
    for i in range(1, len(values)):
        if not falling:
            if values[i] > values[peak_i]:
                peak_i = i
            elif values[i] / values[peak_i] - 1 <= -0.25:
                falling, low_i = True, i
        elif values[i] < values[low_i]:
            low_i = i
        elif values[i] / values[low_i] - 1 >= 0.25:
            falls.append((wealth.index[peak_i + 1], wealth.index[low_i]))
            falling, peak_i = False, i
    if falling:
        falls.append((wealth.index[peak_i + 1], wealth.index[low_i]))
    rows = {f"{a}..{b}": total(d, a, b) for a, b in falls}
    t1 = pd.DataFrame(rows).T
    print("--- 1. falls of 25% or more in software: total return over the same months (%)")
    print(t1.to_string())
    up = (t1[cols] > 0).mean() * 100
    print("\n   share of these falls in which each one rose:", "  ".join(f"{c} {v:.0f}%" for c, v in up.sort_values(ascending=False).items()))
    print("   average over the falls:", "  ".join(f"{c} {v:+.0f}" for c, v in t1[cols].mean().sort_values(ascending=False).items()))

    # 2. the worst 10% of months for software
    bad = d.software <= d.software.quantile(0.10)
    pd.set_option("display.float_format", "{:+.1f}".format)
    print(f"\n--- 2. the worst 10% of months for software ({bad.sum()} months, software {d.software[bad].mean() * 100:+.1f}% on average): average return that month (%)")
    print("  ".join(f"{c} {v * 100:+.1f}" for c, v in d.loc[bad, cols].mean().sort_values(ascending=False).items()))
    print("   correlation with software, all months:", "  ".join(f"{c} {v:.2f}" for c, v in d[cols].corrwith(d.software).sort_values().items()))

    # 3. after a very strong year for software
    past = (1 + d.software).rolling(12).apply(np.prod, raw=True) - 1
    ahead = pd.DataFrame({c: ((1 + d[c]).rolling(12).apply(np.prod, raw=True) - 1).shift(-12) for c in d.columns}) * 100
    hot = past >= past.quantile(0.90)
    rows = {"after software's best 10% of years": ahead[hot].mean(), "after any month": ahead.mean(),
            "share of cases with a loss, after the best years": (ahead[hot].dropna() < 0).mean() * 100, "share with a loss, any month": (ahead.dropna() < 0).mean() * 100}
    print(f"\n--- 3. the next twelve months (%), after software gained {past.quantile(0.90) * 100:.0f}% or more in a year ({hot.sum()} months, in {int((hot & ~hot.shift(1, fill_value=False)).sum())} separate runs)")
    print(pd.DataFrame(rows).T[["software"] + cols].to_string())

    # 4. rate-raising cycles
    pd.set_option("display.float_format", "{:+.0f}".format)
    t4 = pd.DataFrame({k: total(d, a, b) for k, (a, b) in HIKES.items()}).T
    print("\n--- 4. Fed rate-raising cycles (first to last increase): total return (%)")
    print(t4.to_string())
    print("   share of cycles in which each one beat Treasury bills:", "  ".join(f"{c} {v:.0f}%" for c, v in (t4.gt(t4["T-bills"], axis=0).mean() * 100).drop("T-bills").sort_values(ascending=False).items()))
    for name, t in (("falls", t1), ("hikes", t4)):
        t.to_csv(os.path.join(HERE, "cache", f"div_longrun_{name}.csv"))


if __name__ == "__main__":
    main()
