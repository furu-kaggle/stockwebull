"""Build the five-year outlook for the four slots other than defense (draft/research/slots_outlook.html).

Annual figures come from SEC filings (draft/cache/slot_annual.pkl, written while researching); prices and
dividend yields from Yahoo; company targets and outside forecasts from the pages listed at the end of the report.
The scenario returns are arithmetic on stated assumptions, not forecasts:
    return per year = (1 + earnings growth) x (multiple at the end / multiple now)^(1/5) - 1 + dividend yield

Usage: python draft/report_slots.py
"""
import html
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "research", "slots_outlook.html")

CSS = """
/* layout: one reading column; a verdict table first, then one chapter per slot with the same seven parts */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #171a1f; --muted: #5d6470; --line: #dde1e7;
  --accent: #257de0; --series: #257de0; --second: #00a888; --neg: #ec4647; --warn-bg: #fff4e5; --warn-line: #f2a600;
  --good: #008a17; --mid: #b67a00; --weak: #ec4647;
  --font-body: "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Yu Gothic", system-ui, sans-serif;
  --font-head: "Zen Kaku Gothic New", "Noto Sans JP", "Hiragino Kaku Gothic ProN", sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #14161a; --surface: #1c1f25; --fg: #eceef1; --muted: #9aa1ad; --line: #30353e;
  --accent: #338ced; --series: #338ced; --second: #00b894; --neg: #eb6263; --warn-bg: #2b2415; --warn-line: #d28e05;
  --good: #0aac23; --mid: #f2a600; --weak: #eb6263; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #14161a; --surface: #1c1f25; --fg: #eceef1; --muted: #9aa1ad; --line: #30353e;
  --accent: #338ced; --series: #338ced; --second: #00b894; --neg: #eb6263; --warn-bg: #2b2415; --warn-line: #d28e05;
  --good: #0aac23; --mid: #f2a600; --weak: #eb6263; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.75;
       padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 64px }
main { max-width: 840px; margin: 0 auto; display: flex; flex-direction: column; gap: 40px }
header .date { color: var(--muted); font-size: 13px; letter-spacing: .04em }
h1 { font-family: var(--font-head); font-size: 28px; line-height: 1.35; margin: 4px 0 8px; text-wrap: balance }
h2 { font-family: var(--font-head); font-size: 21px; line-height: 1.4; margin: 0 0 4px; text-wrap: balance }
h3 { font-size: 15px; margin: 20px 0 6px }
p { margin: 0 0 10px; max-width: 43em }
section { min-width: 0 }
.lead { font-size: 16px }
.sub { color: var(--muted); margin-bottom: 12px }
.note { color: var(--muted); font-size: 13px; max-width: 46em; margin-top: 10px }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 20px }
.ask { background: var(--warn-bg); border: 1px solid var(--warn-line); border-radius: 10px; padding: 16px 20px }
ol, ul { margin: 0 0 8px; padding-left: 1.3em; display: flex; flex-direction: column; gap: 6px }
.scroll { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top }
thead th { color: var(--muted); font-weight: 500; font-size: 12.5px; border-bottom: 1px solid var(--muted) }
td.n, th.n { text-align: right; white-space: nowrap }
td:first-child { min-width: 7em }
tr.pick td { font-weight: 700 }
.tag { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; border: 1px solid currentColor; white-space: nowrap }
.tag.good { color: var(--good) } .tag.mid { color: var(--mid) } .tag.weak { color: var(--weak) }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px 28px }
.pair > div { min-width: 0 }
.cap { font-weight: 700; margin: 0 0 8px; font-size: 14px }
.bars { display: grid; grid-template-columns: 3.4em minmax(0, 1fr) 4.4em; gap: 5px 10px; align-items: center; font-size: 13.5px; font-variant-numeric: tabular-nums }
.bars .val { text-align: right }
.track { height: 12px; display: grid; grid-template-columns: var(--left, 0fr) var(--right, 1fr) }
.track .l { display: flex; justify-content: flex-end }
.track.zero .l { border-right: 1px solid var(--muted) }
.bar { height: 12px; background: var(--series); border-radius: 0 4px 4px 0; min-width: 2px }
.bar.second { background: var(--second) }
.bar.neg { background: var(--neg); border-radius: 4px 0 0 4px }
.src { font-size: 13px; color: var(--muted) }
.src a { color: var(--accent) }
code { font-size: 13px }
"""


