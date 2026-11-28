"""Build the HTML report of the diversification research (draft/research/diversification_report.html).

Figures come from the result files the research scripts leave in draft/cache where they exist; the few that
were only printed (this week's review, the basket windows, Monday's preview) are written here with the script
that produced them named beside each.

Usage: python draft/report_diversification.py
"""
import html
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "research", "diversification_report.html")

CSS = """
/* layout: one reading column; conclusions and decisions first, evidence after; charts are bar lists drawn to one scale each */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #171a1f; --muted: #5d6470; --line: #dde1e7;
  --accent: #257de0; --series: #257de0; --dim: #b9c0cb; --neg: #ec4647; --warn-bg: #fff4e5; --warn-line: #f2a600;
  --font-body: "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Yu Gothic", system-ui, sans-serif;
  --font-head: "Zen Kaku Gothic New", "Noto Sans JP", "Hiragino Kaku Gothic ProN", sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #14161a; --surface: #1c1f25; --fg: #eceef1; --muted: #9aa1ad; --line: #30353e;
  --accent: #338ced; --series: #338ced; --dim: #4b525e; --neg: #eb6263; --warn-bg: #2b2415; --warn-line: #d28e05; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #14161a; --surface: #1c1f25; --fg: #eceef1; --muted: #9aa1ad; --line: #30353e;
  --accent: #338ced; --series: #338ced; --dim: #4b525e; --neg: #eb6263; --warn-bg: #2b2415; --warn-line: #d28e05; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.75;
       padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 64px }
main { max-width: 820px; margin: 0 auto; display: flex; flex-direction: column; gap: 36px }
header .date { color: var(--muted); font-size: 13px; letter-spacing: .04em }
h1 { font-family: var(--font-head); font-size: 28px; line-height: 1.35; margin: 4px 0 8px; text-wrap: balance }
h2 { font-family: var(--font-head); font-size: 20px; line-height: 1.4; margin: 0 0 12px; text-wrap: balance }
h3 { font-size: 15px; margin: 20px 0 6px }
p { margin: 0 0 10px; max-width: 42em }
section { min-width: 0 }
.lead { font-size: 16px }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px }
.box ol, .box ul { margin: 0; padding-left: 1.3em; display: flex; flex-direction: column; gap: 8px }
.ask { background: var(--warn-bg); border: 1px solid var(--warn-line); border-radius: 10px; padding: 18px 20px }
.ask table { margin-top: 8px }
.note { color: var(--muted); font-size: 13px; max-width: 46em }
.scroll { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 14px }
th, td { text-align: right; padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap }
th:first-child, td:first-child { text-align: left; white-space: normal; min-width: 9em }
thead th { color: var(--muted); font-weight: 500; font-size: 12.5px; border-bottom: 1px solid var(--muted) }
td.heat { color: var(--fg) }
tr.pick td { font-weight: 700 }
table.text th, table.text td { text-align: left; white-space: normal; vertical-align: top }
table.text td:first-child { min-width: 11em }
table.tight th, table.tight td { padding: 6px 7px }
table.tight td:first-child { min-width: 10em; font-size: 13px }
.bars { display: grid; grid-template-columns: minmax(6.5em, 15em) minmax(0, 1fr) 4.2em; gap: 7px 12px; align-items: center; font-size: 14px; font-variant-numeric: tabular-nums }
.bars .name { min-width: 0 }
.bars .val { text-align: right }
.track { height: 14px; display: grid; grid-template-columns: var(--left, 0fr) var(--right, 1fr) }
.track .l { display: flex; justify-content: flex-end; border-right: 1px solid var(--muted) }
.track .r { display: flex }
.track.plain .l { border-right: 0 }
.bar { height: 14px; background: var(--series); border-radius: 0 4px 4px 0; min-width: 2px }
.bar.dim { background: var(--dim) }
.bar.neg { background: var(--neg); border-radius: 4px 0 0 4px }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px 28px }
.pair > div { min-width: 0 }
.cap { font-weight: 700; margin: 0 0 8px; font-size: 14px }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; color: var(--muted); font-size: 12.5px; margin-top: 8px }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px }
code { font-size: 13px }
"""


