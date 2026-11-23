"""CVE publications and the two core share prices in 2026, each with one-week and one-month moving averages.

Three panels on one time axis. In every panel the same colour means the same thing:
grey = the daily value, blue = one-week average, orange = one-month average.
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
SURFACE, INK, MUTED, GRID, RAW, WEEK, MONTH = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#c9c8c2", "#2a78d6", "#eb6834"
START = pd.Timestamp("2026-01-01")

cve = pd.read_csv(os.path.join(HERE, "cve_daily.csv"), parse_dates=["date"]).set_index("date").total.iloc[:-2]
close = fresh_bars(DataClient(make_client()), ["QLYS", "TENB"], count=600)["close"]

fig, axes = plt.subplots(3, 1, figsize=(11, 9.6), dpi=200, facecolor=SURFACE, sharex=True, gridspec_kw={"hspace": 0.3})
for ax in axes:
    ax.set_facecolor(SURFACE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)


def end_labels(ax, pairs, fmt, gap):
    pairs = sorted(pairs, key=lambda p: p[1].iloc[-1])
    ys = [p[1].iloc[-1] for p in pairs]
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + gap)
    for (name, s, c), y in zip(pairs, ys):
        ax.scatter([s.index[-1]], [s.iloc[-1]], s=30, color=c, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        ax.text(s.index[-1] + pd.Timedelta(days=5), y, f"{name}  {fmt(s.iloc[-1])}", va="center", color=INK, fontsize=9)


w, m = cve.rolling(7).mean(), cve.rolling(28).mean()
ax = axes[0]
ax.bar(cve[START:].index, cve[START:].clip(upper=1500), width=0.8, color=RAW, linewidth=0)
ax.plot(w[START:].index, w[START:], color=WEEK, linewidth=2)
ax.plot(m[START:].index, m[START:], color=MONTH, linewidth=2)
ax.set_ylim(0, 1500)
end_labels(ax, [("1週間", w, WEEK), ("1か月", m, MONTH)], lambda v: f"{v:,.0f}件", 130)
ax.set_title("脆弱性の公開件数（1日あたり）。棒は1,500件で打ち切り", loc="left", color=INK, fontsize=11, pad=6)

stats = {}
for ax, sym in zip(axes[1:], ("QLYS", "TENB")):
    c = close[sym].dropna()
    w, m = c.rolling(5).mean(), c.rolling(21).mean()
    ax.plot(c[START:].index, c[START:], color=RAW, linewidth=1.2)
    ax.plot(w[START:].index, w[START:], color=WEEK, linewidth=2)
    ax.plot(m[START:].index, m[START:], color=MONTH, linewidth=2)
    span = c[START:].max() - c[START:].min()
    end_labels(ax, [("終値", c, MUTED), ("1週間", w, WEEK), ("1か月", m, MONTH)], lambda v: f"{v:,.1f}ドル", span * 0.075)
    ax.set_title(f"{sym} の株価（ドル）", loc="left", color=INK, fontsize=11, pad=6)
    hi = c[START:]
    stats[sym] = dict(close=c.iloc[-1], w=w.iloc[-1], m=m.iloc[-1], vs_m=(c.iloc[-1] / m.iloc[-1] - 1) * 100, w_vs_m=(w.iloc[-1] / m.iloc[-1] - 1) * 100,
                      high=hi.max(), high_day=str(hi.idxmax().date()), from_high=(c.iloc[-1] / hi.max() - 1) * 100, low=hi.min(), low_day=str(hi.idxmin().date()),
                      m_slope_20d=(m.iloc[-1] / m.iloc[-21] - 1) * 100)

axes[-1].set_xlim(START - pd.Timedelta(days=4), close.index[-1] + pd.Timedelta(days=42))
axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
handles = [plt.Line2D([0], [0], color=RAW, linewidth=4), plt.Line2D([0], [0], color=WEEK, linewidth=2), plt.Line2D([0], [0], color=MONTH, linewidth=2)]
fig.legend(handles, ["日々の値", "1週間の移動平均", "1か月の移動平均"], loc="upper left", bbox_to_anchor=(0.04, 0.945), frameon=False, fontsize=9.5, labelcolor=MUTED, ncol=3)
fig.suptitle("件数の1か月平均は11月に頭打ち、株価は1か月平均を約7%下回っている", x=0.045, y=0.985, ha="left", color=INK, fontsize=13.5)
fig.text(0.045, 0.953, f"2026年。件数は NVD 公開日ベース（{cve.index[-1]:%-m月%-d日}まで、7日と28日の平均）。株価は終値（{close.index[-1]:%-m月%-d日}まで、5営業日と21営業日の平均）", color=MUTED, fontsize=8.5)
fig.subplots_adjust(left=0.06, right=0.985, top=0.885, bottom=0.045)
out = os.path.join(HERE, "charts", "cve_vs_price_ma.png")
fig.savefig(out, facecolor=SURFACE)
print(out)
print(pd.DataFrame(stats).round(1).to_string())
cw, cm = cve.rolling(7).mean(), cve.rolling(28).mean()
print("cve 7d", round(cw.iloc[-1]), "28d", round(cm.iloc[-1]), "28d 4w ago", round(cm.iloc[-29]), "28d max", round(cm.max()), cm.idxmax().date())
print(cm.resample("MS").last().round(0).to_dict())
