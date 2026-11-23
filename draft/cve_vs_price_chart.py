"""CVE publications per day (monthly) above the share prices of the two core names and the sector ETF.

Two panels on one time axis, not one chart with two scales: the measures are different things.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
from webull.data.data_client import DataClient

from _client import make_client
from plan_live import fresh_bars

HERE = os.path.dirname(os.path.abspath(__file__))
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams["font.family"] = "IPAGothic"
SURFACE, INK, MUTED, GRID, BAR = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#c9c8c2"
SERIES = {"QLYS": "#2a78d6", "TENB": "#eb6834", "CIBR": "#1baf7a"}
NAMES = {"QLYS": "QLYS", "TENB": "TENB", "CIBR": "セキュリティETF（CIBR）"}
START = "2025-01-01"

m = pd.read_csv(os.path.join(HERE, "cve_monthly.csv"), index_col="month")
m["per_day"] = m.total / m.through
daily = pd.read_csv(os.path.join(HERE, "cve_daily.csv"), parse_dates=["date"]).set_index("date").iloc[:-2]
cur = daily[daily.index >= daily.index[-1].replace(day=1)]
m.loc[cur.index[-1].strftime("%Y-%m"), "per_day"] = cur.total.mean()
m = m[m.index >= START[:7]]
mid = pd.to_datetime(m.index + "-15")

close = fresh_bars(DataClient(make_client()), list(SERIES), count=600)["close"]
close = close[close.index >= START]
idx = close / close.iloc[0] * 100

fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7.4), dpi=200, facecolor=SURFACE, sharex=True, gridspec_kw={"height_ratios": [1, 1.25], "hspace": 0.28})
for ax in (a1, a2):
    ax.set_facecolor(SURFACE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)

a1.bar(mid, m.per_day, width=22, color=BAR, linewidth=0)
for i in (0, 12, len(m) - 2, len(m) - 1):
    a1.text(mid[i], m.per_day.iloc[i] + 12, f"{m.per_day.iloc[i]:,.0f}", ha="center", color=INK, fontsize=9)
a1.set_ylim(0, m.per_day.max() * 1.18)
a1.set_title("脆弱性の公開件数（1日あたり、月平均）", loc="left", color=INK, fontsize=11, pad=6)

for s, c in SERIES.items():
    a2.plot(idx.index, idx[s], color=c, linewidth=2, solid_capstyle="round")
ends = sorted(SERIES, key=lambda s: idx[s].iloc[-1])
ypos = [idx[s].iloc[-1] for s in ends]
for i in range(1, len(ypos)):                                       # keep the end labels apart
    ypos[i] = max(ypos[i], ypos[i - 1] + 9)
for s, y in zip(ends, ypos):
    a2.scatter([idx.index[-1]], [idx[s].iloc[-1]], s=36, color=SERIES[s], zorder=3, edgecolor=SURFACE, linewidth=1.5)
    a2.text(idx.index[-1] + pd.Timedelta(days=8), y, f"{s}  {idx[s].iloc[-1]:.0f}", va="center", color=INK, fontsize=9.5)
a2.axhline(100, color=MUTED, linewidth=0.8, linestyle=(0, (2, 3)))
a2.set_title("株価（2025年1月の最初の取引日を100とした指数）", loc="left", color=INK, fontsize=11, pad=6)
a2.set_xlim(pd.Timestamp(START) - pd.Timedelta(days=5), idx.index[-1] + pd.Timedelta(days=95))
a2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y年%-m月"))
handles = [plt.Line2D([0], [0], color=c, linewidth=2) for c in SERIES.values()]
a2.legend(handles, [NAMES[s] for s in SERIES], loc="upper left", frameon=False, fontsize=9, labelcolor=MUTED, ncol=3)
r = m.per_day.iloc[-2] / m.per_day.iloc[0]
lo, hi = idx.iloc[-1].min() - 100, idx.iloc[-1].max() - 100
fig.suptitle(f"件数は2025年1月の約{r:.0f}倍、株価は同じ期間で +{lo:.0f}〜+{hi:.0f}%", x=0.045, y=0.985, ha="left", color=INK, fontsize=13.5)
fig.text(0.045, 0.945, f"件数は NVD 公開日ベース（最後の月は{cur.index[-1]:%-m月%-d日}まで）。株価は終値、{idx.index[-1]:%-m月%-d日}まで", color=MUTED, fontsize=9)
fig.subplots_adjust(left=0.06, right=0.985, top=0.885, bottom=0.06)
out = os.path.join(HERE, "charts", "cve_vs_price.png")
fig.savefig(out, facecolor=SURFACE)
lowd = idx.loc["2026-01-01":].idxmin(); print("2026 low", {k: (str(lowd[k].date()), round(idx[k].min()), round((idx[k].iloc[-1] / idx.loc[lowd[k], k] - 1) * 100)) for k in idx})
print(out); print(idx.iloc[-1].round(0).to_dict(), idx.index[0].date(), idx.index[-1].date()); print(idx.resample("QE").last().round(0).to_string())
