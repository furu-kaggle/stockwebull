"""Chart CVE publications per day by month since January 2025 (reads cve_monthly.csv and cve_daily.csv)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams["font.family"] = "IPAGothic"
SURFACE, INK, MUTED, GRID, LAST, THIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#c9c8c2", "#2a78d6"

m = pd.read_csv(os.path.join(HERE, "cve_monthly.csv"), index_col="month")
m["per_day"] = m.total / m.through
daily = pd.read_csv(os.path.join(HERE, "cve_daily.csv"), parse_dates=["date"]).set_index("date").iloc[:-2]
cur = daily[daily.index >= daily.index[-1].replace(day=1)]          # the month in progress, from the daily file
m.loc[cur.index[-1].strftime("%Y-%m"), ["total", "through", "per_day"]] = [cur.total.sum(), len(cur), cur.total.mean()]
m = m[m.index >= "2025-01"]

fig, ax = plt.subplots(figsize=(11, 5.2), dpi=200, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
x = range(len(m))
colors = [LAST if k.startswith("2025") else THIS for k in m.index]
bars = ax.bar(x, m.per_day, width=0.72, color=colors, linewidth=0)
bars[-1].set_alpha(0.55)                                              # the month in progress
for i, (k, v) in enumerate(m.per_day.items()):
    if k in ("2025-01", "2025-12", "2026-01", "2026-06") or i >= len(m) - 4:
        ax.text(i, v + 8, f"{v:,.0f}", ha="center", va="bottom", color=INK, fontsize=9)
ax.set_xticks(list(x))
ax.set_xticklabels([f"{int(k[5:])}月" for k in m.index], fontsize=8.5)
for year, first in (("2025年", 0), ("2026年", 12)):
    ax.text(first - 0.4, -0.115, year, transform=ax.get_xaxis_transform(), color=MUTED, fontsize=9.5, ha="left")
ax.set_ylim(0, m.per_day.max() * 1.13)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(colors=MUTED, length=0, labelsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ratio = m.per_day["2026-10"] / m.per_day["2025-10"]
ax.set_title(f"脆弱性（CVE）の1日あたり公開件数：2025年は横ばい、2026年10月は前年の約{ratio:.0f}倍", loc="left", color=INK, fontsize=13, pad=18)
ax.text(0, 1.02, f"NVD 公開日ベースの月平均。薄い棒は途中の月（{cur.index[-1]:%-m月%-d日}まで）", transform=ax.transAxes, color=MUTED, fontsize=9)
handles = [plt.Rectangle((0, 0), 1, 1, color=LAST), plt.Rectangle((0, 0), 1, 1, color=THIS)]
ax.legend(handles, ["2025年", "2026年"], loc="upper left", frameon=False, fontsize=9, labelcolor=MUTED, bbox_to_anchor=(0, 0.97))
fig.tight_layout()
out = os.path.join(HERE, "charts", "cve_per_day_by_month.png")
fig.savefig(out, facecolor=SURFACE)
print(out)
print(m[["total", "through", "per_day"]].round(0).to_string())