def esc(x):
    return html.escape(str(x))


def bars(rows, kind="", unit="", digits=2, signed=False):
    lo, hi = min(0, min(v for _, v in rows)), max(0, max(v for _, v in rows))
    out = [f'<div class="bars" style="--left:{-lo:.3f}fr;--right:{hi:.3f}fr">']
    for label, v in rows:
        neg = v < 0
        width = abs(v) / (-lo if neg else hi) * 100 if (-lo if neg else hi) else 0
        text = f"{v:+.{digits}f}{unit}" if signed else f"{v:.{digits}f}{unit}"
        bar = f'<div class="bar {"neg" if neg else kind}" style="width:{width:.1f}%" title="{esc(label)} {text}"></div>'
        out.append(f'<div>{esc(label)}</div><div class="track{" zero" if lo < 0 else ""}"><div class="l">{bar if neg else ""}</div><div>{"" if neg else bar}</div></div><div class="val">{text}</div>')
    return "\n".join(out) + "</div>"


def table(head, rows, pick=None, right=()):
    th = "".join(f'<th class="{"n" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(head))
    body = "".join(f'<tr{" class=\"pick\"" if i == pick else ""}>' + "".join(f'<td class="{"n" if j in right else ""}">{c}</td>' for j, c in enumerate(r)) + "</tr>" for i, r in enumerate(rows))
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def per_year(growth, multiple_now, multiple_end, dividend):
    return ((1 + growth / 100) * (multiple_end / multiple_now) ** 0.2 - 1) * 100 + dividend


def scenarios(multiple_now, dividend, cases):
    """cases: (name, what has to be true, earnings growth % per year, multiple in five years, unused)"""
    rows = []
    for name, story, g, m, _ in cases:
        r = per_year(g, multiple_now, m, dividend)
        rows.append([name, story, f"{g:+.0f}%", f"{multiple_now:.1f}倍 → {m:.0f}倍", f"<b>{r:+.0f}%</b>", f"{((1 + r / 100) ** 5 - 1) * 100:+.0f}%"])
    return table(["筋書き", "起きていること", "利益の伸び（年）", "利益の倍率", "年あたりの成績", "5年の合計"], rows, pick=1, right=(2, 3, 4, 5))


def decade(t, first=2016):
    t = t.loc[first:]
    return ('<div class="pair"><div><p class="cap">1株あたりの利益（ドル）</p>' + bars([(str(y), v) for y, v in t.eps.dropna().items()]) +
            '</div><div><p class="cap">1株あたりの配当（ドル）</p>' + bars([(str(y), v) for y, v in t.dps.dropna().items()], kind="second") + "</div></div>")


def main():
    annual = pd.read_pickle(os.path.join(HERE, "cache", "slot_annual.pkl"))
    P = []
    add = P.append

    add("""<header><div class="date">2026年11月28日（土）時点</div>
<h1>4つの枠の5年見立て</h1>
<p class="lead">防衛以外の4枠（外食 MCD、飲料 PEP、電力 NEE、金 GLD）を、5年持つ前提で1つずつ見ます。何で稼ぐ会社か、この10年どうだったか、今の値段は高いのか、今後5年の追い風と向かい風は何か。</p>
<p class="note">「年あたりの成績」は予想ではなく、前提を置いた計算です（利益の伸び、5年後の利益の倍率、配当）。前提が変われば答えも変わります。</p></header>""")

    add('<section><h2>先に見立て</h2>' + table(
        ["枠", "基本の筋書き", "いちばんの追い風", "いちばんの心配", "私の評価"],
        [["外食 MCD", "年 +10% 前後", "店を年4%ずつ増やす計画。利益の倍率が自分の10年で最低圏", "やせ薬の普及と、米国の客数の減少", '<span class="tag good">続けてよい</span>'],
         ["飲料 PEP", "年 +8% 前後。幅が広い", "割安で配当が4%。会社が立て直しの最中", "やせ薬がいちばん効く商品（スナックと炭酸）が主力。配当が稼ぎのほぼ全部", '<span class="tag mid">MCD と心配が重なる</span>'],
         ["電力 NEE", "年 +9% 前後", "データセンター向けの電力需要。利益を年8%以上伸ばす目標", "借金940億ドルと利上げ。大型合併の審査", '<span class="tag mid">AEP への入れ替えを勧める</span>'],
         ["金 GLD", "年 0〜+3%", "ほかの枠と動きが重ならない。中央銀行の買い", "利上げ。2025年に +64% 上げたあとの反動がまだ途中かもしれない", '<span class="tag weak">5年の伸びは期待しにくい</span>']]) +
        '<p class="note">評価は「5年持って報われそうか」で付けた。分散の役（ほかの枠と違う動きをするか）は別の話で、その点では金がいちばん役に立つ。</p></section>')

    add("""<section class="ask"><h2>訂正：電力を NEE にした理由の1つが誤りでした</h2>
<p>選び直しのとき、「NEE は利益の倍率が2年で最低圏（15倍）だから割安」と説明しました。これは誤りです。直近の四半期に一時的な利益が大きく乗っていて（純利益 47.8億ドルに対し、本業の営業利益は 26.2億ドル）、見かけの倍率が低く出ていただけでした。会社が示す本業の1株利益（2026年の見通し 3.92〜4.02ドル）で計算すると約21倍で、AEP（約19.5倍）より高い水準です。</p>
<p>この理由を外すと、AEP のほうが条件がそろいます（下の「電力」の章）。入れ替えるかどうかは、この資料を見て決めてください。月曜に NEE を買う額は 2.76ドルなので、あとから替えても差し支えありません。</p></section>""")

    # ---------------- MCD
    mcd = annual["MCD"]
    add('<section><h2>外食：マクドナルド（MCD）</h2><p class="sub">株価 282.6ドル ／ 配当利回り 2.6% ／ 利益の22.4倍</p>'
        "<h3>どんな商売か</h3><p>店の約95%を加盟店が運営し、マクドナルド本体は土地と建物を貸して家賃を取り、売上に応じた手数料を受け取る。自分で店を回す会社ではないので、売上の46%が営業利益として残る。"
        "ハンバーガーの会社というより、世界4万4千店の大家に近い。</p>"
        "<h3>この10年</h3>" + decade(mcd) +
        '<p class="note">1株利益は10年で年 +9.6%、配当は年 +7.6% ずつ伸びた。配当は約50年続けて増えている。株を5年持った場合の成績（2000年以降のすべての5年間）は、真ん中が年 +14.6%、最悪が年 -4.8%、マイナスだったのは全体の2%。'
        "ただし直近5年は年 +4.9% と冴えない。</p>"
        "<h3>いまの値段</h3><p>利益の22.4倍は、自分の過去10年（真ん中が26.1倍、ふだんの幅は22〜34倍）の下から6%の位置。10月には9週続けて下げ、4年ぶりの安値（230ドル）をつけた。そこから2割戻している。</p>"
        "<h3>今後5年の追い風</h3><ul>"
        "<li><b>店が増える。</b>2027年末までに5万店（今は約4万4千店）にする計画を会社が維持している。年4%ほどの増加。</li>"
        "<li><b>会員が増える。</b>直近90日に使った会員は約2.2億人（前年から +13%）。2027年末に2.5億人、会員向けの売上を450億ドルにする目標。</li>"
        "<li><b>値段が安い。</b>倍率が10年の真ん中（26倍）に戻るだけで、年3%分の上乗せになる。</li></ul>"
        "<h3>今後5年の向かい風</h3><ul>"
        "<li><b>米国の客が減っている。</b>既存店の売上の伸びは、2026年1〜3月の +3.9% から4〜6月は +0.8% に落ち、7月はマイナス。安いメニューを出したが、加盟店の6割強しか採用せず、会社も失敗を認めた。</li>"
        "<li><b>やせ薬（GLP-1）。</b>使っている米国の成人は2025年の14%から2026年春に18%へ。2030年までに3人に1人が使った経験を持つという見通しがある。使う人はファストフードへの支出が約5%減り、普及の進んだ地域ではファストフードの取り分が2022〜25年に2.86%から2.38%へ下がった。</li>"
        "<li><b>加盟店の体力。</b>人件費と食材の値上がりで、安売りに付き合う余力が減っている。</li></ul>"
        "<h3>3つの筋書き</h3>" + scenarios(22.4, 2.6, [
            ("良い", "店が年4%増え、客数も戻る。倍率が10年の真ん中へ", 9, 26, ""), ("基本", "店は増えるが、既存店の伸びは年1〜2%。倍率は今のまま", 7, 22.4, ""),
            ("悪い", "やせ薬で客数が減り続け、出店も鈍る。倍率がさらに下がる", 2, 18, "")]) +
        "<h3>見立てが外れたと分かる合図</h3><ul><li>米国の既存店の売上が、4四半期続けてマイナス。</li><li>5万店の目標を先送りする。</li><li>配当の増額が止まる。</li></ul></section>")

    # ---------------- PEP
    pep = annual["PEP"]
    add('<section><h2>飲料：ペプシコ（PEP）</h2><p class="sub">株価 144.6ドル ／ 配当利回り 4.1% ／ 利益の18.2倍</p>'
        "<h3>どんな商売か</h3><p>名前は飲料だが、稼ぎの柱はスナック（レイズ、ドリトス、チートス）。それに炭酸とスポーツ飲料、シリアル。売上の約4割が米国の外。値上げが通りやすい強いブランドを持つ一方、工場と配送を自前で抱えるので利益率は12〜14%と、マクドナルドよりずっと薄い。</p>"
        "<h3>この10年</h3>" + decade(pep) +
        '<p class="note">売上は10年で年 +4.1%、1株利益は年 +5.0%、配当は年 +7.4%。配当は54年続けて増えている。ただし利益より配当の伸びが速かったので、いまは配当（年79億ドル）が、事業で残る現金（約80億ドル）のほぼ全部を使っている。'
        "株を5年持った場合は、真ん中が年 +9.7%、最悪が年 -0.9%。直近5年は年 +0.7% で、ほぼ横ばい。</p>"
        "<h3>いまの値段</h3><p>利益の18.2倍は、自分の過去10年（真ん中が25.8倍）の下から13%。10月に2008年以来の深い下げとなり、取締役が2,370万ドル分を買った（同社で過去最大の内部者の買い、X の投稿による）。アナリストの買い推奨は24%しかない。</p>"
        "<h3>今後5年の追い風</h3><ul>"
        "<li><b>立て直しの最中。</b>2025年にもの言う株主が入り、会社は費用の削減と事業の見直しを約束した。2026年は過去最大の費用削減を見込み、本業の1株利益を5〜7%伸ばす計画。</li>"
        "<li><b>米国の外が伸びている。</b>2026年は海外の売上が好調で、北米の弱さを補っている。</li>"
        "<li><b>値段が安く、配当が厚い。</b>何も良くならなくても、配当だけで年4%が入る。</li></ul>"
        "<h3>今後5年の向かい風</h3><ul>"
        "<li><b>やせ薬がいちばん効く商品が主力。</b>調査では、落ち込みが大きいのは塩味のスナック、甘いパン・菓子、清涼飲料。ペプシコの主力そのもの。2026年4〜6月の北米の売上は -0.5%。</li>"
        "<li><b>配当に余裕がない。</b>稼いだ現金のほぼ全部が配当に出ていく。売上が減れば、増配を止めるか、借金で払うことになる。</li>"
        "<li><b>取引先を失う例。</b>10月、KFC が米国の数千店でペプシからコカ・コーラに切り替える方向と報じられた。</li></ul>"
        "<h3>3つの筋書き</h3>" + scenarios(18.2, 4.1, [
            ("良い", "立て直しが効き、海外と新しい商品が伸びる。倍率が戻る", 7, 23, ""), ("基本", "費用削減で利益は年4%増。売上は横ばい。倍率は今のまま", 4, 18.2, ""),
            ("悪い", "やせ薬でスナックと炭酸の量が減り続ける。増配が止まり、倍率が下がる", 0, 15, "")]) +
        "<h3>見立てが外れたと分かる合図</h3><ul><li>北米の販売量の減少が年3%を超える。</li><li>増配を見送る、または配当を借金でまかなう。</li><li>本業の1株利益の見通しを引き下げる。</li></ul>"
        '<p class="note"><b>MCD との重なり：</b>どちらも「やせ薬」と「消費の弱さ」で売られていて、5年の心配ごとが同じ。2割分を同じ心配に置くことになる。割安さでは PEP、稼ぐ仕組みの強さでは MCD。</p></section>')

    # ---------------- power
    nee = annual["NEE"]
    add('<section><h2>電力：ネクステラ（NEE）と、代わりの候補 AEP</h2><p class="sub">NEE：株価 85.0ドル ／ 配当利回り 2.9% ／ 本業の利益の約21倍</p>'
        "<h3>どんな商売か</h3><p>2つの事業がある。1つはフロリダの電力会社（州が決めた料金で安定して稼ぐ）。もう1つは全米で風力・太陽光・蓄電池を建てて電気を売る事業で、この分野では米国最大。発電所を建て続ける商売なので、借金（長期で940億ドル）と増資で資金を集め続ける。</p>"
        "<h3>この10年</h3>" + decade(nee) +
        '<p class="note">決算書の利益は年によって大きくぶれる（電力の先渡し契約の評価損益が入るため）。会社が示す本業の1株利益は2025年が3.71ドル。配当は10年で年 +11.4% と速く伸びた。'
        "株を5年持った場合は、真ん中が年 +16.5%、最悪でも年 +0.6%。ただし直近5年は年 +1.9% で、金利が上がってからは伸びていない。</p>"
        "<h3>いまの値段</h3><p>本業の利益の約21倍。電力会社としては高め（AEP は約19.5倍）。値段に、成長への期待がすでに入っている。</p>"
        "<h3>今後5年の追い風</h3><ul>"
        "<li><b>電気の需要が増える。</b>10年以上横ばいだった米国の電力需要が、2030年まで年1.4%ずつ増える見通し。データセンターの電力は2030年に今の4倍。</li>"
        "<li><b>会社の目標。</b>本業の1株利益を2032年まで年8%以上伸ばす（2026年の見通しは3.92〜4.02ドル）。建設待ちの案件は36.7ギガワットで過去最大。</li>"
        "<li><b>選挙の結果。</b>中間選挙のあと、再生可能エネルギーへの追い風を見込む声がある。</li></ul>"
        "<h3>今後5年の向かい風</h3><ul>"
        "<li><b>借金と利上げ。</b>借金が多いので、金利が上がると利払いが増え、株も売られやすい。2022年の利上げ局面では -6%。</li>"
        "<li><b>大型合併の審査。</b>2026年5月、ドミニオン・エナジーを株式交換（670億ドル）で買うと発表。成立は2027年末の見込みで、連邦と3つの州の承認が要る。反対運動もあり、ネクステラは過去にハワイで買収を却下されている。</li>"
        "<li><b>税の優遇と料金への反発。</b>再生可能エネルギーの税優遇が2027年に縮む可能性。家庭の電気料金は前年から8%上がっていて、値上げの申請が通りにくくなっている。</li></ul>"
        "<h3>3つの筋書き（NEE）</h3>" + scenarios(21.0, 2.9, [
            ("良い", "合併が通り、需要も計画どおり。利益は年9%増", 9, 23, ""), ("基本", "目標どおり年8%増。金利が高いので倍率は少し下がる", 8, 19, ""),
            ("悪い", "税優遇が縮み、金利が上がり、合併でもめる。倍率が電力の下限へ", 4, 15, "")]) +
        "<h3>代わりの候補：アメリカン・エレクトリック・パワー（AEP）</h3><p>中西部とテキサスなど11州で送電と配電を担う電力会社。株価 127.7ドル、配当利回り 3.1%、本業の利益の約19.5倍。</p>" + table(
            ["", "NEE", "AEP"],
            [["利益の倍率（本業、2026年の見通し）", "約21倍", "約19.5倍"], ["会社の利益成長の目標", "年8%以上（2032年まで）", "年9〜11%（2027〜31年）。10月に7〜9%から引き上げ"],
             ["直近の決算", "1株利益は予想超え、売上は予想に届かず", "売上 +14%、1株利益 +24%。通期見通しは上限以上"], ["過去7回の下落で上がった回数", "3回", "5回"],
             ["1年の値動きの幅", "25%", "19%"], ["直近5年の成績（年）", "+1.9%", "+12.9%"], ["大きな出来事", "ドミニオンとの合併（審査中）", "5年で1,000億ドルの設備投資。契約済みの新規需要は2031年までに84ギガワット"],
             ["共通の心配", "利上げ、料金値上げへの反発、データセンター需要が見込みを下回ること", ""]]) +
        "<h3>3つの筋書き（AEP）</h3>" + scenarios(19.5, 3.1, [
            ("良い", "需要が契約どおり立ち上がり、料金の値上げも通る", 11, 21, ""), ("基本", "目標の下限で年9%増。倍率は少し下がる", 9, 18, ""),
            ("悪い", "AI向けの需要が見込みを下回り、値上げが通らない", 5, 15, "")]) +
        "<h3>見立てが外れたと分かる合図</h3><ul><li>利益成長の目標を引き下げる。</li><li>州の委員会が値上げや合併を認めない。</li><li>データセンターの契約の取り消しが続く。</li></ul>"
        '<p class="note"><b>私の見立て：</b>5年で見るなら AEP のほうが条件がそろう（倍率が低く、目標の伸びが高く、合併の不確かさがなく、下落に強い）。NEE は当たれば大きいが、借金・合併・政策と、うまくいく条件が多い。'
        "どちらも「AIのデータセンター需要」に成長を頼っているので、AI関連が崩れたときは電力も無傷ではない。</p></section>")

    # ---------------- gold
    years = {2014: -2, 2015: -11, 2016: 8, 2017: 13, 2018: -2, 2019: 18, 2020: 25, 2021: -4, 2022: -1, 2023: 13, 2024: 27, 2025: 64, 2026: -16}
    add('<section><h2>金：金の投資信託（GLD）</h2><p class="sub">株価 334.4ドル ／ 配当なし ／ 1月の最高値から -33%</p>'
        "<h3>どんなものか</h3><p>金の現物を持つ投資信託。会社ではないので、利益も配当もない。値段は「金を欲しがる人が増えるか」だけで決まる。持つ理由は伸びではなく、株と違う動きをすること。</p>"
        "<h3>この13年（1年ごとの騰落）</h3>" + bars([(str(y), v) for y, v in years.items()], unit="%", digits=0, signed=True) +
        '<p class="note">2026年は11月27日まで。2024年 +27%、2025年 +64% と急騰し、2026年1月に最高値（1オンス約5,600ドル）をつけてから3割強下げた。それでも3年前と比べれば年 +21% の水準にあり、「安くなった」というより「急騰の途中まで戻った」状態。</p>'
        "<h3>5年持った場合（2004年以降）</h3><p>真ん中は年 +8.1%、最悪は年 -8.2%。5年持ってマイナスだった割合は23%で、MCD（2%）、PEP（1%）、NEE（0%）よりずっと多い。"
        "前回、最高値から3割下げたのは2013年6月。そこから5年持った成績は合計 -3% だった（途中でさらに19%下げた）。</p>"
        "<h3>今後5年の追い風</h3><ul>"
        "<li><b>中央銀行の買い。</b>各国の中央銀行がドル以外の資産として金を買い続けている。4,000ドルに近づけば買いを増やすという見方がある。</li>"
        "<li><b>銀行の予想。</b>11月に各社が予想を引き下げたあとでも、2027年末で 4,650〜5,000ドル（今より2〜3割高い）。</li>"
        "<li><b>利上げが止まれば。</b>金は利息を生まないので、金利が下がる局面で買われやすい。</li></ul>"
        "<h3>今後5年の向かい風</h3><ul>"
        "<li><b>利上げが続いている。</b>金が下げている理由はドル高と利上げ観測。10月は2008年以来の下げ幅だった。</li>"
        "<li><b>急騰のあとは長い。</b>2011年の最高値のあとは、4年かけて45%下げた。銀行の予想は当時も強気のままだった。</li>"
        "<li><b>何も生まない。</b>短期の米国債なら、値下がりなしで年3.6%の利息がつく。</li></ul>"
        "<h3>3つの筋書き</h3>" + table(["筋書き", "起きていること", "5年後の値段（今と比べて）", "年あたりの成績"],
                                 [["良い", "利上げが止まり、中央銀行の買いが続く。1月の最高値を回復", "+48%", "<b>+8%</b>"], ["基本", "行ったり来たり。銀行の予想ほどは戻らない", "0〜+15%", "<b>0〜+3%</b>"],
                                  ["悪い", "2011年のあとのように、急騰の反動が続く", "-25%", "<b>-6%</b>"]], pick=1, right=(2, 3)) +
        "<h3>見立てが外れたと分かる合図</h3><ul><li>利上げが止まっても金が上がらない。</li><li>中央銀行の買いが減る。</li><li>株が大きく下げた日に、金も一緒に下げる日が増える（分散の役を果たさなくなる）。</li></ul>"
        '<p class="note"><b>私の見立て：</b>5年の伸びを期待して持つものではない。分散の役（ほかの4枠と動きが重ならない）に1割を払う、と割り切れるなら残す意味がある。伸びを求めるなら、別の枠に替えるほうがよい。</p></section>')

    # ---------------- alternatives
    add('<section><h2>入れ替えるなら、という候補</h2><p>どれも日本の Webull で端株で買える。割安度の順位は80以上が割高。</p>' + table(
        ["枠", "銘柄", "割安度の順位", "配当利回り", "直近5年（年）", "過去7回の下落で上昇", "ひとこと"],
        [["電力", "AEP", "68", "3.1%", "+12.9%", "5回", "NEE の代わり。上の章のとおり"],
         ["製薬", "LLY", "56", "0.6%", "+41.7%", "4回", "やせ薬を売る側。MCD・PEP の心配ごとの裏返しになる。利益の45倍と高く、X でも人気が集中"],
         ["たばこ", "PM", "66", "3.5%", "+22.0%", "3回", "加熱式と口に含むたばこが伸びている。10月の最高値から下げている最中"],
         ["ごみ処理", "WM", "67", "1.7%", "+9.8%", "－", "景気に左右されにくい。利益の32倍で安くはない"],
         ["保険", "PGR", "56", "6.5%（特別配当を含む）", "+23.0%", "3回", "利益の12倍。保険料の伸びが鈍っている"]], right=(2, 3, 4, 5)) +
        '<p class="note">過去の検証では、5つの枠に何を入れても全体の結果はほとんど変わらなかった（落ち込みは -37%〜-43% の範囲）。入れ替えは「5年持っていて気持ちよく持てるか」で決めてよい。</p></section>')

    add("""<section class="box"><h2>決めてほしいこと</h2><ol>
<li><b>電力を NEE から AEP に替えるか。</b>おすすめは「替える」。</li>
<li><b>MCD と PEP の両方を持つか。</b>心配ごとが重なる。片方にするなら、残すのは MCD、空いた枠は LLY（やせ薬を売る側）か PM が候補。</li>
<li><b>金を残すか。</b>伸びは期待しにくいが、分散の役はいちばん果たす。外すなら、上の候補から。</li>
</ol><p class="note">月曜の注文は、返事がなければ今の5枠（NOC・MCD・PEP・NEE・GLD）のまま各2.76ドルで出します。1日分は小さいので、あとから替えても差し支えありません。</p></section>""")

    add("""<section><h2>この資料の限界</h2><ul>
<li>5年先を当てることはできない。筋書きは「この前提ならこうなる」という計算で、良い・悪いの幅のほうを見てほしい。</li>
<li>利益の伸びの前提は、会社の目標と過去10年の実績から私が置いた。会社の目標は外れることがある。</li>
<li>やせ薬の影響の数字は、調査会社（ベイン、FTI）の調べで、査読のある研究ではない。</li>
<li>金の値段は GLD の値動きで見ている。1オンスあたりの値段は報道の数字。</li>
</ul>
<p class="src">出所：会社の年次の数字は米国証券取引委員会への提出書類、株価と配当は Yahoo、今の値段と業績は Webull。計画や見通しは次のページから。
<a href="https://www.restaurantdive.com/news/mcdonalds-q1-2026-positive-comp-sales-value-menu-innovation/819554/">Restaurant Dive（MCD 1〜3月）</a>、
<a href="https://www.cnbc.com/2026/08/04/mcdonalds-mcd-q2-2026-earnings.html">CNBC（MCD 4〜6月）</a>、
<a href="https://www.qsrmagazine.com/story/mcdonalds-looks-to-fix-a-value-misfire/">QSR Magazine（安いメニューの失敗）</a>、
<a href="https://www.pepsico.com/en/newsroom/press-releases/2025/pepsico-announces-priorities-to-enhance-shareholder-value-and-provides-preliminary-2026-outlook">ペプシコ（株主価値の計画）</a>、
<a href="https://www.sec.gov/Archives/edgar/data/0000077476/000007747626000050/q320268-kxexhibit991.htm">ペプシコ 7〜9月決算</a>、
<a href="https://seekingalpha.com/news/4543151-nextera-energy-targets-8-percent-eps-cagr-through-2032-as-large-load-demand-and-data-center">Seeking Alpha（NEE の目標）</a>、
<a href="https://www.utilitydive.com/news/nextera-dominion-merger-would-create-worlds-largest-regulated-electric-ut/820457/">Utility Dive（ドミニオンとの合併）</a>、
<a href="https://finviz.com/news/409789/aep-reports-third-quarter-2026-earnings-expands-capital-plan-and-increases-growth-outlook">AEP 7〜9月決算</a>、
<a href="https://www.morningstar.com/business/insights/blog/us-utilities-sector-outlook-the-next-tech-boom">Morningstar（電力需要）</a>、
<a href="https://www.bain.com/insights/preparing-for-the-next-wave-of-weight-loss-drug-adoption-snap-chart/">Bain（やせ薬の普及）</a>、
<a href="https://www.fticonsulting.com/insights/articles/glp-1-drugs-rewriting-rules-food-beverage">FTI（やせ薬と食品）</a>、
<a href="https://goldsilver.com/industry-news/article/gold-price-forecast-2026-2027-key-predictions-from-top-analysts/">GoldSilver（銀行の金予想）</a>、
<a href="https://investingnews.com/gold-falls-14-month-low/">Investing News（金が1年2か月ぶりの安値）</a>。</p></section>""")

    page = ('<title>4つの枠の5年見立て</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Zen+Kaku+Gothic+New:wght@700&display=swap">\n'
            f"<style>{CSS}</style>\n<main>\n" + "\n".join(P) + "\n</main>\n")
    open(OUT, "w").write(page)
    print("wrote", OUT, f"{len(page) / 1024:.0f} KB")
    for name, now, div, cases in (("MCD", 22.4, 2.6, [(9, 26), (7, 22.4), (2, 18)]), ("PEP", 18.2, 4.1, [(7, 23), (4, 18.2), (0, 15)]), ("NEE", 21.0, 2.9, [(9, 23), (8, 19), (4, 15)]), ("AEP", 19.5, 3.1, [(11, 21), (9, 18), (5, 15)])):
        print(name, [round(per_year(g, now, m, div), 1) for g, m in cases])


if __name__ == "__main__":
    main()