def esc(text):
    return html.escape(str(text))


def signed(v, digits=1, unit="%"):
    return f"{v:.0f}{unit}" if unit == "件" else f"{v:+.{digits}f}{unit}"


def bars(rows, scale=None, digits=1, unit="%", plain=False):
    """rows: (label, value, kind) with kind in '', 'dim'. One scale for the whole list; negatives grow left of the zero line."""
    lo, hi = min(0, min(v for _, v, _ in rows)), max(0, max(v for _, v, _ in rows))
    if scale:
        lo, hi = scale
    left, right = -lo, hi
    out = [f'<div class="bars" style="--left:{left:.3f}fr;--right:{right:.3f}fr">']
    for label, v, kind in rows:
        neg = v < 0
        width = (abs(v) / (left if neg else right) * 100) if (left if neg else right) else 0
        bar = f'<div class="bar {"neg" if neg else kind}" style="width:{min(width, 100):.1f}%" title="{esc(label)} {signed(v, digits, unit)}"></div>'
        out.append(f'<div class="name">{esc(label)}</div><div class="track{" plain" if plain and left == 0 else ""}"><div class="l">{bar if neg else ""}</div><div class="r">{"" if neg else bar}</div></div>'
                   f'<div class="val">{signed(v, digits, unit)}</div>')
    out.append("</div>")
    return "\n".join(out)


def heat(v, cap=40.0, digits=0):
    """A table cell tinted by sign and size: blue for a gain, red for a loss; the number stays in the text colour."""
    if pd.isna(v):
        return '<td class="heat">－</td>'
    strength = min(abs(v) / cap, 1) * 42
    colour = "var(--series)" if v >= 0 else "var(--neg)"
    return f'<td class="heat" style="background:color-mix(in oklab, {colour} {strength:.0f}%, var(--surface))">{signed(v, digits)}</td>'


def table(head, rows, pick=None, kind=""):
    body = "".join(f'<tr{" class=\"pick\"" if pick is not None and i == pick else ""}>' + "".join(c if str(c).startswith("<td") else f"<td>{c}</td>" for c in r) + "</tr>" for i, r in enumerate(rows))
    return f'<div class="scroll"><table class="{kind}"><thead><tr>' + "".join(f"<th>{esc(h)}</th>" for h in head) + f"</tr></thead><tbody>{body}</tbody></table></div>"


