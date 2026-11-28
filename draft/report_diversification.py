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


def bars(rows, scale=None, digits=1, unit="%", plain=False, sign=True):
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
                   f'<div class="val">{signed(v, digits, unit) if sign else f"{v:.{digits}f}{unit}"}</div>')
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
    defense = pd.read_csv(os.path.join(CACHE, "defense_value.csv"), index_col=0)
    defense_falls = pd.read_csv(os.path.join(CACHE, "defense_falls.csv"), parse_dates=["day"])

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
                cand("NOC", "ノースロップ"), cand("HII", "ハンティントン・インガルス"), cand("LHX", "L3ハリス"), cand("PEP", "ペプシコ"), cand("MCD", "マクドナルド")]

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
<li><b>決まった形：セキュリティ5割、残りを1割ずつ5つの枠へ。</b>枠は防衛（NOC）・外食（MCD）・飲料（PEP）・電力（NEE）・金（GLD）。2013年以降で確かめると、伸びは年1ポイントほどの差で、値動きの幅と落ち込みがほぼ半分になる。効果のほとんどは「5割に下げること」から来ていて、5枠に何を入れるかの差は小さい。</li>
<li><b>米国の防衛株は「割安」ではなく「普通の値段に戻った」段階。</b>NOC は3月の高値のとき利益の26倍、今は18倍弱で、過去10年の真ん中。本当に割安だった2011〜13年は8〜10倍だった。</li>
</ol></section>""")

    add("""<section class="ask"><h2>月曜からの動かし方（11月28日に決定）</h2>
