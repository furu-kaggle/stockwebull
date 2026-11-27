"""Average daily move of the security ETF and the core pair, grouped by how the Nasdaq-100 ETF moved that day."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams["font.family"] = "IPAGothic"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
COL = {"QQQ": "#2a78d6", "CIBR": "#eb6834", "core": "#1baf7a"}
NAME = {"QQQ": "ナスダック100（QQQ）", "CIBR": "セキュリティETF（CIBR）", "core": "QLYS・TENB の平均"}

r = pd.read_csv(os.path.join(HERE, "cache", "etf_vs_nasdaq.csv"), index_col=0, parse_dates=True)
q = r.QQQ
groups = [("2%以上の下げ", q <= -0.02), ("1〜2%の下げ", (q <= -0.01) & (q > -0.02)), ("1%未満の下げ", (q < 0) & (q > -0.01)),
          ("1%未満の上げ", (q > 0) & (q < 0.01)), ("1〜2%の上げ", (q >= 0.01) & (q < 0.02)), ("2%以上の上げ", q >= 0.02)]
t = pd.DataFrame({g: r[m].mean() * 100 for g, m in groups}).T
n = [int(m.sum()) for _, m in groups]

fig, ax = plt.subplots(figsize=(11, 5.4), dpi=200, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
w = 0.26
for i, k in enumerate(COL):
    xs = [j + (i - 1) * (w + 0.015) for j in range(len(t))]
    ax.bar(xs, t[k], width=w, color=COL[k], linewidth=0, label=NAME[k])
    for x, v in zip(xs, t[k]):
        ax.text(x, v + (0.08 if v >= 0 else -0.08), f"{v:+.1f}", ha="center", va="bottom" if v >= 0 else "top", color=INK, fontsize=8)
ax.axhline(0, color=MUTED, linewidth=0.8)
ax.set_xticks(range(len(t)))
ax.set_xticklabels([f"{g}\n（{k}日）" for (g, _), k in zip(groups, n)], fontsize=9)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left", "bottom"):
    ax.spines[side].set_visible(False)
ax.tick_params(colors=MUTED, length=0, labelsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
ax.set_ylim(t.values.min() - 0.6, t.values.max() + 0.6)
ax.set_title("ナスダックが動いた日の平均の騰落：上げにはほぼ付いていき、下げは浅い", loc="left", color=INK, fontsize=13, pad=18)
ax.text(0, 1.02, f"ナスダック100 のETFの1日の騰落で分けた平均。直近250営業日（{r.index[0]:%Y年%-m月%-d日}〜{r.index[-1]:%-m月%-d日}）", transform=ax.transAxes, color=MUTED, fontsize=9)
ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=MUTED, bbox_to_anchor=(0, 0.97))
fig.tight_layout()
out = os.path.join(HERE, "charts", "etf_vs_nasdaq.png")
fig.savefig(out, facecolor=SURFACE)
print(out)