def main():
    forward = pd.read_csv(os.path.join(CACHE, "div_rich_forward.csv"), index_col=0)
    share = pd.read_csv(os.path.join(CACHE, "div_share.csv"))
    rule = pd.read_csv(os.path.join(CACHE, "div_rule.csv"), index_col=0)
    falls = pd.read_csv(os.path.join(CACHE, "div_longrun_falls.csv"), index_col=0)
    profile = pd.read_csv(os.path.join(CACHE, "div_profile.csv"), index_col=0)
    value = pd.read_csv(os.path.join(CACHE, "div_valuecheck.csv"), index_col=0)
    names = pd.read_csv(os.path.join(CACHE, "div_names_windows.csv"), index_col=0)

    parts = []
    add = parts.append

    # ---- this week (draft/weekly_review.py, prices at the 11-27 close)
    week = [("今回の積み立て", 7.33, ""), ("QLYS・TENB を半分ずつ", 6.82, "dim"), ("セキュリティ22銘柄を均等に", 5.95, "dim"), ("セキュリティの投資信託（CIBR）", 3.46, "dim"),
            ("小型株（IWM）", 3.18, "dim"), ("ナスダック100（QQQ）", 2.09, "dim"), ("S&P500（SPY）", 1.79, "dim")]
    holdings = [("AXON", 15.4, ""), ("FTNT", 7.3, ""), ("TENB", 7.2, ""), ("QLYS", 7.0, ""), ("FFIV", 3.7, ""), ("GEN", 1.5, "")]

    # ---- after each state of the core (draft/diversify_rich.py)
    state_names = {"very rich (95+)": "超割高（順位95以上）", "rich (80-95)": "割高（80〜95）", "normal (20-80)": "普通（20〜80）", "cheap (under 20)": "割安（20未満）", "all days": "全期間の平均"}

    def state_rows(h):
        f = forward[forward.horizon == h]
        return [(state_names[k], f.loc[k, "core"], "dim" if k == "all days" else "") for k in state_names]

    # ---- outside share when the core is rich (draft/diversify_share.py)
    rich = share[share.group == "core rich (80+)"]
    funds = rich[rich.basket.isin(["core only", "fund mix (defense, health, staples, insurers, T-bills)"])]
    share_label = {"0%": "外へ回さない", "30%": "3割を外へ", "50%": "半分を外へ", "70%": "7割を外へ", "100%": "全部を外へ"}

    # ---- candidates today (draft/diversify_profile.py)
    def cand(sym, label):
        r = profile.loc[sym]
        return (f"{label}（{sym}）", r.ps_rank, "" if r.ps_rank >= 80 else "dim")
    rich_now = [cand("QLYS", "軸：クオリス"), cand("TENB", "軸：テナブル"), cand("AMGN", "アムジェン"), cand("CB", "チャブ"), cand("TRV", "トラベラーズ"), cand("KO", "コカ・コーラ"), cand("JNJ", "J&J"),
                cand("PG", "P&G"), cand("WMT", "ウォルマート"), cand("DG", "ダラー・ゼネラル"), cand("LMT", "ロッキード"), cand("RTX", "RTX"), cand("GD", "ゼネラル・ダイナミクス"),
                cand("NOC", "ノースロップ"), cand("PEP", "ペプシコ"), cand("MCD", "マクドナルド")]

    # ---- baskets in past sell-offs (printed by the stage-5 run; prices from Yahoo, dividends included)
    windows = [("2015年6月〜16年2月（QLYS -65%）", -62.7, 9.0, -4.0, 0.1, -8.2, -54.8, -12.5), ("2018年秋", -31.6, -13.5, -11.6, 0.6, 0.8, -45.5, -21.3),
               ("2020年 コロナ急落", -24.5, -30.8, -35.2, 0.6, -11.5, -27.4, -27.2), ("2021年11月〜22年11月（利上げ）", -26.5, 26.8, 1.1, 0.3, 10.1, -16.6, -34.2),
               ("2025年 関税ショック", -21.4, 2.6, -7.8, 0.6, -16.0, -29.0, -22.7), ("2025年7月〜26年4月（セキュリティだけ下げ）", -50.4, 11.4, 14.3, 3.0, 129.0, -56.2, 11.0),
               ("2026年10〜11月（AI関連の急落）", 1.3, 10.9, 5.1, 0.5, -2.9, -29.3, -19.5)]

    # ---- sixty years of industries (draft/diversify_longrun.py)
    industry = {"T-bills": "短期国債", "soft drinks": "清涼飲料", "tobacco": "たばこ", "food": "食品", "utilities": "電力", "defense": "防衛", "oil": "石油", "insurance": "保険",
                "retail": "小売", "drugs": "製薬", "market": "市場全体", "chips": "半導体", "restaurants": "外食"}
    rose = ((falls[list(industry)] > 0).mean() * 100).sort_values(ascending=False)
    rose_rows = [(industry[k], v, "" if k == "T-bills" else "dim") for k, v in rose.items()]

    add(f"""<header><div class="date">2026年11月28日（土）時点・研究の途中経過（締め切りは11月29日 12時）</div>
<h1>セキュリティ株の分散先</h1>
<p class="lead">今週の成績の振り返りと、「機関投資家はもう織り込んでいそう」という見方を受けた、セキュリティ以外の置き場の研究です。</p></header>""")

    add("""<section class="box"><h2>先に結論</h2><ol>
<li><b>今週は +7.33%。</b>ただしセキュリティ株そのものが強かった週で、買い方の工夫による上乗せは小さい（軸の2銘柄を同じ日に半分ずつ買っただけで +6.82%）。</li>
<li><b>軸の2銘柄は「割高」の水準。</b>過去13年、この水準に入ったあとの1年で2割近く下げたのは13回中5回。一方で、割高のまま倍になった時期もあるので、売る合図ではない。</li>
<li><b>どの下落でも減らなかったのは短期の米国債だけ。</b>守りの株（防衛・食品など）は「ハイテクだけが売られる下げ」には効くが、「全部が売られる危機」では一緒に下げる。定番のコカ・コーラや P&amp;G は、今すでに軸と同じくらい割高。</li>
<li><b>提案：軸が割高のあいだは、毎日の半分をセキュリティの外へ。</b>外の半分は短期国債（SHV）、残りは割高でない守りの株（NOC・GD・PEP・MCD）。平均の成績を年0.5ポイントほど下げるかわりに、割高で始めた場合の最悪を -63% から -24% にする「保険」。</li>
</ol></section>""")

    add("""<section class="ask"><h2>決めてほしいこと</h2>
<p>月曜の注文（日本時間 11月30日 23:47）までに返事をください。返事がなければ、月曜は今の決まりのまま出します（FFIV に 27.57ドル全額）。</p>""" + table(
        ["決めること", "おすすめ", "理由"],
        [["A. 軸が割高のあいだ、毎日の半分を外へ回す", "回す", "割高で始めたときの最悪が半分以下になる"],
         ["B. 外の中身", "SHV 半分＋NOC・GD・PEP・MCD", "SHV だけが全局面で無傷。株は割高でないものに限る"],
         ["C. 軸以外の1銘柄は1日の3分の1まで", "入れる", "月曜のような1銘柄への集中を防ぐ"],
         ["D. AXON を逃げ先から外す（持っている分はそのまま）", "外す", "過去7回の下落すべてで17〜56%下げた"],
         ["E. UI を外の候補から外す", "外す", "+129% から -16% まで当たり外れが大きい"]], kind="text") + "</section>")

    add('<section><h2>今週の成績</h2><p>投じた 214.01ドルが、11月27日の終値で 229.70ドル（+15.70ドル）。同じ金額を同じ時刻に別の買い方をした場合と比べます。</p>'
        '<div class="pair"><div><p class="cap">同じ日・同じ金額で買った場合の成績</p>' + bars(week, plain=True) +
        '</div><div><p class="cap">持っている銘柄ごとの成績</p>' + bars(holdings, plain=True) + "</div></div>"
        '<p class="note">今週（11月23〜27日）だけの損益は +18.84ドル。買う時刻の影響はほぼなし（寄り付きで買うと +7.75%、引けで買うと +7.28%）。GEN は大口の売り越しが続いている。出所：<code>draft/weekly_review.py</code></p></section>')

    add('<section><h2>機関投資家は織り込み済みか</h2>' + table(
        ["", "株価", "アナリスト目標の平均", "目標まで", "買い推奨の割合", "割安度の順位（100がいちばん割高）"],
        [["QLYS", "206.33ドル", "196.8ドル", "-4.6%", "18%", "97"], ["TENB", "47.21ドル", "48.4ドル", "+2.4%", "35%", "88"]]) +
        '<p class="note">順位は、株価売上高倍率（株価が1株あたり売上の何倍か）が、その銘柄自身の直近2年の中でどの位置にあるか。大口の注文は11月10〜27日の合計で QLYS +2,410万ドル、TENB +3,250万ドルの買い越し。'
        "QLYS は株価がすでに目標を上回っていて、「織り込み済み」という見方と合う。</p></section>")

    add('<section><h2>軸が割高になったあと、どうなったか</h2><p>Webull の価格データ（2022年〜）には、軸が割高だった時期が今回の1回しかない。'
        "そこで米国の決算書類と長期の株価から同じ物差しを作り直し、QLYS は2013年、TENB は2020年までさかのぼった。</p>"
        '<div class="pair"><div><p class="cap">その後60営業日の軸の成績（平均）</p>' + bars(state_rows(60), scale=(-4, 24)) +
        '</div><div><p class="cap">その後250営業日（約1年）の軸の成績（平均）</p>' + bars(state_rows(250), scale=(-4, 24)) + "</div></div>"
        '<p class="note">超割高は2〜3か月は勢いが続くが、1年後は +3.6% にとどまる。割高は直後の60日が弱い。割高の時期は15回で、1年後まで見られる13回のうち5回は、1年以内に18%以上下げた。'
        "反対に 2017〜18年は割高のまま1年で +124%。出所：<code>draft/diversify_rich.py</code></p></section>")

    def share_bars(col, scale):
        return bars([(share_label[r.outside], getattr(r, col), "" if r.outside == "50%" else "dim") for r in funds.itertuples()], scale=scale)
    add('<section><h2>割高のときに、どれだけ外へ回すか</h2><p>軸が割高の日に23営業日の積み立てを始め、毎日の一定割合を外へ回して、1年後まで持った場合（144本）。'
        "外は業種の投資信託4本と短期国債。あとから伸びたと分かっている個別株は入れていない。</p>"
        '<div class="pair"><div><p class="cap">1年後の成績（平均）</p>' + share_bars("end_mean", (-70, 12)) +
        '</div><div><p class="cap">1年後の成績（いちばん悪かった1本）</p>' + share_bars("end_worst", (-70, 12)) + "</div></div>"
        '<p class="note">外へ回す割合を上げても平均はあまり変わらず（+8.5% から +6.7%）、最悪だけが大きく縮む（-62.6% から -6.8%）。'
        "ふだん（割高でないとき）に外へ回すと、年に8ポイントほど取り逃すので、割高のときだけに限る。出所：<code>draft/diversify_share.py</code></p>"
        "<h3>決まりとして、全部の時期に当てた場合</h3>" + table(
            ["決まり", "全607本の平均", "最悪", "割高で始めた144本の平均", "その最悪"],
            [[label] + [signed(rule.loc[key, c]) for c in ("end_mean", "end_worst", "end_mean_rich", "end_worst_rich")] for label, key in (
                ("外へ回さない", "never outside"), ("いつも半分を外へ", "always 50%"), ("順位80以上で3割", "80+: 30%"), ("順位80以上で半分、95以上で7割（提案）", "80+: 50%, 95+: 70% (proposed)"),
                ("順位80以上で全部", "80+: 100%"), ("逆：順位50未満のとき半分を外へ", "opposite: 50% outside when under 50"))], pick=3) +
        '<p class="note">しきい値や割合を動かしても結果はなだらかに変わるだけで、特定の数字にたまたま合っているわけではない。全体の最悪 -43.9% はどの決まりでも変わらない。'
        "これは割高でない水準から始まった下げ（2025年7月〜2026年4月）で、割高さを見る決まりでは防げない。出所：<code>draft/diversify_rule.py</code></p></section>")

    add('<section><h2>分散先の候補は、今どれくらい割高か</h2><p>軸と同じ物差し（その銘柄自身の直近2年の中での位置）で並べたもの。80以上を「割高」としている。</p>' + bars(rich_now, scale=(0, 100), digits=0, unit="", plain=True) +
        '<div class="legend"><span><i style="background:var(--series)"></i>80以上（割高）</span><span><i style="background:var(--dim)"></i>80未満</span></div>'
        '<p class="note">生活必需品・製薬・保険の大手は、この1年で30〜40%上がり、軸と同じ水準まで買われている。アナリスト目標が株価より下の銘柄も多い（アムジェン -7.0%、トラベラーズ -7.5%）。'
        "ただし守りの株35銘柄で確かめると、割高なものもその後1年は平均 +14%（割安なものは +18.6%）。割高だから危ない、とまでは言えず、選ぶときの優先順位に使う程度。"
        "割高でない NOC は、11月の中間選挙のあと国防予算の懸念で急落した銘柄で、安い理由がそのまま危険でもある。出所：<code>draft/diversify_profile.py</code>、<code>draft/diversify_valuecheck.py</code></p>"
        "<h3>日本の Webull で買えないもの</h3><p>短期国債の投資信託 SGOV・BIL、値動きの小さい株の投資信託 USMV、保険の投資信託は取引不可。短期国債の置き場は SHV（0〜1年の米国債、直近1年 +3.6%）になる。個別株はどれも端株で買える。</p></section>")

    # ---- how much X talks about them (draft/x_defensive.py --summary)
    from x_defensive import summary
    rotation, valuation, tickers = summary()
    month_label = lambda m: f"{m[:4]}年{int(m[5:])}月" if m.endswith("-01") or m == rotation.index[0] else f"{int(m[5:])}月"
    rot_rows = [(month_label(m) + ("（27日まで）" if m == rotation.index[-1] else ""), float(v), "" if m >= "2026-10" else "dim") for m, v in rotation.items()]
    before = tickers.iloc[:-3].mean()
    tick_names = {"KO": "コカ・コーラ", "WMT": "ウォルマート", "COST": "コストコ", "PG": "P&G", "NOC": "ノースロップ", "GD": "ゼネラル・ダイナミクス", "LMT": "ロッキード", "RTX": "RTX",
                  "PEP": "ペプシコ", "MCD": "マクドナルド"}
    tick_rows = [[f"{tick_names[t]}（{t}）", f"{before[t]:.0f}", str(tickers[t].iloc[-3]), str(tickers[t].iloc[-2]), str(tickers[t].iloc[-1])] for t in tickers.columns]
    add('<section><h2>X ではどれくらい話題になっているか</h2><p>人気が集まりすぎていないかを見るために、英語の投稿を月ごとに数えた（一定以上「いいね」がついたものだけ）。</p>'
        '<p class="cap">「守りの株へ資金が移っている」という話題の投稿数（いいね100以上）</p>' + bars(rot_rows, digits=0, unit="件", plain=True) +
        "<h3>銘柄ごとの投稿数（いいね50以上）</h3>" + table(["銘柄", f"{tickers.index[0][:4]}年{int(tickers.index[0][5:])}月〜{tickers.index[-4][:4]}年{int(tickers.index[-4][5:])}月の月平均", "9月", "10月", "11月（27日まで）"], tick_rows) +
        f'<p class="note">生活必需品の投稿のうち割高さに触れたものは、それまで月 {valuation.iloc[:-1].min()}〜{valuation.iloc[:-1].max()} 件だったのが、11月は {valuation.iloc[-1]} 件。'
        "「安全資産株のバブル」「生活必需品の割高さは1999年以来」「ウォルマートに利益の40倍」といった内容で、人気が集まりすぎていることを皮肉る投稿が多い。"
        "防衛は逆に、11月の投稿がほとんどない。ペプシコとマクドナルドは9〜10月に1年の安値をつけたときに話題になり、今は落ち着いている。"
        "10月にペプシコの取締役が2,370万ドル分の自社株を買った、という投稿が複数ある（投稿による情報で、届け出は確認していない）。"
        "話題の少なさで選ぶなら、防衛がいちばん「まだ織り込まれていない」側にある。出所：<code>draft/x_defensive.py</code></p></section>")

    add('<section><h2>過去の下落で、それぞれどう動いたか</h2>' + table(
        ["下落の時期", "軸", "守りの株", "投資信託", "SHV", "UI", "AXON", "QQQ"],
        [[w[0]] + [heat(v) for v in w[1:]] for w in windows], kind="tight") +
        '<p class="note">軸は QLYS と TENB、守りの株は NOC・GD・PEP・MCD・PGR、投資信託は防衛・ヘルスケア・生活必需品・電力の4本、SHV は短期国債、QQQ はナスダック100。色は青が値上がり、赤が値下がり。AXON は7回すべてで17〜56%下げ、うち5回は軸より大きく下げた。守りの株と投資信託は、コロナ急落では軸より大きく下げた。全部の回で減らなかったのは短期国債だけ。</p>'
        "<h3>60年分の業種データ：ソフトウェアが25%以上下げた12回で、上がっていた割合</h3>" + bars(rose_rows, scale=(0, 100), digits=0, plain=True) +
        '<p class="note">セキュリティという業種はデータにないので、ソフトウェアで代用。ソフトウェアが大きく下げるとき、市場全体も6回に5回は下げている。防衛は 2000〜02年と 2021〜22年に大きく上げたが、2008年は -41%。'
        "外食は12回中1回しか上がっていない（マクドナルドは外食の中では例外的に下げにくい）。出所：<code>draft/diversify_longrun.py</code></p></section>")

    add('<section><h2>提案する決まりと、月曜の注文</h2><div class="box"><ol>'
        "<li><b>外へ回す割合を、軸の状態で決める。</b>軸2銘柄の順位の平均が80未満なら 0（今と同じ）、80以上なら毎日の半分、95以上なら7割。今は 92.7 なので半分。</li>"
        "<li><b>外の中身。</b>半分を SHV、残りを NOC・GD・PEP・MCD に等分。その日に「上がりすぎ」の判定にかかった銘柄の分は SHV に回す。</li>"
        "<li><b>1銘柄の上限。</b>軸以外の1銘柄は1日の3分の1まで。超える分は外へ。</li>"
        "<li><b>AXON と UI を逃げ先から外す。</b>持っている分は売らない。</li>"
        "<li>SHV は置き場。軸が普通〜割安に戻ったときに SHV を売って軸へ戻す決まりは、3か月後の見直しで作る。</li></ol></div>"
        "<h3>月曜（米国 11月30日）の注文の試算</h3><p>11月27日の終値で判定、1日 27.57ドル。QLYS は順位97で買わない、TENB・GEN・FTNT は上がりすぎの判定、AXON は5日で +18%。セキュリティの中で買えるのは FFIV だけ。</p>" + table(
            ["決まり", "注文"],
            [["今のまま", "FFIV 27.57ドル（100%）"], ["今の決まり＋1銘柄の上限（超過は UI へ）", "UI 18.38ドル（67%）、FFIV 9.19ドル（33%）"],
             ["提案", "SHV 16.08ドル（58%）、FFIV 9.19ドル（33%）、GD 2.30ドル（8%）"]], pick=2, kind="text") +
        '<p class="note">提案では NOC・PEP・MCD も上がりすぎの判定にかかるので、その分が SHV に入る。全体が大きく上げた直後なので、月曜は「ほとんど置き場へ」になる。'
        "決まりの計算にはこの切り替えを入れてあるが、初期値はオフで、本番の注文は変えていない。出所：<code>draft/diversify_preview.py</code></p></section>")

    add("""<section><h2>この研究の弱いところ</h2><div class="box"><ul>
<li><b>例が少ない。</b>軸が割高だった時期は15回。TENB も入っているのは2020年以降だけ。</li>
<li><b>あとから選んでいる。</b>NOC・GD・PEP・MCD は、今の割高さと直近の下落を見て選んだ。業種で見ると、下落時に上がっていたのは防衛が5割、外食は1割。</li>
<li><b>今の環境に寄っている。</b>この1年は利上げ・物価高・戦争で、守りの株と資源が買われた。利下げや和平で逆回転すれば、守りの株は取り残される。</li>
<li><b>防げない下げがある。</b>割高でない水準から始まる下げ（2025〜26年のセキュリティの下げ）には、この決まりは何もしない。全部が売られる危機では、守りの株も20〜60%下げる。</li>
<li><b>割合に強い根拠はない。</b>半分・7割は目安。上げるほど落ち込みは減り、上昇の取り分も減る。</li>
<li><b>期間が短い。</b>今回の積み立ては残り15営業日。この研究が見ているのは半年〜1年先で、12月18日までの値動きについては何も言えない。</li>
</ul></div><p class="note">くわしい記録は <code>draft/research/diversification.md</code>。</p></section>""")

    page = ('<title>セキュリティ株の分散先</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Zen+Kaku+Gothic+New:wght@700&display=swap">\n'
            f"<style>{CSS}</style>\n<main>\n" + "\n".join(parts) + "\n</main>\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(page)
    print("wrote", OUT, f"{len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