<p>形と中身は了承済み。銘柄は X の動向も入れて選び直した。月曜（日本時間 11月30日 23:47）の注文からこの形で出す。替えたい銘柄があれば、注文の前に伝えてほしい。</p>""" + table(
        ["決まったこと", "中身"],
        [["配分", "積み立ての残りを、セキュリティ5割、5つの枠に1割ずつ"],
         ["5つの枠", "防衛 NOC、外食 MCD、飲料 PEP、電力 NEE、金 GLD"],
         ["セキュリティ側", "行き先は今の決まりのまま。軸以外の1銘柄は1日全体の3分の1まで"],
         ["上がりすぎの日", "その銘柄は買わず、お金は持ち分に残して翌日以降に回す"],
         ["対象から外すもの", "AXON と UI（持っている分は売らない）"]], kind="text") + "</section>")

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

    add('<section><h2>分散先の候補は、今どれくらい割高か</h2><p>軸と同じ物差し（その銘柄自身の直近2年の中での位置）で並べたもの。80以上を「割高」としている。</p>' + bars(rich_now, scale=(0, 100), digits=0, unit="", plain=True, sign=False) +
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
        "防衛は「織り込まれていない」のではなく、いったん織り込まれた期待が剥がれた状態。1月に国防予算を1.5兆ドルへ増やす案が出て話題も株価も盛り上がり、NOC と LMT は3月2日に高値をつけた。"
        "その後は NOC が高値から -27%、防衛の投資信託（ITA）が -18%。欧州はもっと極端で、ラインメタルは1月の高値から -60%。出所：<code>draft/x_defensive.py</code></p></section>")

    # ---- are the US defense contractors cheap? (draft/defense_value.py)
    dn = {"NOC": "ノースロップ（NOC）", "HII": "ハンティントン・インガルス（HII）", "LHX": "L3ハリス（LHX）", "LMT": "ロッキード（LMT）", "GD": "ゼネラル・ダイナミクス（GD）", "RTX": "RTX"}
    def_rows = [[dn[k], f"{r.pe:.1f}倍", f"{r.pe_at_1y_high:.1f}倍", f"{r.pe_median_10y:.1f}倍", f"下から{r.pe_place_since_2011:.0f}%", signed(r.from_high, 0), signed(r.eps_growth, 0), f"{r.cash_yield:.1f}%"]
                for k, r in defense.loc[list(dn)].iterrows()]
    recent = defense_falls[defense_falls.day >= "1993-02-01"]
    one, three = recent.dropna(subset=["1y"]), recent.dropna(subset=["3y"])
    add('<section><h2>米国の防衛株は割安か</h2><p>各社の株価が利益の何倍かを、その会社自身の過去と比べた（11月27日の終値）。</p>' + table(
        ["", "今", "今年の高値のとき", "過去10年の中央値", "2011年以降での位置", "高値から", "1株利益の伸び（1年）", "事業で残る現金（時価総額比）"], def_rows) +
        f'<p class="note">割安とまでは言えない。起きたのは「割高だったものが普通に戻った」こと。この業種が本当に割安だったのは2011〜13年で、国防費の強制削減の不安から利益の8〜10倍まで売られた。'
        f"NOC が過去10年の下限（利益の{defense.loc['NOC', 'pe_low_10y']:.1f}倍）まで売られると約{defense.loc['NOC', 'price_at_low_band']:.0f}ドルで、今から {(defense.loc['NOC', 'price_at_low_band'] / defense.loc['NOC', 'price'] - 1) * 100:.0f}%。"
        f"6社が1年の高値から25%以上下げた場面は1993年以降に{len(one)}回あり、その後1年は平均 {one['1y'].mean():+.0f}%（上がった割合 {(one['1y'] > 0).mean() * 100:.0f}%）。ふだんの1年（+18%）とほぼ同じで、"
        f"S&amp;P500 に勝ったのは {(one['1y_vs_spy'].dropna() > 0).mean() * 100:.0f}%。「下げたから買い」と言えるほどの差はない。"
        "上がる根拠があるとすれば倍率の低さではなく、利益が伸びていることと、ハイテクだけが売られる下げに強いこと。全面安には弱く、リーマンで -45〜-59%、コロナで -26〜-50%。"
        "出所：<code>draft/defense_value.py</code></p></section>")

    add('<section><h2>過去の下落で、それぞれどう動いたか</h2>' + table(
        ["下落の時期", "軸", "守りの株", "投資信託", "SHV", "UI", "AXON", "QQQ"],
        [[w[0]] + [heat(v) for v in w[1:]] for w in windows], kind="tight") +
        '<p class="note">軸は QLYS と TENB、守りの株は NOC・GD・PEP・MCD・PGR、投資信託は防衛・ヘルスケア・生活必需品・電力の4本、SHV は短期国債、QQQ はナスダック100。色は青が値上がり、赤が値下がり。AXON は7回すべてで17〜56%下げ、うち5回は軸より大きく下げた。守りの株と投資信託は、コロナ急落では軸より大きく下げた。全部の回で減らなかったのは短期国債だけ。</p>'
        "<h3>60年分の業種データ：ソフトウェアが25%以上下げた12回で、上がっていた割合</h3>" + bars(rose_rows, scale=(0, 100), digits=0, plain=True, sign=False) +
        '<p class="note">セキュリティという業種はデータにないので、ソフトウェアで代用。ソフトウェアが大きく下げるとき、市場全体も6回に5回は下げている。防衛は 2000〜02年と 2021〜22年に大きく上げたが、2008年は -41%。'
        "外食は12回中1回しか上がっていない（マクドナルドは外食の中では例外的に下げにくい）。出所：<code>draft/diversify_longrun.py</code></p></section>")

    # ---- half in security, five slots of 10% (draft/lineup.py, draft/lineup_preview.py)
    combos = pd.read_csv(os.path.join(CACHE, "lineup_all.csv"))
    kinds_alone = pd.read_csv(os.path.join(CACHE, "lineup_kinds.csv"), index_col=0)
    kind_cols = ["level_0", "level_1", "level_2", "level_3", "level_4"]
    kind_ja = {"restaurants": "外食", "gold": "金", "tobacco": "たばこ", "drug makers": "製薬", "power": "電力", "7-10 year Treasuries": "7〜10年の米国債", "insurance": "保険", "retail": "小売",
               "waste": "ごみ処理", "drinks and food": "飲料・食品", "exchanges": "取引所", "defense": "防衛", "household goods": "日用品", "telecom": "通信", "health insurer": "医療保険", "oil": "石油"}
    best = combos.head(len(combos) // 20)                              # the file is sorted by the combined rank
    freq = pd.Series({k: best[kind_cols].eq(k).any(axis=1).mean() * 100 for k in kind_ja}).sort_values(ascending=False)
    freq_rows = [(kind_ja[k], v, "" if v >= 5 / 16 * 100 else "dim") for k, v in freq.items()]
    mid = combos[["growth", "swing", "deepest", "falls_avg"]].median()
    core_row = kinds_alone.loc["core"]
    shape_rows = [["セキュリティの軸だけ", signed(core_row.growth), f"{core_row.swing:.0f}%", signed(core_row.deepest), signed(core_row.falls_avg)],
                  ["軸5割＋5枠（4,368通りの真ん中）", signed(mid.growth), f"{mid.swing:.0f}%", signed(mid.deepest), signed(mid.falls_avg)],
                  ["いちばん良い組み合わせ", signed(combos.growth.max()), f"{combos.swing.min():.0f}%", signed(combos.deepest.max()), signed(combos.falls_avg.max())],
                  ["いちばん悪い組み合わせ", signed(combos.growth.min()), f"{combos.swing.max():.0f}%", signed(combos.deepest.min()), signed(combos.falls_avg.min())]]

    def pick(kind, sym, note):
        r = profile.loc[sym]
        return [kind, sym, f"{r.ps_rank:.0f}", f"{r.growth_before:.1f}% から {r.growth:.1f}%", signed(r.target_gap, 0), signed(r.from_high, 0), note]
    gld = profile.loc["GLD"]
    pick_rows = [pick("防衛", "NOC", "過去7回の下落のうち5回で上昇。選挙後に国防予算の懸念で売られた。X では悪い話題なし"),
                 pick("外食", "MCD", "10月に9週続落で4年ぶりの安値（230ドル）をつけ、X は悲観一色だった。そこから2割戻している"),
                 pick("飲料", "PEP", "10月に取締役が2,370万ドル分を買った（同社で過去最大）。アナリストの買い推奨は24%と不人気"),
                 pick("電力", "NEE", "利益の倍率が2年で最低圏。データセンター向けの需要と、選挙後の再生可能エネルギーへの追い風。利上げに弱い"),
                 ["金", "GLD", "－", "－", "－", signed(gld.from_high, 0), "10月は2008年以来の下げ。X は投げ売りの話題。ほかの枠と動きが重ならない"]]
    from x_lineup import summary as x_summary
    xs, _ = x_summary()
    names = pd.read_csv(os.path.join(CACHE, "lineup_names.csv"), index_col=0)

    def swap(slot, old, new, why):
        cell = lambda t: (f"{t}：順位 {profile.loc[t, 'ps_rank']:.0f}、下落7回で上昇 {names.loc[t, 'rose']:.0f}回、"
                          f"X の投稿 {xs.loc[t, 'posts']:.0f}件（買い {xs.loc[t, 'buy']:.0f}%・売り {xs.loc[t, 'sell']:.0f}%）")
        return [slot, cell(old), cell(new), why]
    swap_rows = [swap("防衛", "LHX", "NOC", "11月13日に全米で航空機の離陸が4時間止まり、原因として LHX の通信網が名指しされた。運輸長官は別の会社に替えたい意向。X の話題（いいねの合計）は3倍に増え、中身は批判"),
                 swap("飲料（たばこから変更）", "PM", "PEP", "PM は10月に最高値をつけたあと下げ続け、利益の伸びは見通しの下半分。直近2回の下落でも下げた。PEP は割安で、売上が上向き、取締役の大口買い"),
                 swap("電力（据え置き）", "AEP", "NEE", "AEP は下落に強く決算も好調だが、利益の倍率が2年で高い側（下から88%）。NEE は最低圏（4%）。割安なほうを残した")]
    add('<section><h2>セキュリティ5割、残りを1割ずつ5つの枠へ</h2><p>枠の種類を16用意し、そこから5つを選ぶ4,368通りすべてについて、'
        "「軸5割＋5枠を1割ずつ、毎日配分を戻す」を2013年から計算した。</p>" + table(
            ["", "年あたりの伸び", "1年の値動きの幅", "いちばん深い落ち込み", "7回の下落の平均"], shape_rows) +
        '<p class="note">5割に下げると、伸びは年1ポイントほどの差で、値動きの幅と落ち込みがほぼ半分になる。5枠の中身を替えても、落ち込みは -37%〜-43% の範囲にしかならない。'
        "軸の値動き（年43%）が、ほかの枠（年16〜20%）よりずっと大きいから。全面安（コロナ）ではどの5枠でも -22%〜-28% で、軸だけ（-24.5%）と変わらない。</p>"
        '<p class="cap">成績が上位5%だった組み合わせに、その枠が入っていた割合</p>' + bars(freq_rows, scale=(0, 100), digits=0, plain=True, sign=False) +
        '<div class="legend"><span><i style="background:var(--series)"></i>偶然（31%）より多い</span><span><i style="background:var(--dim)"></i>偶然より少ない</span></div>'
        '<p class="note">外食はマクドナルド1社だけの結果なので割り引いて見る。金と国債は、ほかのどの枠とも動きが重ならない。防衛は2018年秋とコロナで軸と一緒に下げたので中くらい。'
        "ただ1割なら全体への影響は小さい。出所：<code>draft/lineup.py</code></p>"
        "<h3>5つの枠と、選んだ銘柄</h3>" + table(["枠", "銘柄", "割安度の順位（80以上が割高）", "売上の伸び（前の年から直近）", "アナリスト目標まで", "1年の高値から", "直近の様子"], pick_rows, kind="text") +
        "<h3>X の動向を入れて選び直したところ</h3><p>候補を31銘柄に広げ、銘柄名つきの英語の投稿（いいね30以上、5月〜11月）を集めて、話題の量と中身を見た。投稿数は直近2か月。</p>" +
        table(["枠", "見送った銘柄", "選んだ銘柄", "理由"], swap_rows, kind="text") +
        '<p class="note">外食は MCD のまま。ほかの外食（YUM・SBUX・CMG・DRI）は過去の下落でほとんど上がっていない。金は GLD のまま。金鉱株（NEM）は値動きが年42%と大きすぎる。'
        "製薬は JNJ と AMGN の話題が2倍超に増えていて、割安度の順位も98〜100。人気が集まりすぎている。保険は話題がほぼなく割高でもないが、伸びが鈍っている。"
        "買い・売りの割合は投稿の中の言葉で機械的に数えたもので、目安。出所：<code>draft/x_lineup.py</code></p>" +
        '<p class="note">この5枠で計算すると、年あたりの伸び +19.4%、いちばん深い落ち込み -37.4%、7回の下落の平均 -15.5%（4,368通りの上位1%）。製薬と保険は枠としては良いが、割高でない銘柄が見当たらない（製薬大手は順位87〜100、'
        "LLY は利益の45倍、PGR は伸びが鈍っている）。どれも日本の Webull で端株で買える。</p>"
        "<h3>動かし方と、月曜（米国 11月30日）の注文</h3><div class=\"box\"><ol>"
        "<li>積み立ての残りの現金を、セキュリティ用に5割、5つの枠に1割ずつ、あらかじめ分けておく。</li>"
        "<li>毎日、それぞれの持ち分を残り日数で割った額だけ買う。</li>"
        "<li>セキュリティ側の行き先は今の決まりのまま（軸の QLYS・TENB、割高なら別のセキュリティ銘柄）。軸以外の1銘柄は1日全体の3分の1まで。</li>"
        "<li>その日に上がりすぎの判定にかかった銘柄は買わず、そのお金は持ち分に残して翌日以降に回す。</li></ol></div>" + table(
            ["決まり", "注文", "買わずに持ち分へ残る分"],
            [["今のまま", "FFIV 27.57ドル", "なし"],
             ["セキュリティ5割＋5枠", "FFIV 9.19ドル、NEE・GLD に各 2.76ドル（合計 14.70ドル）", "セキュリティ側 4.59ドル、NOC・MCD・PEP の枠 計 8.27ドル"]], pick=1, kind="text") +
        '<p class="note">11月27日の終値で判定、1日 27.57ドル。セキュリティ側で買えるのが FFIV だけなのは、QLYS が順位97で買わない水準、TENB・GEN・FTNT が今週の急騰で上がりすぎの判定にかかっているため。'
        "NOC・MCD・PEP も同じ判定で月曜は見送りになり、その分は各枠の持ち分に残って翌日以降に回る。守りの株でも、この判定にかかった日のあとは成績がやや低い（その後60日で +2.9%、ほかの日は +4.0%）ので、判定は残した。この研究の前半で出した案（軸が割高のあいだだけ半分を外へ、行き先は NOC・GD・PEP・MCD）は、この形に置きかえた。"
        "本番のプログラム（<code>draft/plan_live.py</code>）にはこの形を入れ、注文を出さない空回しで同じ結果になることを確かめた。出所：<code>draft/lineup_preview.py</code></p></section>")

    add("""<section><h2>この研究の弱いところ</h2><div class="box"><ul>
