"""Chart the daily CVE publications with a 7-day moving average (reads draft/cve_daily.csv)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams["font.family"] = "IPAGothic"
SURFACE, INK, MUTED, GRID, BAR, LINE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#c9c8c2", "#2a78d6"

d = pd.read_csv(os.path.join(HERE, "cve_daily.csv"), parse_dates=["date"]).set_index("date")
d = d.iloc[:-2]                                    # the last two days are still filling in
ma = d.total.rolling(7).mean()

fig, ax = plt.subplots(figsize=(11, 5.2), dpi=200, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
ax.bar(d.index, d.total, width=0.8, color=BAR, linewidth=0, label="1日の件数")
ax.plot(ma.index, ma, color=LINE, linewidth=2, solid_capstyle="round", label="7日移動平均")
ax.scatter([ma.index[-1]], [ma.iloc[-1]], s=40, color=LINE, zorder=3, edgecolor=SURFACE, linewidth=1.5)
ax.annotate(f"{ma.iloc[-1]:,.0f}件/日", (ma.index[-1], ma.iloc[-1]), xytext=(8, 0), textcoords="offset points",
            va="center", color=INK, fontsize=10)
first = ma.dropna()
ax.annotate(f"{first.iloc[0]:,.0f}件/日", (first.index[0], first.iloc[0]), xytext=(0, 10), textcoords="offset points",
            ha="center", color=INK, fontsize=10)
for day, name in (("2026-10-13", "マイクロソフト月例"), ("2026-10-20", "オラクル定例"), ("2026-11-10", "マイクロソフト月例")):
    ts = pd.Timestamp(day)
    if ts in d.index:
        ax.annotate(name, (ts, d.total[ts]), xytext=(0, 4), textcoords="offset points", ha="center", color=MUTED, fontsize=8)
ax.set_ylim(0, d.total.max() * 1.1)
ax.set_xlim(d.index[0] - pd.Timedelta(days=1), d.index[-1] + pd.Timedelta(days=9))
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(colors=MUTED, length=0, labelsize=9)
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.set_title("脆弱性（CVE）の公開件数：7日移動平均は8月上旬の約300件から約660件へ", loc="left", color=INK, fontsize=13, pad=14)
ax.text(0, 1.015, f"NVD 公開日ベース、{d.index[0]:%Y年%-m月%-d日}〜{d.index[-1]:%-m月%-d日}。直近2日は登録の遅れがあるため除外",
        transform=ax.transAxes, color=MUTED, fontsize=9)
ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=MUTED, bbox_to_anchor=(0, 0.97))
fig.tight_layout()
out = os.path.join(HERE, "charts", "cve_daily_ma7.png")
fig.savefig(out, facecolor=SURFACE)
m = ma.dropna()
print(out); print("ma first", round(m.iloc[0]), "last", round(m.iloc[-1]), "min", round(m.min()), m.idxmin().date(), "max", round(m.max()), m.idxmax().date())
print(m.resample("W-SUN").last().round(0).to_string())
print("top days", d.total.nlargest(8).to_dict())