<li><b>例が少ない。</b>軸が割高だった時期は15回。TENB も入っているのは2020年以降だけ。</li>
<li><b>あとから選んでいる。</b>NOC・GD・PEP・MCD は、今の割高さと直近の下落を見て選んだ。業種で見ると、下落時に上がっていたのは防衛が5割、外食は1割。</li>
<li><b>今の環境に寄っている。</b>この1年は利上げ・物価高・戦争で、守りの株と資源が買われた。利下げや和平で逆回転すれば、守りの株は取り残される。</li>
<li><b>防げない下げがある。</b>割高でない水準から始まる下げ（2025〜26年のセキュリティの下げ）には、この決まりは何もしない。全部が売られる危機では、守りの株も20〜60%下げる。</li>
<li><b>割合に強い根拠はない。</b>半分・7割は目安。上げるほど落ち込みは減り、上昇の取り分も減る。</li>
<li><b>期間が短い。</b>今回の積み立ては残り15営業日。この研究が見ているのは半年〜1年先で、12月18日までの値動きについては何も言えない。</li>
</ul></div><p class="note">くわしい記録は <code>draft/research/diversification.md</code>。</p></section>""")

    shape = next(i for i, part in enumerate(parts) if "<h2>セキュリティ5割、残りを1割ずつ5つの枠へ</h2>" in part)
    parts.insert(3, parts.pop(shape))                                # the shape under decision comes right after the questions

    page = ('<title>セキュリティ株の分散先</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Zen+Kaku+Gothic+New:wght@700&display=swap">\n'
            f"<style>{CSS}</style>\n<main>\n" + "\n".join(parts) + "\n</main>\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(page)
    print("wrote", OUT, f"{len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
