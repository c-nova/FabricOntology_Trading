"""Build the Japanese presenter guide deck from the verified Trading demo artifacts.

Run from any directory with python3 (python-pptx and Pillow are required).
Writes decks/TradingOntology_Demo_Presenter_Guide_JA.pptx, presentation/slide_sources.json
and prompts/presenter_prompts_ja.txt. No Fabric API is called. python-pptx is used because
the pptxgenjs probe failed in the original environment. The DAG image is a browser capture
of the saved local SVG (reports/step3_food_loss_dag.svg), not a Fabric UI screenshot.
"""
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt
from pptx.oxml.xmlchemy import OxmlElement

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OUT = PROJECT / "decks" / "TradingOntology_Demo_Presenter_Guide_JA.pptx"
OUT.parent.mkdir(exist_ok=True)
QA = HERE / "qa"
QA.mkdir(exist_ok=True)
manifest = json.loads((PROJECT / "config/deployment_manifest.json").read_text())
audit = json.loads((PROJECT / "reports/step3_live_audit.json").read_text())
step3 = json.loads((PROJECT / "config/step3_deployment.json").read_text())
events = json.loads((PROJECT / "reports/qa_expected_event_totals.json").read_text())
dataset = json.loads((PROJECT / "data/demo_dataset.json").read_text())["LH_Group_SAP"]

NAVY = "17334A"
TEAL = "087F83"
CORAL = "BD4354"
INK = "21374A"
MUTED = "566A78"
BG = "F4F7F7"
WHITE = "FFFFFF"
PALE = "E6F2EF"
GRAY = "E5EBEE"
PURPLE = "7352AD"
FONT = "Yu Gothic"
SW, SH = 13.333333, 7.5
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
prs.core_properties.title = "Trading Fabric Ontology デモ説明者ガイド"
prs.core_properties.subject = "営業向け基礎解説、DA入力全文と対応結果、食品損失DAG、説明台本"
prs.core_properties.author = "Microsoft Scout"
prs.core_properties.keywords = "Japanese, Presenter Enablement, Synthetic, Fabric, Ontology"
slide_metadata = []

DA = manifest["data_agent"]["url"]
ONTOLOGY = manifest["ontology"]["url"]
NOTEBOOK = step3["url"]
WORKSPACE = manifest["workspace"]["url"]

Q1 = """2025-10-01～2026-09-30を対象に、全額連結EBITDAのbaselineとactualを月次で集計し、折れ線グラフで比較してください。横軸は「2025-10」のような年月の文字列で、2025-10から2026-09までの12か月だけを載せ、期間合計はグラフに含めないでください。縦軸は円を1億で割った億円にしてください。actualとbaselineは別系列にし、同じ行を重複集計しないでください。グラフとは別に、期間全体のactualの全額連結EBITDAと持分管理寄与EBITDAを億円で示し、51%子会社の扱いの違いを説明してください。"""
Q2 = """2025-10-01～2026-09-30の全10イベントについて、全額連結EBITDAへの影響を符号付きの億円で集計し、棒グラフで表示してください。各effect_idは一度だけ合計し、CROSS_NEGとCROSS_POSを含めてください。グラフの項目名は次の短い日本語ラベルを使ってください。
MTL_NEG=製錬停止、MTL_POS=再生合金、ENE_NEG=LNG遅延、ENE_POS=配分最適化、FOD_NEG=食品損失、FOD_POS=調達改善、FIN_NEG=与信費増、FIN_POS=ヘッジ手数料、CROSS_NEG=横断混乱、CROSS_POS=横断回復。
元のevent_idと影響額の対応表も示してください。"""
Q3 = """食品損失イベントFOD_NEGの全額連結EBITDA影響額と持分管理寄与額、重複のないeffect_id件数を示してください。根拠ID、代表する活動ID、契約ID、効果ID、日次指標ID、全社KPI IDを確認できる形で短く説明してください。代表効果はeffect_idの昇順で先頭の1件にし、日次指標IDと全社KPI IDは、その代表効果と同じ日付のactual・全額連結EBITDAのものにしてください。架空の設計上の影響配賦であることを明記してください。図やMermaidは不要です。関係の図は別のNotebookで確認します。"""
Q4 = """ENE_POSについて、根拠、対象活動、契約、効果、EBITDA、全社KPIのつながりをID付きで説明してください。全額JPYと持分管理JPYを区別し、配分最適化の設計上の機構と未確認事項を示してください。架空データであり、実世界の因果証明ではないと明記してください。"""
Q5 = """CROSS_NEGとCROSS_POSを、配賦先会社のsectorで4セクターに分類して比較してください。primary_sector='all'を除外せず、effect_idごとに一度だけ合計し、全額と持分管理のEBITDA影響を億円で示してください。時期の異なるイベントなので回復率とは呼ばないでください。"""


Q_ACT = """2025-10-01～2026-09-30のネガティブイベント（CROSS_NEGを含む5件）について、全額連結EBITDAへの影響が大きかった契約の上位5件と、2件以上のネガティブイベントの影響を受けた契約を、重複を除いて1つの表にまとめ、契約ID、子会社、商品、影響したイベント、影響額（億円）を示してください。primary_sector='all'のCROSS_NEGを除外せず、各effect_idは一度だけ合計し、影響を受けたネガティブイベントの数も示してください。続いて、表の各契約への対応を高、中、低の優先度で提案し、優先度は影響額と、複数のイベントの影響を受けたかで判定して、判定基準も示してください。データから言えることと、仮説としてのアイデアを分け、取引先名はデータにないため作らず、契約IDと商品で示してください。架空データであり、実世界の因果証明ではないと明記してください。"""
DA_ACTION_TEXT = """対応案
高：SUB_FIN_US_01_C08、SUB_FIN_US_01_C07、SUB_FIN_JP_01_C08、SUB_FIN_JP_01_C07

データから言えること：4契約はすべてtrade_financeで、CROSS_NEGとFIN_NEGの両方の影響を受け、-0.43～-0.45億円のマイナスです。
仮説としてのアイデア：契約別の信用枠、担保・ヘッジ条件、例外承認ルールを優先点検し、横断混乱と与信費上昇が同時に発生した場合の早期エスカレーション条件を設定します。
中：SUB_MTL_JP_01_C07

データから言えること：copper_alloyの契約で、CROSS_NEG単独により-0.37億円の影響です。
仮説としてのアイデア：代替調達、在庫バッファ、納期・価格条件の見直しなど、横断的な混乱に耐える契約運用を検討します。
低：SUB_FIN_JP_01_C09、SUB_FIN_US_01_C09

データから言えること：両契約はtrade_financeで、2イベントの影響を受けていますが、影響額は各-0.24億円で上位4契約より小さい水準です。
仮説としてのアイデア：高優先契約で有効性を確認した与信・ヘッジの監視ルールを横展開し、影響拡大時に優先度を引き上げる基準を設けます。"""


def box(slide, x, y, w, h, fill=WHITE, line=None, rounded=False, flat=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor.from_string(fill)
    shp.line.fill.background() if line is None else None
    if line:
        shp.line.color.rgb = RGBColor.from_string(line)
    if rounded:
        shp.adjustments[0] = 0.08
    if flat:
        shp.shadow.inherit = False
    return shp


def text(slide, value, x, y, w, h, size=19, color=INK, bold=False,
         align=None, fill=None):
    if fill:
        box(slide, x, y, w, h, fill)
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(value.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(5)
        p.font.name = FONT
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor.from_string(color)
        if align is not None:
            p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.name = FONT
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = RGBColor.from_string(color)
        rPr = r._r.get_or_add_rPr()
        ea = OxmlElement("a:ea")
        ea.set("typeface", FONT)
        rPr.append(ea)
        rPr.set("lang", "ja-JP")
    return shape


def arrow(slide, x1, y1, x2, y2, color=TEAL, dashed=False):
    c = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = RGBColor.from_string(color)
    c.line.width = Pt(2.2)
    if dashed:
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    tail = OxmlElement("a:tailEnd")
    tail.set("type", "triangle")
    c.line._get_or_add_ln().append(tail)
    return c


def pill(slide, label, x, y, w, url=None, color=TEAL):
    shp = box(slide, x, y, w, .44, color, rounded=True)
    if url:
        shp.click_action.hyperlink.address = url
    t = text(slide, label, x + .13, y + .1, w - .2, .32, 13, WHITE, True)
    if url:
        t.click_action.hyperlink.address = url


def card(slide, x, y, w, h, title, body, accent=TEAL, number=None):
    box(slide, x, y, w, h, WHITE, rounded=True)
    if number:
        text(slide, number, x + .22, y + .18, .65, .52, 30, accent, True)
        tx = x + .98
        tw = w - 1.2
    else:
        tx, tw = x + .25, w - .5
    text(slide, title, tx, y + .22, tw, .48, 22, accent, True)
    text(slide, body, x + .25, y + .95, w - .5, h - 1.03, 18)


def new_slide(title, lead, section, notes, sources, takeaway=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_string(BG)
    n = len(prs.slides)
    text(slide, section, .6, .32, 11.4, .25, 11, TEAL, True)
    text(slide, title, .6, .8, 12.05, .66, 32, NAVY, True)
    text(slide, lead, .62, 1.64, 12.02, .88, 18, MUTED)
    if takeaway:
        box(slide, .6, 6.54, 12.12, .43, PALE, rounded=True)
        text(slide, takeaway, .78, 6.62, 11.78, .29, 13, NAVY, True)
    text(slide, "架空の業務データ／公開ECB為替を使用  |  検証済み構成：2026-10-26",
         .62, 7.12, 11.3, .22, 9, MUTED)
    text(slide, f"{n:02}", 12.17, 7.06, .55, .3, 13, TEAL, True)
    source_text = "\n".join(sources)
    slide.notes_slide.notes_text_frame.text = (
        notes.strip() + "\n\n【出典と照合先】\n" + source_text)
    slide_metadata.append({"slide": n, "title": title, "sources": sources})
    return slide


def dashed_frame(slide, x, y, w, h, color=PURPLE):
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = .05
    shp.fill.background()
    shp.shadow.inherit = False
    shp.line.color.rgb = RGBColor.from_string(color)
    shp.line.width = Pt(1.75)
    shp.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    return shp


def nodes(slide, labels, y=3.2, xs=None, w=2.7, h=1.5, edge_colors=None):
    xs = xs or [.65, 3.8, 6.95, 10.1]
    for i, (title, body, color) in enumerate(labels):
        x = xs[i]
        box(slide, x, y, w, h, WHITE, rounded=True)
        text(slide, title, x + .18, y + .2, w - .36, .42, 20, color, True)
        text(slide, body, x + .18, y + .76, w - .36, .64, 17)
        if i:
            arrow(slide, xs[i - 1] + w + .03, y + h / 2,
                  x - .06, y + h / 2,
                  edge_colors[i - 1] if edge_colors else color)


def prompt_slide(title, question, purpose, expected, sources, size=16,
                 result_note=None, notes_extra=""):
    slide = new_slide(
        title,
        purpose,
        "DAへの入力  |  枠内の全文をコピー",
        "【操作】枠内の文章をすべてコピーし、公開済みFabric DAへ入力します。\n"
        "【入力全文】\n" + question +
        "\n【回答の見方】" + expected +
        "\n【保存結果との区別】" + (result_note or (
            "次ページは保存データから作った照合用の参考結果です。"
            "今回この質問を再実行した回答ではありません。文章やグラフの見た目は変わり得ます。"
            "別途、実際の保存済みDA応答を抜粋したページも収録しています。")) + "\n"
        "【失敗時】対象期間、指標、通貨、件数を確かめます。エラーや欠落を隠して、"
        "参考結果をライブの回答として見せないでください。DAの結果を待つ間は、"
        "質問で何を確かめたいかを説明します。\n"
        "【説明者向け】英文の列名や長いIDを読み上げる必要はありません。"
        "入力する条件を示した後、結果の金額と業務上の意味に注目してもらいます。"
        + notes_extra,
        sources, "次ページ：この入力に対応する参考結果と、営業向けの読み方")
    box(slide, .65, 2.76, 12.02, 3.05, WHITE, rounded=True)
    text(slide, "入力するテキスト（全文）", .9, 2.95, 11.5, .38, 18, TEAL, True)
    text(slide, question, .9, 3.5, 11.5, 2.25, size)
    box(slide, .65, 5.98, 12.02, .43, PALE, rounded=True)
    text(slide, expected, .9, 6.06, 11.5, .3, 15, NAVY)
    pill(slide, "Fabric DAを開く", 10.1, .3, 2.55, DA)
    return slide


# 01
s = new_slide(
    "Trading Ontology デモ説明者ガイド",
    "損益グラフだけでは、食品の損失がどの記録や取引に結び付くかを説明できません。\n金額の比較と、根拠をたどる操作を分けて案内します。",
    "営業向け改訂版  |  基礎 → DA入力と結果 → 根拠の確認",
    """【目安】40秒。これは説明者の準備資料です。全ページをそのまま10分で投影する構成ではありません。基礎解説は事前学習用で、ライブ10分枠とは別です。
【話す】「架空の総合商社を使い、まず損益の変化を見ます。その後、食品損失を一つ選んで、根拠記録や契約と結び付けて確認します。今日見せるのは、数字と説明を同じデータに照らす方法です。」
【指す】3つのカードを順に指し、「概況、イベント、根拠」と読みます。Ontology、GQL、DAGという名前はここでは暗記させません。
【操作】事前に「実演前の制約と確認先」のリンクで公開済みFabric Data AgentとStep03 Notebookを別タブで開きます。今回の作業はローカル資料作成だけで、クラウドの設定変更や再公開は行っていません。
【避ける】実在企業の実データ、実世界の因果分析、自動の原因究明、正式な連結会計の完成版とは言いません。
【つなぎ】「この順序なら、画面の移動も一度で済みます。」""",
    ["config/deployment_manifest.json", "config/step3_deployment.json"],
    "本番前：DAの公開済み画面とNotebookの保存済みHTMLを別タブで確認")
card(s, .6, 2.85, 3.83, 2.96, "全社の概況", "月次の基準値と実績\n年間の全額／持分管理", number="1")
card(s, 4.75, 2.85, 3.83, 2.96, "10イベントの比較", "符号付きの増減\n食品損失を選択", accent=CORAL, number="2")
card(s, 8.9, 2.85, 3.83, 2.96, "食品損失の根拠", "実体の関係をDAGで表示\n記録、活動、契約、KPI", number="3")

# 02
s = new_slide(
    "10分デモの進行と画面切替",
    "自然言語の応答と、関係図の表示は別の画面です。\nDAで金額を確かめてから、食品の実体経路をNotebookで示します。",
    "進行表  |  説明者が手元で参照",
    """【目安】準備時に60秒。下記の時間はライブデモ全体の割当です。
【0:00～1:00】架空データ、対象年度、全額と持分管理を一言で説明します。
【1:00～3:00】公開済みFabric DAにQ1。月次のbaselineとactualの線を指し、年間actual 447.57億円を確認します。年度を本日からの直近1年に置き換えません。
【3:00～5:00】Q2。符号付き棒グラフを指し、横断2件を含めて10件あること、食品損失が約-1.14億円であることを確認します。色や横向きの指定で失敗した場合は、それらを外します。
【5:00～9:00】Q3で食品の要約とIDを確認し、Step03へ一度だけ切り替えます。先頭の保存済みHTML、カード、8ノードのDAG、根拠の原文を順に示します。
【9:00～10:00】関係の共有と金額照合の価値を説明します。余裕がなければ追加質問は実行しません。
【Step04】余裕があれば、DAでQ4（影響点の特定と対応案）を実行します。Q4はNotebookの前後どちらでも実行できます。画面の切替を減らしたい場合は、Q3の直後にDAでQ4を実行してからNotebookへ移ります。
【待ち時間】DAの処理中は「金額を先に確認し、関係は次の画面で確認します」と説明します。無応答時は既存の保存結果／この資料に切り替え、ライブ応答が成功したとは言いません。
【操作】質問全文は「入力①～④」の各スライドの枠内からコピーします。ノートにも全文があります。基礎解説は事前学習用で、10分の実演枠には含めません。""",
    ["prompts/demo_questions_ja.txt", "reports/step3_ui_verification.json"],
    "必須はStep01～03。Step04（影響点と対応案）、ENE_POS、横断比較は時間が余った場合のみ")
rows = [
    ("0～1分", "前提", "架空の8社、対象年度、金額の定義"),
    ("1～3分", "Step01：DA", "月次のbaseline／actual"),
    ("3～5分", "Step02：DA", "全10イベントの符号付き影響"),
    ("5～9分", "Step03：Notebook", "食品の要約 → 保存済みDAG → 根拠"),
    ("9～10分", "締め", "共通の意味、追跡、正確な金額照合"),
]
for i, (tm, screen, purpose) in enumerate(rows):
    y = 2.73 + i * .67
    box(s, .62, y, 12.08, .55, WHITE if i != 3 else PALE, rounded=True)
    text(s, tm, .83, y + .12, 1.3, .3, 17, TEAL, True)
    text(s, screen, 2.25, y + .12, 3.35, .3, 17, INK, True)
    text(s, purpose, 5.72, y + .12, 6.64, .3, 17)

# 03
s = new_slide(
    "架空の8社を同じ尺度で比較",
    "国や事業が異なる会社のデータは、通貨や損益の定義がそのままでは揃いません。\nこのデモはJPYに換算し、全額と持分管理寄与を分けます。",
    "背景  |  最初に共有する業務設定",
    """【目安】45秒。
【話す】「金属、エネルギー、食品、金融の4分野に、日本と米国の会社が1社ずつあります。各社の原本は別のLakehouseに残し、共通の分析用データを用意しています。」
【指す】4セクターの枠を指し、国を跨ぐ比較であることを伝えます。次に年度と通貨、所有比率の欄を指します。
【補足】100%所有は4社、51%所有も4社です。国だけで決めた割当ではありません。全8社は支配子会社という設定なので、51%でも全額ベースの管理デモ集計には100%を取り込みます。一方で持分管理寄与には所有比率を掛けます。法定の連結財務諸表や持分法損益とは区別します。
【実データ】業務、契約、根拠、イベント、価格は架空です。為替だけは公開されたECBの日次観測値を使用しています。USD/JPYはEUR建ての2通貨から計算し、休日は直前観測を最大5日補完します。
【為替の言い方】「為替だけは実データです。ECBが公開している日次の参考レートで、ドル建ての金額を円に換算しています。」
対象年度のUSD/JPYは約146.8円から約163.9円で、期初は147.11円、期末は157.00円です。
【避ける】「実際の市場や業績を反映したデモ」とは言いません。為替が実データでも、会社、取引、金額、イベントは架空です。
ECBの参考レートは公表用の参考値で、企業の決算で使う換算レートではありません。
【つなぎ】「別々の会社のデータを、どこで共通化しているかを見ます。」""",
    ["docs/architecture.md", "config/subsidiaries.json", "data/ecb_fx_raw.csv"],
    "対象年度：2025-10-01～2026-09-30。最新データ日：2026-09-30")
for i, name in enumerate(["金属", "エネルギー", "食品", "金融"]):
    card(s, .62 + i * 3.1, 2.78, 2.78, 1.73, name, "日本1社＋米国1社", accent=TEAL)
box(s, .62, 4.85, 12.07, 1.3, WHITE, rounded=True)
text(s, "通貨", .88, 5.05, 1, .35, 18, TEAL, True)
text(s, "JPY／USD → JPY", 1.95, 5.05, 3.15, .4, 20, INK, True)
text(s, "所有比率", 5.48, 5.05, 1.5, .35, 18, TEAL, True)
text(s, "100%×4社／51%×4社", 7.05, 5.05, 5.1, .4, 20, INK, True)
text(s, "為替は実データ（ECBが公開する日次の参考レート）。会社、契約、金額は架空。", .88, 5.64, 11.2, .3, 16, INK)

# Sales foundations
foundation_notes = """
【使い方】経済や会計を専門にしない営業向けの事前学習ページです。基礎説明を含める場合は
10分枠とは別に時間を取ります。実演中にすべてのページを読む必要はありません。
【注意】ここに置く小さな数値例は概念を説明するための例であり、8社デモの集計結果ではありません。
顧客固有の会計定義を確認せずに、同じ指標名なら同じ計算方法だと説明しないでください。
【話す順】まず日常的な言葉で意味を伝え、次に数値例を指し、最後に今回のデモでの使い方を説明します。
用語の英語名や計算式の暗記は求めません。読者が結果の単位、対象、比較相手を説明できれば十分です。
【対象】今回の業務データは架空です。金額例や関係の説明を、実在企業の業績や実証済みの因果として
外部に説明しないでください。疑問が出た場合は、既存のデータ定義と保存結果に戻って確認します。
"""
s = new_slide(
    "売上とEBITDAの違い",
    "たくさん売れていても、仕入れや運営にお金がかかれば利益は残りません。\n"
    "事業の稼ぎを比べるため、このデモではEBITDA（イービットディーエー）を使います。",
    "営業向け基礎 1  |  金額は説明用の例",
    foundation_notes + """
【話す】「売上100万円だけでは、儲かっているかは分かりません。仕入れ60万円と、人件費など25万円を
差し引くと15万円が残ります。この簡単な例では15万円をEBITDAと考えます。」
【定義】EBITDAは利払い前、税引き前、減価償却前の利益です。一般には営業利益に減価償却費などを
足し戻す見方がありますが、実務では会社ごとの定義と調整項目を確認します。
【減価償却】設備の購入額を使用期間に分けて費用化する会計処理です。その年の現金支出とは一致しません。
【避ける】売上、最終利益、現金残高と同じだと説明しないでください。""",
    ["説明用の単純化した数値例", "docs/architecture.md"],
    "EBITDAは事業の稼ぎを見る指標。最終利益や手元の現金とは別")
nodes(s, [
    ("売上", "100万円\n販売の対価", TEAL),
    ("仕入れ", "−60万円\n仕入れ費用", CORAL),
    ("運営費", "−25万円\n人件費など", CORAL),
    ("EBITDA", "15万円\n事業の稼ぎ", TEAL),
], xs=[.65, 3.84, 7.03, 10.22], w=2.45, h=1.7)
text(s, "EBITDA：利息、税金、減価償却を差し引く前の利益。\n"
     "減価償却は、設備の購入額を使用期間に分けて費用にする会計処理。", .85, 5.35, 11.7, .85, 18, MUTED)

s = new_slide(
    "食品損失によるEBITDAの変化",
    "前ページと同じ例で、食品廃棄により費用が3万円増えた場合を考えます。\n"
    "同じ期間の「損失がない想定」と「損失を反映した結果」を比べます。",
    "営業向け基礎 2  |  前ページの15万円から続く説明用の例",
    foundation_notes + """
【前ページからのつなぎ】「先ほど、売上100万円から仕入れ60万円と運営費25万円を引くと、
EBITDAは15万円でした。では、その事業で食品廃棄が起き、費用が3万円増えたらどうでしょう。」
【話す】「売上と仕入れは変わらず、運営費が25万円から28万円になったとします。
稼ぎは15万円から12万円へ、3万円減ります。比較している金額は、どちらも同じ期間のEBITDAです。」
【用語の順】先に日本語で例を説明してから、「損失がない場合の15万円を基準値、baselineと呼びます。
損失を反映した12万円をこのデモ上の実績、actualと呼びます。両者の差はマイナス3万円、
これが差分、deltaです」と対応付けます。3つの英単語を別の経営指標として暗記させません。
【用語】baselineはこのデモでイベントを加える前の基準値であり、会社の正式な予算を意味しません。
actualはイベント反映後のデモ上の実績です。実在企業から収集した実績という意味ではありません。
【期間】前月と今月の比較ではありません。同じ期間について、イベントがない想定と反映後の値を比較します。
【符号】追加費用はプラス3万円ですが、稼ぎを減らすため、EBITDAへの影響はマイナス3万円です。
【二重計上】actualの12万円には損失がすでに反映されています。さらに3万円を引いて9万円にしません。
【実データとの区別】この食品廃棄の3万円は理解のための説明用で、FOD_NEGの実際のデモ配賦額ではありません。
【実演】年間や月次を比較する際もこの区別を保ちます。丸めと集計粒度で微差が出る場合は照合元に戻ります。""",
    ["前ページから継続する説明用の数値例",
     "data/demo_dataset.json:semantic_financial_metrics_daily", "prompts/da_instructions_ja.txt"],
    "baselineとactualはEBITDAの比較条件。actualの12万円から損失をもう一度引かない")
card(s, .65, 2.85, 3.78, 2.6, "損失なしの稼ぎ",
     "EBITDA 15万円\n基準値（baseline）\n前ページと同じ計算")
card(s, 4.77, 2.85, 3.78, 2.6, "食品廃棄の影響",
     "追加費用 ＋3万円\n稼ぎへの影響 −3万円\n差分（delta）", accent=CORAL)
card(s, 8.89, 2.85, 3.78, 2.6, "損失反映後の稼ぎ",
     "EBITDA 12万円\n実績（actual）\nこのデモ上の呼び方")
text(s, "基準15万円 ＋ 影響（−3万円）＝ 実績12万円",
     .85, 5.67, 11.7, .45, 25, NAVY, True)
text(s, "反映後の計算：売上100万円 − 仕入れ60万円 − 運営費28万円 ＝ EBITDA 12万円",
     .85, 6.17, 11.7, .28, 14, MUTED)

s = new_slide(
    "51%所有の金額を区別",
    "グループ全体の事業規模と、出資割合を掛けた管理上の貢献額は目的が異なります。\n"
    "このデモでは8社すべてを支配子会社として扱います。",
    "営業向け基礎 3  |  子会社EBITDAが1億円の場合",
    foundation_notes + """
【話す】「51%の株式を持つ子会社が1億円を稼いだ場合です。支配子会社として全額を見る指標は1億円。
所有比率を掛ける管理指標は5,100万円です。目的が違うので合計しません。」
【定義】連結は、企業グループを一つのまとまりとして見ることです。実務上の支配の判定は、
単に株式比率だけで決めるものではありません。このデモでは全社FULL_CONTROLという設定です。
【注意】持分管理寄与は簡易指標です。配当、親会社の最終利益、法定の持分法損益ではありません。
残る49%分との差をそのまま非支配株主利益と呼ぶことも避けます。
【全額連結の側も】全額連結EBITDAも、連結財務諸表の数値ではなくデモの管理値です（親会社の費用、税、未実現利益の消去は対象外）。EBITDAは会計基準が定める項目ではないため、「法定連結EBITDA」と言うより「連結財務諸表の数値とは別のデモ用の値」と説明するほうが正確です。
【デモの実数】各社の全額EBITDAに所有割合を掛けて合計すると335.48億円で、全額447.57億円との差は約112.1億円です。この差は、51%の4社のEBITDA（約228.8億円）の49%分に当たります。ただし非支配株主利益そのものではありません。""",
    ["config/subsidiaries.json", "reports/da_qa_published.json"],
    "2つの金額は同じ稼ぎの別の見方。足し合わせない")
card(s, .65, 2.85, 5.83, 2.8, "全額連結：事業全体を見る", "1億円 × 100% ＝ 1億円\n51%所有の子会社も全額を集計\n今回の管理デモ上の扱い")
card(s, 6.85, 2.85, 5.83, 2.8, "持分管理：出資割合で見る", "1億円 × 51% ＝ 5,100万円\n所有比率を反映した簡易的な貢献額\n配当や最終利益ではない", accent=PURPLE)
text(s, "「51%だから、全額連結にも51%を掛ける」という説明はしません。", .85, 5.9, 11.6, .45, 18, MUTED)

s = new_slide(
    "通貨と現金の読み違い",
    "日本円と米ドルをそのまま足したり、利益をそのまま現金と考えたりすると判断がずれます。\n"
    "金額を見るときは、通貨と指標の定義も確認します。",
    "営業向け基礎 4  |  レートは実データ、100万ドルは説明用の例",
    foundation_notes + """
【為替】「100万ドルの稼ぎは、1ドル156.25円なら約1億5,625万円です。事業のドル額が同じでも、
換算レートが変われば円表示は変わります。」100万ドルは説明用の仮の金額です。
156.25円は、デモが実際に使う2026-09-04のレート（ECBの円/ユーロとドル/ユーロから算出した156.24677336円）を丸めた値です。
【レートの幅】対象年度のUSD/JPYは約146.8円から約163.9円まで動きました。同じ100万ドルでも、
円換算は約1億4,700万円から約1億6,400万円の幅になります。
【確認先】DAの検証記録に同じ156.24677336円があります。2026-09-05は土曜のため、前営業日2026-09-04の値を1日補完した適用です。
休日は直前値を最大5日まで補完し、補間や将来レートの推測はしていません。
【避ける】「実際の市場や業績を反映したデモ」とは言いません。為替が実データでも、会社、取引、金額は架空です。
ECBの参考レートは公表用の参考値で、企業の決算で使う換算レートではありません。
【CF】キャッシュフローは、一定期間に現金がどのように増減するかという見方です。
商品を売って売上や利益が立っても、代金の入金が翌月ならその時点で現金はまだ増えていません。
【今回のCF】EBITDAの80%を起点にイベントのCF効果を加えた簡易シミュレーションです。
正式な営業CFやフリーCFとして説明しないでください。""",
    ["data/ecb_fx_raw.csv", "reports/da_qa_final_draft.json"],
    "主役はEBITDA。CFは補足の簡易値として説明")
card(s, .65, 2.85, 5.83, 2.8, "為替：共通の通貨に換算", "100万ドル × 156.25円/ドル\n＝ 約1億5,625万円\n2026-09-04のデモの実レート\n出典：ECB公開の日次参考レート")
card(s, 6.85, 2.85, 5.83, 2.8, "CF：現金の増減", "売上が立っても、入金は翌月の例\n利益と現金の動きは一致しない\n今回のCFは簡易シミュレーション", accent=PURPLE)
text(s, "億円の換算：1億円＝100,000,000円 ／ 0.01億円＝100万円", .85, 5.9, 11.6, .45, 18, MUTED)

# 04
s = new_slide(
    "原本を分離した分析構成",
    "会社ごとの原本と、共通の意味付けや集計のためのデータを区別します。\nすべてをゼロコピーで処理する構成ではありません。",
    "構成  |  データ参照と実体照会を区別",
    """【目安】60秒。
【話す】「左が8社の原本です。上の経路は共通の分析用投影で、ここには実データのコピーを作っています。下の経路は業種別の拡張表だけをゼロコピーで参照する8つのショートカットです。両者を同じものとして説明しないでください。」
【指す】左、中央の上下、右の順です。親LakehouseはSAP風の管理データも持ち、子会社8個と合わせて9個です。物理表95個とショートカット8個を足して物理表103個とは数えません。
【Ontology】共通の実体名と関係を定義し、各表へ対応付けます。その定義からGraphModelをマテリアライズしています。GraphModelは参照可能な実体のグラフで、NotebookはそこへGQLを実行します。
【DA】構成上のソースはOntologyと親Lakehouseの論理参照面です。DAの金額質問ではSQL集計が確認されています。すべての質問が自動的にGQLへ流れるという主張はしません。
【更新】投影、GraphModel、保存HTMLはそれぞれ更新タイミングが別です。原本の変更が即座にすべてへ反映するとは約束しません。
【つなぎ】「ここで登場した4つの用語を食品の例に置き換えます。」""",
    ["docs/architecture.md:81-123", "config/deployment_manifest.json"],
    "ゼロコピーは業種拡張8表への参照。semantic_*投影とGraphModelは実体化")
card(s, .62, 2.92, 2.45, 2.8, "子会社原本", "8 Lakehouse\n会社ごとに分離\n\n親を含め計9個")
card(s, 3.66, 2.8, 3.24, 1.55, "共通の分析用投影", "分析用コピーを生成")
card(s, 3.66, 4.68, 3.24, 1.45, "業種別拡張の参照", "8表をゼロコピー参照")
arrow(s, 3.1, 3.56, 3.59, 3.56, TEAL)
arrow(s, 3.1, 5.27, 3.59, 5.27, MUTED, True)
box(s, 7.47, 2.8, 2.33, 3.33, PALE, rounded=True)
text(s, "Ontology", 7.7, 3.04, 1.95, .4, 23, TEAL, True)
text(s, "実体と関係の定義\n＋表への対応付け", 7.7, 3.61, 1.9, 1.1, 17)
text(s, "GraphModel\n実体化したグラフ", 7.7, 4.94, 1.9, .85, 17, TEAL, True)
arrow(s, 6.95, 3.56, 7.4, 3.56)
arrow(s, 6.95, 5.27, 7.4, 5.27)
card(s, 10.34, 2.8, 2.36, 1.55, "Fabric DA", "金額集計／説明")
card(s, 10.34, 4.68, 2.36, 1.45, "Notebook", "GQL経路＋DAG")
arrow(s, 9.83, 3.56, 10.27, 3.56)
arrow(s, 9.83, 5.27, 10.27, 5.27)

# 05
s = new_slide(
    "4つの用語を食品の例で区別",
    "「Ontology」と「画面に見える図」は同じものではありません。\n定義、照会対象、表示方法を分けると説明の範囲が明確になります。",
    "用語  |  名前より役割を説明",
    """【目安】45秒。
【話す】「Ontologyは、契約や活動が何を意味し、どう関係するかの共通定義です。GraphModelには、今回の契約や活動といった実際のレコードがノードと関係として入っています。」
【指す】左上から右上、左下、右下へ。グラフ一般は点と線からなる構造で、線のつながりをたどれます。DAGは向きがあり、ぐるっと一周して戻る閉路がない図です。
【このデモ】Ontologyに17種類の実体と39種類の関係を定義しています。GraphModelの実体照会では33,960ノードと65,684エッジを検証していますが、表示はその全体ではありません。食品の代表1活動に関連する8ノード、7矢印を選んでDAGにしています。
【避ける】GraphModel全体がDAGである、Ontologyが因果推論モデルである、グラフを描けば因果が証明できる、という説明はしません。
【つなぎ】「用語を知ったら、操作はまず金額の比較からです。」""",
    ["reports/step3_live_audit.json:diagram_relations", "config/deployment_manifest.json"],
    "画面のDAGは、取得した関係のうち代表1活動を選んだ部分図")
card(s, .62, 2.73, 5.86, 1.59, "Ontology：共通定義", "例：「活動は契約に属する」という関係")
card(s, 6.83, 2.73, 5.86, 1.59, "GraphModel：実体の照会対象", "例：ある販売活動と小麦契約のレコード")
card(s, .62, 4.67, 5.86, 1.59, "グラフ：点と線の構造", "例：活動、契約、根拠を関係で結ぶ")
card(s, 6.83, 4.67, 5.86, 1.59, "DAG：向きがあり閉路のない図", "例：食品の8ノード／7矢印を表示")

prompt_slide(
    "入力① 年間と月次の稼ぎ",
    Q1,
    "まず全社の稼ぎを見て、増減のあった月を確認します。\n"
    "グラフの崩れと集計の取り違いを防ぐ指定を含みます。そのままコピーできます。",
    "見る点：2本の月次線、年間actualの全額447.57億円と持分管理335.48億円",
    ["Q1: 本ファイルのコピー用質問", "reports/da_qa_published.json"],
    notes_extra="\n【Q1の文面】期間合計をグラフに含めず12か月だけにする、縦軸を億円にする、横軸を年月の文字列にする指定は、"
    "実行時の崩れ（期間合計の混入、縦軸のB表記、時刻軸で1点だけ）を避けるためです。"
    "説明者の実行で、期待どおりの表示を確認済みです（2026-10-26）。")

# 06
monthly = defaultdict(lambda: defaultdict(Decimal))
for r in dataset["semantic_financial_metrics_daily"]:
    if r["metric_code"] == "EBITDA":
        monthly[r["metric_date"][:7]][r["scenario_tag"]] += Decimal(r["amount_group"])
s = new_slide(
    "Step01は基準値と実績の比較",
    "増減の理由を質問する前に、対象年度と指標を固定します。\n持分比率を掛けた金額は、全額連結とは別の管理指標です。",
    "入力①に対応する参考結果  |  保存データから再作成",
    """【目安】ライブ2分。資料の説明は45秒。
【話す】「まず対象年度の全社損益を見ます。baselineがイベントを加える前の基準値、actualが配賦済みの実績です。DAに月次の折れ線比較を依頼します。」
【操作】公開済みFabric DAでQ1を貼り付けます。質問全文は直前の「入力①」スライドとノートにあります。
【指す】月次の2系列を指して期間を確認し、年間actualの全額447.57億円と持分管理335.48億円を区別します。このページの線は保存された元データから再作成した編集可能な参考グラフで、DA画面のスクリーンショットではありません。
【金額】全額44,757,399,732.84円。持分管理33,547,898,914.09円。どちらもactualのみです。51%子会社も全額側では100%を取り込みます。
【避ける】持分管理の差額をそのまま非支配株主利益と呼ぶ、actualにイベント差分をもう一度加える、baselineとactualを合算すること。
【DAの出力が崩れた場合】よくある崩れは3つです。①期間合計がグラフの13個目の点として入り、月次の線が平らになる。②縦軸が億円ではなく「B（10億円）」表記になる。③横軸が時刻軸になり、1点しか表示されない。Q1はこれらを避ける文面にしてありますが、実行ごとに結果は変わります。崩れた場合の追い指示は「期間合計をグラフから外し、12か月だけ、縦軸を億円にして作り直してください」です。それでも崩れる場合は、このページの参考グラフを使い、DAの応答は数値の確認に使います。
【つなぎ】「この変化にどのイベントが配賦されているか、10件を比較します。」
【コピー用Q1】\n""" + Q1,
    ["data/demo_dataset.json:semantic_financial_metrics_daily",
     "reports/da_qa_published.json"],
    "参考グラフは元データから再作成。DAの応答や表示形式はその場で確認")
chartdata = CategoryChartData()
chartdata.categories = [m[2:] for m in sorted(monthly)]
for scenario, label in [("baseline", "baseline"), ("actual", "actual")]:
    chartdata.add_series(label, [float(monthly[m][scenario] / Decimal(10**8))
                                for m in sorted(monthly)])
ch = s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(.64), Inches(2.85),
                        Inches(7.45), Inches(3.3), chartdata).chart
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.font.size = Pt(12)
for series, color in zip(ch.series, [MUTED, TEAL]):
    series.format.line.color.rgb = RGBColor.from_string(color)
    series.format.line.width = Pt(2.5)
ch.category_axis.tick_labels.font.size = Pt(11)
ch.value_axis.tick_labels.font.size = Pt(11)
ch.value_axis.has_title = True
ch.value_axis.axis_title.text_frame.text = "億円"
text(s, "年間actual／全額", 8.65, 2.94, 3.82, .4, 18, TEAL, True)
text(s, "447.57 億円", 8.65, 3.51, 3.9, .65, 33, NAVY, True)
text(s, "年間actual／持分管理", 8.65, 4.51, 3.82, .4, 18, TEAL, True)
text(s, "335.48 億円", 8.65, 5.08, 3.9, .65, 33, NAVY, True)

prompt_slide(
    "入力② 増減の理由を比較",
    Q2,
    "全社の稼ぎを押し上げた出来事と、押し下げた出来事を比べます。\n"
    "イベントとは、損益に影響を与える「出来事」です。",
    "見る点：全10件、プラスとマイナス、食品損失FOD_NEGの約−1.14億円",
    ["Q2: 本ファイルのコピー用質問", "reports/qa_expected_event_totals.json"])

# 07
order = ["MTL_NEG", "MTL_POS", "ENE_NEG", "ENE_POS", "FOD_NEG", "FOD_POS",
         "FIN_NEG", "FIN_POS", "CROSS_NEG", "CROSS_POS"]
labels = ["製錬停止", "再生合金", "LNG遅延", "配分最適化", "食品損失",
          "調達改善", "与信費増", "ヘッジ手数料", "横断混乱", "横断回復"]
s = new_slide(
    "Step02は10イベントの増減",
    "損失だけを見ると、好影響や横断イベントを取りこぼします。\n短い項目名を使い、正負の符号と億円の単位で比較します。",
    "入力②に対応する参考結果  |  保存データから再作成",
    """【目安】ライブ2分。資料の説明は45秒。
【話す】「全10イベントの配賦額です。マイナスは損益の押し下げ、プラスは押し上げです。食品損失は約-1.14億円なので、この事例を詳しく確認します。」
【指す】ゼロ線、食品損失、横断混乱と横断回復の順です。固有8件と横断2件の計10件であることを確認します。
【操作】Q2は短い日本語ラベルと符号付き億円を指定し、色や縦横は指定しません。この環境では赤青や横棒を厳密に指定した要求が失敗し、制約を外すとネイティブな縦棒が生成されました。長い名称は切れたため短いラベルにしています。製品の普遍的制約という意味ではありません。
【この図】出典の確定額で再作成した参考図です。棒と文字は編集可能なPowerPoint図形です。DAの実画面キャプチャではなく、表示色や配置を保証するものでもありません。ラベルに対応するevent_idと円単位の値は「10イベントの照合用金額」にあります。ローカルのLibreOfficeではネイティブ棒グラフの負数描画に問題があったため、符号に忠実な図形描画へ切り替えています。
【避ける】横断回復÷横断混乱を回復率と呼ぶこと。異なる時期の設計イベントです。棒の値をactualへ再加算しません。
【横断とは】「他の8件は1つの業種（2社）だけに起きる出来事です。この2件は、4業種すべて（8社）に同時に影響します。業種をまたぐので『横断』と呼んでいます。」横断混乱は、港の混乱と資金繰りの悪化が業種を問わず起きた想定（2026年5月）で、コストが増え、EBITDAを約6.80億円押し下げます。横断回復は、物流と資金管理が改善し、全業種で取扱量が増えた想定（2026年9月）で、約5.84億円押し上げます。
【大きく見える理由】1件あたりの影響は他のイベントと同程度（約140〜250万円）です。合計が大きいのは、2社ではなく8社に当たるためです（336効果対84効果）。
【回復の意味】横断回復は、5月の混乱からの回復ではなく、別に設計した独立の好影響イベントです。
【与信費増の訳】FIN_NEGの原文はcounterparty servicing cost shockで、取引先対応コストの急増を指す設計です。ラベルの「与信費増」は短くした呼び名で、貸倒関連の与信費用を意味しません。金融に詳しいお客様には、この点を一言添えます。
【つなぎ】「食品の金額は分かりました。どの記録や販売活動と結び付いているかは、次の画面で確認します。」
【コピー用Q2】\n""" + Q2,
    ["reports/qa_expected_event_totals.json", "data/demo_dataset.json:semantic_risk_events"],
    "各effect_idは一度だけ集計。primary_sector='all'の横断2件を除外しない")
text(s, "全額EBITDA影響（億円）／元データから再作成", .92, 2.65, 8.8, .3, 14, MUTED)
zero, scale, chart_x, chart_w = 4.46, .17, 1.06, 8.64
for tick in [-8, -4, 0, 4, 8]:
    y = zero - tick * scale
    box(s, chart_x, y, chart_w, .012, MUTED if tick == 0 else GRAY)
    text(s, f"{tick:+d}".replace("-", "−") if tick else "0", .65, y - .1, .35, .22, 10, MUTED)
for i, (eid, label) in enumerate(zip(order, labels)):
    value = float(Decimal(events[eid]["full_jpy"]) / Decimal(10**8))
    x = chart_x + i * chart_w / 10 + .13
    height = abs(value) * scale
    y = zero - height if value > 0 else zero
    box(s, x, y, .5, height, CORAL if value < 0 else TEAL)
    text(s, f"{value:+.2f}".replace("-", "−"), x - .125,
         y - .27 if value > 0 else y + height + .035,
         .75, .23, 10, CORAL if value < 0 else TEAL, True, PP_ALIGN.CENTER)
    category = label if label != "ヘッジ手数料" else "ヘッジ\n手数料"
    text(s, category, x - .16, 6.01, .82, .43, 9.5, INK, False, PP_ALIGN.CENTER)
text(s, "選ぶ事例", 10.2, 3.05, 2.4, .4, 18, TEAL, True)
text(s, "食品損失", 10.2, 3.64, 2.4, .4, 23, NAVY, True)
text(s, "−1.14", 10.2, 4.25, 2.4, .7, 38, CORAL, True)
text(s, "億円／FOD_NEG", 10.2, 5.04, 2.5, .4, 17, MUTED)
frame_x = chart_x + 8 * chart_w / 10 - .02
dashed_frame(s, frame_x, 3.0, 1.66, 3.3, PURPLE)
text(s, "横断", frame_x, 2.7, .9, .24, 11, PURPLE, True)
text(s, "点線の枠は横断。\n4業種の8社すべてに影響。\n他の8件は1業種の2社。", 10.2, 5.58, 2.5, .85, 12.5, INK)

prompt_slide(
    "入力③ 食品損失の根拠",
    Q3,
    "食品損失について「どの記録、販売、契約とつながるか」を確認します。\n"
    "図はDAに作らせず、この後のNotebookで示します。",
    "見る点：全額−1.1446億円、持分管理−0.8763億円、84効果、根拠と取引のID",
    ["Q3: 本ファイルのコピー用質問", "reports/step3_live_audit.json"],
    notes_extra="\n【代表効果の固定】Q3は代表効果をeffect_idの昇順で先頭に固定します。固定しないと、DAが「最も負の1件」を代表に選び、"
    "Notebookの図と別の効果（SUB_FOD_US_01_A135_1_FOD_NEG_F、2026-02-13）を返すことがあります。"
    "全社KPI IDも、代表効果と同じ日付のものを指定しています（指定しないと、最新日のKPIを返した例があります）。"
    "2026-10-26に公開済みDAで、この文面が図と同じ代表効果（SUB_FOD_JP_01_A133_0_FOD_NEG_F、2026-02-11）、ID、金額を返すことを確認しました。")

s = new_slide(
    "食品損失の回答を読む",
    "食品損失によって、期間全体の稼ぎがどれだけ押し下げられたかを見ます。\n"
    "「84効果」は損益への影響明細の数で、84件の事故という意味ではありません。",
    "入力③に対応する参考結果  |  保存監査値を要約",
    foundation_notes + """
【回答の位置づけ】このページは保存されたGraph照会とDeltaの金額照合結果から再構成した参考結果です。
Q3を今回DAで実行した応答の転載ではありません。金額とIDの照合に使用します。
【説明】「食品の損失イベント全体で、EBITDAを約1.14億円押し下げています。
その説明に使う代表例として、2月11日の日本食品会社の販売活動と小麦契約を確認します。」
【効果】84件のeffect_idを一度ずつ集計しています。代表1明細の金額を84倍して全体を求めません。
【根拠】根拠は合成業務ログです。温度と廃棄率の観測はありますが、温度が腐敗を起こしたという
実世界の因果の証明ではありません。IDは同じ記録を照合するための目印として示します。
【次の操作】Notebookで保存済みHTMLを開き、日時と図の関係を確認します。
【DAでの確認】Q3の最終版は、2026-10-26に公開済みDAで実行し、このページと同じ代表効果、ID、金額が返ることを確認しました。""",
    ["reports/step3_live_audit.json:exact_*,representative_path"],
    "営業の説明例：「稼ぎの減少額から、関連する販売と根拠記録まで確認できます」")
card(s, .65, 2.8, 3.78, 1.75, "全額の影響", "−1.1446億円\n約1億1,446万円の押し下げ", accent=CORAL)
card(s, 4.77, 2.8, 3.78, 1.75, "持分管理の影響", "−0.8763億円\n所有比率を反映した額", accent=PURPLE)
card(s, 8.89, 2.8, 3.78, 1.75, "影響明細の件数", "84効果\n重複のないeffect_id", accent=TEAL)
box(s, .65, 4.75, 12.02, 1.65, WHITE, rounded=True)
text(s, "代表例：2026-02-11／日本食品会社の外部販売／製粉用小麦", .9, 4.88, 11.5, .35, 16, NAVY, True)
text(s, "根拠：SUB_FOD_JP_01_FOD_NEG_0    活動：SUB_FOD_JP_01_A133_0\n"
     "契約：SUB_FOD_JP_01_C04    効果：SUB_FOD_JP_01_A133_0_FOD_NEG_F\n"
     "日次指標：SUB_FOD_JP_01_2026-02-11_ebitda_actual\n"
     "全社KPI：2026-02-11_EBITDA_FULL_CONSOLIDATED_actual",
     .9, 5.3, 11.5, 1.02, 12.5, MUTED)

# 08
s = new_slide(
    "Step03で食品損失の経路を表示",
    "DAでは食品の金額とIDを短く確認し、図は専用Notebookへ移ります。\n最初に見せるのは、実行日時を持つ保存済みのHTML出力です。",
    "ライブ操作  |  Step03 Notebookの先頭",
    """【目安】60秒。
【話す】「この図は、Ontologyから作ったGraphModelへ実際にGQLを実行して得た関係を表示しています。根拠、対象活動、契約、財務指標を一緒に確認できます。」
【操作】DAにQ3を入力し、要約とIDだけを確認します。その後、Step03 Notebookタブへ一度切り替えます。名前はTradingDemo_03_食品損失のOntology経路とDAG。先頭の保存済みHTMLを開き、上部3カードとDAGを表示します。表示だけなら実行不要です。
【指す】上段の左から根拠、イベント、1効果、会社日次EBITDA、次に右下の全社日次EBITDA。下段の温度記録、活動、契約にも注目してもらいます。8ノードと7矢印ですが、GQLで得た全関係を全部描いているわけではありません。
【画像の由来】このスライドは実行済み出力として保存されたローカルSVGをブラウザ表示し、そのまま撮影した画像です。FabricのUIを模造したスクリーンショットではありません。
【保存時点】2026-10-26 01:25:34 UTC、10:25:34 JST。いま画面を開いた時刻と同一ではありません。保存結果の閲覧と、現在のGraphの再照会を区別します。
【避ける】「この画像を開いた瞬間にGraphを再取得している」「DAがDAGを生成した」とは説明しません。
【コピー用Q3】\n""" + Q3 + "\n【Notebook】\n" + NOTEBOOK,
    ["reports/step3_food_loss_dag.svg", "reports/step3_live_audit.json",
     "reports/step3_ui_verification.json"],
    "図は実行済みSVGのローカル撮影。NotebookのクラウドUI画像ではない")
image = HERE / "actual_saved_dag.png"
from PIL import Image
iw, ih = Image.open(image).size
w = 8.7
h = w * ih / iw
s.shapes.add_picture(str(image), Inches(.65), Inches(2.57), width=Inches(w), height=Inches(h))
text(s, "イベント全体", 9.79, 2.81, 2.83, .36, 18, TEAL, True)
text(s, "-1.1446", 9.79, 3.34, 2.83, .65, 32, CORAL, True)
text(s, "億円／84効果", 9.79, 4.03, 2.83, .4, 17, MUTED)
text(s, "図は代表1活動\n8ノード／7矢印", 9.79, 4.74, 2.83, .9, 18, NAVY, True)
pill(s, "Notebookを開く", 9.79, 5.89, 2.64, NOTEBOOK)

# 09
s = new_slide(
    "矢印は3種類の意味を持つ",
    "つながった線をすべて「原因から結果」と読むと、説明を誤ります。\nこのDAGには根拠の関連、設計上の配賦、指標への対応が混在します。",
    "Step03の読み方  |  関係名を日本語で説明",
    """【目安】45～60秒。
【話す】「灰色は記録や対象との関連、紫はこの架空デモで設計した配賦、緑は日次指標への対応や集約先です。すべての線が実証された因果を表しているわけではありません。」
【指す】根拠からイベント、イベントから効果、効果から会社日次、会社日次から全社日次へと上段を読みます。
【方向】図の実際の向きを守ります。効果から活動へEffectOnActivity、活動から契約へActivityUnderContractです。「根拠→活動→契約」は説明の確認順としては使えますが、その通りの矢印列が図にあるとは言いません。
【省略】GQLではEffectExplainedByEvidence、EffectOnContract、EventImpactsActivityも確認済みですが、図では非循環で読みやすい部分だけを示しています。取得クエリは複数の条件を同時に検証しており、図はその要約です。
【財務】効果の差分、会社の日次総額、全社の日次総額が線でつながっても、3つを加算するという意味ではありません。
【つなぎ】「まず財務金額以外の記録を読み、何が言えて何が言えないかを確認します。」""",
    ["reports/step3_live_audit.json:diagram_relations",
     "scripts/step3_food_loss_runtime.py:197-267"],
    "説明用の再構成図。矢印の方向は保存された実関係に合わせて記載")
nodes(s, [
    ("根拠記録", "架空の業務ログ", MUTED),
    ("食品イベント", "FOD_NEG", PURPLE),
    ("財務効果", "代表1件の差分", PURPLE),
    ("会社日次指標", "actualの総額", TEAL)],
    xs=[.65, 3.84, 7.03, 10.22], w=2.45, h=1.5,
    edge_colors=[MUTED, PURPLE, TEAL])
text(s, "根拠の関連", 2.58, 2.8, 1.95, .3, 13, MUTED)
text(s, "設計した配賦", 5.73, 2.8, 1.95, .3, 13, PURPLE)
text(s, "指標との対応", 8.93, 2.8, 2.1, .3, 13, TEAL)
box(s, .66, 5.04, 12.02, 1.06, WHITE, rounded=True)
text(s, "灰色：関連", .9, 5.27, 3.25, .4, 20, MUTED, True)
text(s, "紫：影響の配賦", 4.82, 5.27, 3.5, .4, 20, PURPLE, True)
text(s, "緑：対応と集約", 8.81, 5.27, 3.5, .4, 20, TEAL, True)

# 10
s = new_slide(
    "代表記録から読める範囲",
    "食品損失という名称だけで、温度逸脱や腐敗原因までは断定できません。\n図に出ている値と、データに存在しない条件を分けて説明します。",
    "Step03の説明  |  根拠、販売活動、契約",
    """【目安】60秒。
【話す】「代表例は2026年2月11日の日本食品会社の外部販売です。観測値はマイナス18度、廃棄率3.5%です。契約の商品コードはmilling_wheat、図では製粉用小麦と表示されています。」
【指す】Notebookの下段にある観測、活動、契約。次に根拠記録の原文欄を指します。
【厳密な注意】許容温度や契約上の閾値は記録にありません。「マイナス18度だから高温障害」「小麦が冷凍必須」といった現実世界の知識で補完しません。これはデモ用に生成したデータで、商品と温度の組合せも原記録のままです。
【根拠】SIM://SUB_FOD_JP_01/FOD_NEG/operations_logという合成業務ログで、原文にもSYNTHETICと書かれています。これが実在の監査証憑という意味ではありません。
【ID】活動SUB_FOD_JP_01_A133_0、契約SUB_FOD_JP_01_C04、根拠SUB_FOD_JP_01_FOD_NEG_0です。長いIDは口頭で読み上げず、下のリネージ表にあることを示します。
【日付】イベント期間は2月9日～3月1日、代表活動と効果は2月11日。イベント開始日と個別の効果日を同一視しません。
【つなぎ】「同じ図に出てくる4つの金額は、対象範囲が異なります。」""",
    ["reports/step3_live_audit.json:representative_path,cold_chain_observation",
     "reports/da_qa_published.json"],
    "許容温度、閾値超過、実世界の腐敗原因は未記録。説明者の推測で補わない")
card(s, .63, 2.79, 3.78, 2.91, "観測記録", "-18.0 ℃\n廃棄率 3.5%\n2026-02-11")
card(s, 4.77, 2.79, 3.78, 2.91, "販売活動と契約", "日本の食品会社\n外部販売\n製粉用小麦")
card(s, 8.91, 2.79, 3.78, 2.91, "根拠の性質", "SIM:// の架空ログ\nSYNTHETICを明記\n設計したcost影響", accent=CORAL)

# 11
s = new_slide(
    "4つの金額は合算しない",
    "イベントの影響額と、日次の損益総額は集計の粒度が違います。\n損失イベントがあっても、当日の全社EBITDAはプラスになり得ます。",
    "Step03の説明  |  数字の読み違いを防止",
    """【目安】60秒。ここは質疑で最も間違えやすい箇所です。
【話す】「左上は食品損失イベント全体。右上はその中の1効果。左下はその会社の同日全体の実績、右下は8社の同日全体の実績です。見えている4つの金額を足してはいけません。」
【指す】4枠を順に指します。イベント全体は84個のeffect_idをそれぞれ一度だけ合計した-114,461,186.25円。持分管理なら-87,630,294.31円です。
【代表効果】SUB_FOD_JP_01_A133_0_FOD_NEG_F、-3,003,488.94円。この会社の所有比率は51%で、代表効果の持分管理は-1,531,779.36円です。
【当日】会社actual EBITDAは+3,711,231.19円。8社actual EBITDAは+113,069,201.90円。どちらも2026-02-11です。これらは損失の額ではなく、ほかの取引も含んだその日の総額です。
【精度】画面の億円表記は丸めています。厳密な照合は下の円表示や監査JSONを使います。効果粒度と日次粒度の換算丸めに微差があり得るため、別粒度の差を機械的に不整合と断定しません。
【避ける】「全社は1.13億円の損失」「84効果×代表効果＝全体」「actualにdeltaを追加」。
【つなぎ】「関係の取得と金額の照合を別処理にすることで、この違いを保ちます。」""",
    ["reports/step3_live_audit.json:exact_*"],
    "上段はイベント差分、下段は日次actual総額。対象範囲を必ず添えて発話")
values = [
    (.64, 2.75, "イベント全体／84効果", "-114,461,186.25 円", "期間全体のFOD_NEG", CORAL),
    (6.86, 2.75, "代表する1効果", "-3,003,488.94 円", "2026-02-11／日本食品会社", PURPLE),
    (.64, 4.65, "同日の会社EBITDA", "+3,711,231.19 円", "2026-02-11／会社actual総額", TEAL),
    (6.86, 4.65, "同日の全社EBITDA", "+113,069,201.90 円", "2026-02-11／全8社actual総額", TEAL),
]
for x, y, title, amount, sub, color in values:
    box(s, x, y, 5.83, 1.58, WHITE, rounded=True)
    text(s, title, x + .22, y + .15, 5.4, .34, 18, color, True)
    text(s, amount, x + .22, y + .62, 5.4, .46, 26, color, True)
    text(s, sub, x + .22, y + 1.18, 5.4, .3, 13, MUTED)

# 12
s = new_slide(
    "関係照会と金額照合を分離",
    "グラフは関係や経路の確認に使い、厳密な金額はDECIMALで計算します。\n画面上の一つの結果に、役割の異なる二つの確認処理を合わせています。",
    "実装説明  |  技術質問が出たときに使用",
    """【目安】60秒。非技術者にはカード見出しだけで十分です。
【話す】「NotebookはGQLで本物の関係を読み、その84効果がDelta側の84効果と一致するかを調べます。金額計算は小数を正確に扱うDECIMALを使用します。」
【指す】左のGraph経路と右のDelta金額、下の一致検査です。
【Graph】OntologyからマテリアライズされたGraphModelに対して公開Graph APIのbeta GQLを実行しています。定義そのものに未提供の実体APIを呼んだり、SQL JOINをGQLと呼び換えたりしていません。
【金額】Sparkでsemantic_event_financial_effects、semantic_financial_metrics_daily、kpi_snapshotのDelta DECIMALを読取専用で照合します。Graphの数値は浮動小数点なので、厳密な会計集計の唯一の根拠にはしません。84 effect_idの集合が一致し、全84金額が小数点以下2桁で一致しました。
【選択】代表はeffect_id順で決定しており、都合のよい値を手作業で書いた図ではありません。食品観測の実関係も追加GQLで取得します。
【停止条件】認証失敗、空結果、取得上限到達、ID不一致、金額不一致では停止します。古い静的な図をライブ結果の代わりに表示して成功扱いにはしません。
【認証】Notebook実行時にnotebookutils.credentials.getToken('pbi')を利用。デッキやソースにトークンは埋め込みません。原本とGraphは読取専用ですが、HTML出力は自分自身の新Notebookへ保存します。
【つなぎ】「説明者は通常、実行ではなく保存結果を開くところから始めます。」""",
    ["scripts/step3_food_loss_runtime.py:85-182",
     "reports/step3_live_audit.json"],
    "認証失敗、空結果、ID不一致、金額不一致では停止。静的な成功図に代替しない")
card(s, .64, 2.79, 5.83, 2.4, "GQL：実体と関係", "GraphModelに2回照会\n食品の84効果と関係を取得\n代表1活動の観測も取得")
card(s, 6.86, 2.79, 5.83, 2.4, "Spark：金額を正確に照合", "DeltaのDECIMAL値を参照\n効果、会社日次、全社日次を区別\neffect_idを重複なく集計")
arrow(s, 3.56, 5.25, 3.56, 5.68)
arrow(s, 9.77, 5.25, 9.77, 5.68)
box(s, 1.48, 5.75, 10.37, .5, PALE, rounded=True)
text(s, "84効果のID集合と金額の一致 → 代表経路のHTML／SVGを保存", 1.7, 5.87, 9.94, .3, 17, TEAL, True)

# 13
s = new_slide(
    "Notebookは保存結果から開始",
    "説明中に再実行を待つ必要がないように、HTMLを先頭に残しています。\n最新のGraphを読み直す操作は、保存結果の閲覧と分けて行います。",
    "操作手順  |  HTML先頭の設計を維持",
    """【目安】60秒。実演前は必ず手元で一度確認します。
【通常表示】①正しいNotebookを開く。②先頭の保存済みHTMLを表示。③読取日時を確認。④上部カード、DAG、根拠原文、必要ならID表の順に指します。表示だけなら「すべて実行」を押しません。
【保存とライブ】最初の表示セルはDEMO_HTMLがセッションにあればそれを表示します。ない場合のコード上の案内と、ファイルに保存された過去の出力は別です。後段runtimeが実GQLを照会し、自Notebookの先頭出力へ結果を保存する設計です。最初のセルが先に走ることは、この配置を変える理由にはしません。
【更新】更新が必要な場合だけ「すべて実行」を1回押し、完了を待ちます。完了後、画面の状態に応じて先頭表示セルを再表示するかNotebookを開き直し、日時が更新されたかを確認します。自動で必ず先頭が最新表示になるとは約束しません。
【失敗時】エラーを確認し、再実行の連打を避けます。読取認証、Graphの利用可否、データ照合などを切り分けます。保存結果を続けて使うなら「こちらは保存時点の結果です」と明示します。権限変更やGraph再生成、DA再公開をその場で試みません。
【現状】2026-10-26の実行完了後、セルを走らせずに開き直した画面で8ノード7矢印と金額、日時の可視性を検証済みです。Notebookそのもののフロントエンド状態まで毎回同じとは保証しません。
【つなぎ】「最後に、業務で使う場合の価値を一言で説明します。」
【直接リンク】\n""" + NOTEBOOK,
    ["scripts/build_step3_notebook.py:39-64", "scripts/step3_food_loss_runtime.py",
     "reports/step3_ui_verification.json"],
    "更新操作は必要時だけ1回。保存時点の結果を現在時点のライブ結果と呼ばない")
card(s, .63, 2.78, 3.78, 2.99, "通常の説明", "Notebookを開く\n先頭HTMLと日時を確認\nそのまま図を説明", number="1")
card(s, 4.77, 2.78, 3.78, 2.99, "最新値への更新", "「すべて実行」を1回\n完了後に再表示／再読込\n日時と結果を確認", number="2")
card(s, 8.91, 2.78, 3.78, 2.99, "エラーの場合", "実行の連打を避ける\n未検証範囲を明示\n保存結果なら日時を告知", accent=CORAL, number="3")

# Step04: impact points and action ideas
con_by_id = {c["contract_id"]: c for c in dataset["semantic_contracts"]}
co_names = {c["entity_id"]: c["entity_name"] for c in dataset["semantic_company_profile"]}
neg_by_contract = defaultdict(lambda: {"amount": Decimal(0), "events": set()})
for r in dataset["semantic_event_financial_effects"]:
    if r["event_id"].endswith("_NEG"):
        neg_by_contract[r["contract_id"]]["amount"] += Decimal(r["delta_ebitda_full_jpy"])
        neg_by_contract[r["contract_id"]]["events"].add(r["event_id"])
ranked = sorted(neg_by_contract, key=lambda cid: neg_by_contract[cid]["amount"])
scope = [cid for cid in ranked
         if cid in ranked[:5] or len(neg_by_contract[cid]["events"]) >= 2]
da_tier = {"SUB_FIN_US_01_C08": "高", "SUB_FIN_US_01_C07": "高", "SUB_FIN_JP_01_C08": "高",
           "SUB_FIN_JP_01_C07": "高", "SUB_MTL_JP_01_C07": "中",
           "SUB_FIN_JP_01_C09": "低", "SUB_FIN_US_01_C09": "低"}
assert set(scope) == set(da_tier), scope
neg_total = sum(v["amount"] for v in neg_by_contract.values())
top5_share = abs(sum(neg_by_contract[c]["amount"] for c in ranked[:5]) / neg_total) * 100
assert (len(con_by_id), len(neg_by_contract), round(top5_share)) == (96, 48, 16)

prompt_slide(
    "入力④ 影響点の特定と対応案",
    Q_ACT,
    "影響額を確認しただけでは、どこから手を打つかは決まりません。\n"
    "影響額に加え、複数のイベントの影響を受けた契約を見て、優先順位を付けます。",
    "見る点：7契約、うち6契約が2回影響、最大は金融の−0.43〜−0.45億円、優先度の基準",
    ["Q4: 本ファイルのコピー用質問", "data/demo_dataset.json:semantic_event_financial_effects"],
    size=15,
    result_note=(
        "次ページの表は元データから再作成した参考結果、その次のページの対応案は2026-10-26に公開済みDAでQ4を実行した応答の要約です。"
        "実行ごとに文面や優先度の分け方は変わります。"),
    notes_extra=(
        "\n【期待する表（7行）】SUB_FIN_US_01_C08 −0.4535（28件、2イベント）、SUB_FIN_US_01_C07 −0.4365（27件、2イベント）、"
        "SUB_FIN_JP_01_C08 −0.4345（28件、2イベント）、SUB_FIN_JP_01_C07 −0.4283（28件、2イベント）、"
        "SUB_MTL_JP_01_C07 −0.3714（14件、1イベント）、SUB_FIN_JP_01_C09 −0.2371（16件、2イベント）、"
        "SUB_FIN_US_01_C09 −0.2356（17件、2イベント）。単位は億円です。"
        "\n【優先度】高、中、低はDAの判断です。判定基準が文章で出ているか確認します。"
        "\n【取引先】データに取引先名はありません。DAには作らせず、契約IDと商品で示します。"
        "取引先名まで見せるには、架空の取引先マスタを追加してOntologyとグラフを更新する必要があります（今回は未実施）。"
        "\n【順序】Q4はNotebookの前後どちらでも実行できます。画面の切替を減らしたい場合は、Q3の直後にDAでQ4を実行してからNotebookへ移ります。"
        "\n【Q4の文面】primary_sector='all'の除外防止、effect_idを一度だけ合計する指定、取引先名を作らせない指定は、"
        "過去の誤り（横断イベントの除外、重複集計、名称の捏造）を避けるためです。"))

s = new_slide(
    "影響が大きい契約と繰り返し影響を受けた契約",
    f"ネガティブ5件の影響は{len(con_by_id)}契約中{len(neg_by_contract)}契約に広がり、上位5件でも全体の約{top5_share:.0f}%です。\n"
    "2回影響を受けた契約を加えると、優先して見る先を絞れます。",
    "入力④に対応する参考結果  |  表は元データから再作成、優先度はDA実行例",
    """【目安】60秒。
【話す】「食品損失の次に、どの契約から手を打つかを考えます。5つのマイナスのイベントを契約ごとに通算すると、影響は96契約中48契約に広く薄く散り、上位5件でも全体の約16%です。そこで、複数のイベントの影響を受けた契約にも注目します。」
【指す】優先度の列と、右端の「回数」の列です。金融子会社2社のtrade_finance契約（C07、C08）は、与信費増（FIN_NEG）と横断混乱（CROSS_NEG）の2回の影響を受け、各−0.43〜−0.45億円と最大です。
【時期】2回の影響は同時期ではありません。FIN_NEGは4月中旬〜5月初め、CROSS_NEGは5月中旬〜下旬に、約2週間あけて続けて当たっています。
【優先度】高、中、低はDAの判断です。判定基準が画面に出ているか確認します。実行例では、額が大きく2回影響を受けた4契約を高、額は大きいが1回だけのSUB_MTL_JP_01_C07を中、2回影響を受けたが額が小さいC09の2契約を低としました。3位と4位の差は約63万円で、実質同じ水準です。
【金額】SUB_FIN_US_01_C08 −0.4535、SUB_FIN_US_01_C07 −0.4365、SUB_FIN_JP_01_C08 −0.4345、SUB_FIN_JP_01_C07 −0.4283、SUB_MTL_JP_01_C07 −0.3714、SUB_FIN_JP_01_C09 −0.2371、SUB_FIN_US_01_C09 −0.2356（億円、全額連結EBITDAへの影響）です。
【避ける】取引先名を口にしません（データにありません）。優先度を、取るべき対応の確定順位と説明しません。与信費増を、貸倒関連の与信費用と説明しません。
【つなぎ】「では、それぞれの契約に対して、どんな対応が考えられるでしょうか。」""",
    ["data/demo_dataset.json:semantic_event_financial_effects,semantic_contracts",
     "説明者の公開済みDA実行例（優先度の列）、2026-10-26"],
    "取引先名はデータにない。契約IDで特定し、実務では取引先マスタにつなぐ")
tier_color = {"高": CORAL, "中": PURPLE, "低": MUTED}
cols = [("優先度", .83, .8), ("契約ID", 1.7, 2.5), ("子会社", 4.25, 2.7), ("商品", 7.0, 1.5),
        ("影響したイベント", 8.55, 2.0), ("影響額（億円）", 10.55, 1.5), ("回数", 12.1, .55)]
for label, x, w in cols:
    text(s, label, x, 2.68, w, .3, 13, TEAL, True)
for i, cid in enumerate(scope):
    y = 3.05 + i * .4
    if i % 2 == 0:
        box(s, .67, y - .07, 12.0, .38, WHITE, flat=True)
    info = neg_by_contract[cid]
    tier = da_tier[cid]
    vals = [tier, cid, co_names[con_by_id[cid]["entity_id"]], con_by_id[cid]["commodity"],
            ", ".join(sorted(info["events"], reverse=True)),
            f"{info['amount'] / Decimal(10**8):.4f}".replace("-", "−"), str(len(info["events"]))]
    for j, ((label, x, w), val) in enumerate(zip(cols, vals)):
        text(s, val, x, y, w, .3, 12.5, tier_color[tier] if j == 0 else (CORAL if j == 5 else INK), j == 0)
text(s, "表は、上位5件と、2件以上のイベントの影響を受けた契約を重複なく並べた7契約です。",
     .85, 6.02, 11.7, .3, 13, MUTED)

s = new_slide(
    "優先度別の対応案（DA実行例）",
    "影響点が分かっても、打つ手は事実だけからは決まりません。\n"
    "DAは、データから言えることと、仮説としてのアイデアを分けて出します。",
    "入力④に対応する応答  |  説明者の実行例（2026-10-26）を要約",
    """【目安】60秒。
【位置づけ】このページの文面は、説明者が2026-10-26に公開済みDAでQ4を実行した応答（対応案の部分）の要約です。実行ごとに文面は変わります。
【話す】「データから言えることと、仮説としてのアイデアを分けて出しています。アイデアはあくまで仮説で、実行を決めるのは担当者です。」
【指す】高、中、低の順に、各カードの「データから言えること」、次に「仮説としてのアイデア」を指します。
【取引先】データには取引先名がないため、契約IDで示しています。実務では取引先マスタを契約につなぎ、取引先単位で見ます。
【実運用】過去の対応事例（Foundry IQ）や担当者とのやり取り（Work IQ）と組み合わせると、一般論ではなく自社の対応の型になります。通知やタスク化は実運用の発展として説明し、このデモの範囲外とします。
【避ける】アイデアを実証済みの対策や因果の証明と言いません。「与信費上昇」は与信費増（FIN_NEG）の言い換えで、貸倒関連の与信費用ではありません。
【実行例の原文】\n""" + DA_ACTION_TEXT,
    ["説明者の公開済みDA実行例（対応案の部分）、2026-10-26",
     "data/demo_dataset.json:semantic_event_financial_effects"],
    "次の1歩：高の4契約について、信用枠、担保・ヘッジ条件の現状を担当者に確認する")


def action_card(slide, x, y, w, h, tier, ids, fact, idea, accent):
    box(slide, x, y, w, h, WHITE, rounded=True)
    text(slide, tier, x + .22, y + .16, w - .44, .42, 20, accent, True)
    text(slide, ids, x + .22, y + .62, w - .44, .5, 10.5, MUTED)
    text(slide, "データから言えること", x + .22, y + 1.14, w - .44, .26, 12.5, TEAL, True)
    text(slide, fact, x + .22, y + 1.42, w - .44, .85, 13)
    text(slide, "仮説としてのアイデア", x + .22, y + 2.3, w - .44, .26, 12.5, PURPLE, True)
    text(slide, idea, x + .22, y + 2.58, w - .44, 1.0, 13)


for k, (tier, ids, fact, idea, accent) in enumerate([
    ("高：金融の4契約", "SUB_FIN_US_01_C08, SUB_FIN_US_01_C07\nSUB_FIN_JP_01_C08, SUB_FIN_JP_01_C07",
     "4契約ともtrade_finance\nCROSS_NEGとFIN_NEGの両方の影響\n各0.43〜0.45億円の押し下げ",
     "契約別の信用枠、担保・ヘッジ条件、例外承認ルールを優先点検し、早期エスカレーション条件を設定する。", CORAL),
    ("中：金属の1契約", "SUB_MTL_JP_01_C07",
     "copper_alloy契約\nCROSS_NEGのみ\n0.37億円の押し下げ",
     "代替調達、在庫バッファ、納期・価格条件の見直しなど、横断的な混乱に耐える契約運用を検討する。", PURPLE),
    ("低：金融の2契約", "SUB_FIN_JP_01_C09, SUB_FIN_US_01_C09",
     "trade_finance契約で2イベントの影響\n各0.24億円の押し下げ\n上位4契約より小さい",
     "高優先契約で有効性を確認した監視ルールを横展開し、影響拡大時に優先度を引き上げる基準を設ける。", MUTED),
]):
    action_card(s, .65 + k * 4.07, 2.68, 3.9, 3.65, tier, ids, fact, idea, accent)

# 14
s = new_slide(
    "説明の価値と追加質問",
    "同じ数値をSQL JOINで求めること自体は可能です。\nこのデモは、会社を跨ぐ意味や関係を共有し、金額と根拠を照合する例です。",
    "締め  |  誇張せず伝える業務価値",
    """【目安】45秒。10分枠の最後に使います。
【話す】「ここで共有したのは、金額の定義と、どの根拠や取引を参照しているかです。説明者は同じ関係をたどって答えを確認できます。金額は別の正確な集計で照合します。」
【指す】3つのカード。定義の統一、根拠への追跡、異なる集計粒度の区別という業務上の利点を述べます。
【SQL比較】Snowflakeや一般的なSQL JOINでも同じ数値を作れます。OntologyだけがJOINできる、SQLでは不可能、という比較はしません。関係と意味を再利用できることに価値があります。
【追加A】余裕があればDAへ戻り、ENE_POSの好影響を同じ確認順で質問します。全額+210,155,445.28円、約+2.10億円。Step03はFOD_NEG専用なのでイベントIDを変えてエネルギー図を作ろうとはしません。
【追加B】横断2件を配賦先sectorで比較します。primary_sector='all'を落とさずに会社のsectorで分けます。負と正の時期が違うため、単純な回復率とは説明しません。
【避ける】画面操作を自動業務判断や本番会計の完成形と結び付けること。因果の証明、全面ゼロコピー、自動最新化とも言いません。
【コピー用追加A】\n""" + Q4 + "\n【コピー用追加B】\n" + Q5,
    ["docs/architecture.md:112-143", "reports/qa_expected_event_totals.json"],
    "次の確認：別イベントでも同じ定義と根拠の確認順を再利用できるか")
card(s, .63, 2.79, 3.78, 2.8, "指標定義の共有", "全額／持分管理を区別\nactual／baselineを区別\nJPYで比較")
card(s, 4.77, 2.79, 3.78, 2.8, "根拠までの追跡", "イベントの説明\n活動と契約の確認\n原記録とIDを参照")
card(s, 8.91, 2.79, 3.78, 2.8, "照合可能な説明", "GQLで関係を取得\nDECIMALで金額照合\n粒度の違いを明示")
text(s, "任意の追加：ENE_POSの好影響 ／ CROSS_NEGとCROSS_POSのセクター比較",
     .83, 5.95, 11.7, .36, 16, MUTED)

# 15
s = new_slide(
    "コピー用質問の使い分け",
    "質問全文は本編の「入力①～④」ページに、編集できる文字として掲載しています。\n"
    "各入力の次に参考結果を置き、ノートにも同じ全文を残しています。",
    "付録A  |  入力と参考結果の対応",
    """【準備用】PowerPointのノートペイン／発表者ツールでこのページを開きます。
【実行順】Q1 → Q2 → Q3 → Q4。Q4はNotebookの前後どちらでも実行できます。画面の切替を減らしたい場合は、Q3の直後にDAでQ4を実行してからNotebookへ移ります。本編の入力ページにはコピー可能な全文があります。この付録の4行は対応を確認するための要約です。
【表示の経験】現在の環境ではMermaidはコードブロックのまま、Pythonによる任意DAG画像の生成表示も利用できない旨の回答でした。DA一般や将来の機能を一律に否定する意味ではありません。棒グラフは色や横向きを強く指定すると失敗し、制約を外した縦棒が成功しました。短い項目名を使います。グラフ成功は毎回確認が必要です。
【実演先】Fabric DAの公開済み画面です。M365 CopilotはDA結果を再構成するため、同じグラフが通過表示される保証はありません。このデモではM365側の表示成功を主張しません。
【Q1全文】\n""" + Q1 + "\n\n【Q2全文】\n" + Q2 + "\n\n【Q3全文】\n" + Q3 + "\n\n【Q4全文】\n" + Q_ACT
    + "\n\n【DA直接リンク】\n" + DA,
    ["prompts/demo_questions_ja.txt", "prompts/da_instructions_ja.txt",
     "説明者の現在環境での表示確認（色と配置は未固定）"],
    "実演先はFabric DA。M365 Copilotで同じグラフが表示される保証はない")
for i, (a, b, c) in enumerate([
    ("Q1", "月次のbaseline／actual", "折れ線＋年間actualの全額／持分管理"),
    ("Q2", "10イベントの影響", "短いラベル＋符号付き億円の棒グラフ"),
    ("Q3", "食品損失の要約とID", "代表効果を固定。図の生成は依頼しない"),
    ("Q4", "影響点と対応案", "契約別の影響額＋優先度付きの対応案"),
]):
    y = 2.75 + i * .92
    box(s, .65, y, 12.04, .75, WHITE, rounded=True)
    text(s, a, .89, y + .15, .8, .45, 24, TEAL, True)
    text(s, b, 2.0, y + .17, 4.45, .4, 21, INK, True)
    text(s, c, 6.8, y + .2, 5.55, .4, 16, MUTED)
pill(s, "Fabric DAを開く", 10.1, .3, 2.55, DA)

# 16
s = new_slide(
    "10イベントの照合用金額",
    "棒グラフの短いラベルは、必ず元のevent_idと対応付けます。\n丸めた億円表示の照合には、円単位の確定額を使います。",
    "付録B  |  全額EBITDAへの設計上の影響配賦",
    """【準備用】ライブ回答が異なる場合の照合表です。取得に失敗した回答を、この表で差し替えて成功したとは言いません。
【読み方】各行はeffect_idを一度だけ集計した全額JPYのdeltaです。actualに追加する金額ではありません。固有イベントは各84効果、横断イベントは各336効果、合計1,344効果です。
【短いラベル】製錬停止=smelter outage、再生合金=recycled alloy premium contract、LNG遅延=LNG terminal maintenance delay、配分最適化=storage dispatch optimization、食品損失=cold chain spoilage incident、調達改善=grain yield and procurement improvement、与信費増=counterparty servicing cost shock、ヘッジ手数料=hedge execution fee uplift、横断混乱=cross-sector port and liquidity disruption、横断回復=cross-sector logistics and treasury recovery。いずれも架空の設計です。
【重複防止】evidenceをevent_idだけで結合すると金額が根拠件数倍になります。effect.evidence_idで結ぶか、効果を重複なく確定してから合計します。日次指標を活動件数倍に加算することも避けます。
【食品の持分管理】-87,630,294.31円。表の全額-114,461,186.25円とは指標が異なります。
【日付】CROSS_NEGは2026年5月、CROSS_POSは9月のイベントです。両者の比率を施策の回復率や同条件の効果比較とは呼びません。
【与信費増の訳】FIN_NEGの原文はcounterparty servicing cost shockで、取引先対応コストの急増を指す設計です。ラベルの「与信費増」は短くした呼び名で、貸倒関連の与信費用を意味しません。""",
    ["reports/qa_expected_event_totals.json", "data/demo_dataset.json:semantic_risk_events"],
    "sector固有は84効果×8件、横断は336効果×2件。合計1,344効果")
colxs = [.83, 3.18, 6.02, 9.34, 11.32]
widths = [2.3, 2.7, 3.1, 1.85, 1.1]
for x, w, label in zip(colxs, widths, ["event_id", "短いラベル", "全額影響（円）", "億円", "効果数"]):
    text(s, label, x, 2.71, w, .32, 14, TEAL, True)
for i, (eid, label) in enumerate(zip(order, labels)):
    y = 3.13 + i * .305
    if i % 2 == 0:
        box(s, .67, y - .02, 12, .305, WHITE)
    amount = Decimal(events[eid]["full_jpy"])
    vals = [eid, label, f"{amount:+,.2f}", f"{amount / Decimal(10**8):+.4f}", str(events[eid]["effects"])]
    for x, w, val in zip(colxs, widths, vals):
        text(s, val, x, y, w, .28, 13, CORAL if amount < 0 else INK)

# 17
s = new_slide(
    "想定質問への短い回答",
    "細部を推測して答えると、実装が確認した範囲を超えてしまいます。\n短い回答のあと、必要な場合だけノートの補足を使います。",
    "付録C  |  説明者用FAQ",
    """【Q：全部ゼロコピー？】A：「いいえ。ゼロコピーは業種拡張8表のショートカットです。親のsemantic_*は分析用の実体化コピー、GraphModelもマテリアライズしています。」
【Q：SQLでもできる？】A：「同じ集計は可能です。ここでは実体名、関係、根拠の確認方法を共有することを示しています。」他製品を結合不能と表現しません。
【Q：線があるなら原因と証明できる？】A：「できません。合成のログと設計した配賦を結んでいます。線には関連や集約先の意味もあります。」現実で因果を論じるには別のデータや検証設計が必要です。
【Q：51%なら半分だけ連結？】A：「このデモは全社が支配子会社なので、全額指標には100%を取り込みます。比率を掛けた方は別の持分管理寄与です。」正式な会計処理一式を再現しているわけではありません。
【Q：食品の温度が原因？】A：「観測値は-18℃ですが、許容温度や閾値は未記録です。原因として断定せず、架空の設計例として説明します。」
【Q：今の画面は最新？】A：「表示しているのは読取日時付きの保存結果です。最新のGraphを読む場合は再実行し、完了と表示日時を確認します。」GraphModel自体の更新時点も別です。
【Q：金融にも出荷がある？】A：「金融はexposureや手数料の活動を使います。存在しない物理出荷は補完しません。」
【Q：なぜマイナスの損失とプラスのKPIが同じ図に？】A：「前者はイベントの差分、後者は他の取引も含む当日の総額だからです。」
【Q：Notebookはデータを書き換える？】A：「原本とGraphは読取専用です。自Notebookの定義には、実行したHTML/SVGと監査出力を保存します。」全操作が完全な無書込みという説明もしません。
【Q：イベントのデータは社内にない？】A：「整った形では、ないのが普通です。差分の理由コメントや事故・契約の記録、業務データの異常から拾い、小さな台帳から始めます。」詳細は付録Fにあります。
【Q：取引先の名前は出せる？】A：「このデモのデータに取引先名はありません。契約IDで特定し、実務では取引先マスタを契約につなぎます。」""",
    ["docs/architecture.md", "reports/step3_live_audit.json",
     "scripts/step3_food_loss_runtime.py"],
    "答えが未確認なら「未検証」と明示。温度の閾値や因果を補完しない")
faqs = [
    ("全部ゼロコピー？", "拡張8表の参照だけ。投影とGraphは実体化。"),
    ("SQLでもできる？", "可能。意味と関係の共有がOntologyの価値。"),
    ("矢印は因果の証明？", "関連、設計上の配賦、集約先を区別。"),
    ("51%なら半分を連結？", "全額は100%。持分管理とは別指標。"),
    ("温度が損失の原因？", "閾値は未記録。観測値から断定しない。"),
    ("開くだけで最新？", "保存出力。更新時は実行と日時を確認。"),
    ("イベントのデータは社内にない？", "差分の理由や事故の記録から拾い、小さく始める。"),
]
for i, (q, a) in enumerate(faqs):
    y = 2.76 + i * .5
    box(s, .65, y, 12.04, .42, WHITE, rounded=True)
    text(s, q, .86, y + .07, 4.2, .33, 16, TEAL, True)
    text(s, a, 5.19, y + .07, 7.23, .33, 16)

# 18
s = new_slide(
    "実演前の制約と確認先",
    "検証済みのデモ動作と、本番の製品保証やライセンス要件は別です。\n画面とノートを手元で確認し、未検証の条件は説明に含めません。",
    "付録D  |  リンク、制約、事前点検",
    """【事前点検】公開済みDAを開き、Notebookの先頭HTMLと日時を確認します。PowerPointの発表者ノートが見えるか、画面切替ができるか、ネットワークとFabric利用権限があるかを確認します。必要な権限がなければ管理者へ通常の手順で確認し、この資料から共有設定を変更しません。
【実行環境】実際のDA runtimeはPreviewです。別のBasic-plan設定は発見も検証もしていません。要求したBasic条件を満たしたと説明したり、ライセンス準拠を認証済みと表現したりしません。GQLの公開Graph APIもbetaです。
【日本語】日本語応答はこのデモで動作確認したbest-effortです。公式な日本語サポート保証として説明しません。
【会計】全額と所有比率付き管理寄与を区別します。CFはEBITDAの80%を起点にイベントCFを足した簡易シミュレーションで、正式な営業CFやフリーCFではありません。税、非支配持分、資本連結、在庫未実現利益などは対象外です。
【チャネル】公開済みFabric DAを実演先にします。M365 Copilotへの公開はOFFで、結果を再構成する場合のグラフ表示は未保証です。
【PowerPoint表示】このファイルは編集可能な図形とネイティブグラフを使い、日本語にYu Gothicを指定しています。ローカル描画で点検していますが、Windows PowerPointなど実際に使う環境でのフォント、改行、ノート表示の最終確認をお願いします。
【リンク】\nDA：""" + DA + "\nNotebook：" + NOTEBOOK + "\nOntology：" + ONTOLOGY
    + "\nWorkspace：" + WORKSPACE
    + "\n【今回の範囲】ローカル資料作成のみ。Fabric変更、共有、送信、GitHub操作は行いません。",
    ["config/deployment_manifest.json:limitations", "config/step3_deployment.json",
     "docs/architecture.md:135-144"],
    "本番前に使用環境のPowerPointで日本語フォント、改行、ノート、リンクを最終確認")
card(s, .65, 2.78, 5.84, 2.82, "検証した範囲", "Fabric DAの公開済み日本語QA\n実GraphのGQL照会と金額照合\nNotebookの保存出力の再表示")
card(s, 6.84, 2.78, 5.84, 2.82, "保証しない範囲", "Basic-planの個別条件\n日本語の公式サポート保証\n正式会計／実世界の因果証明", accent=CORAL)
for label, x, w, link in [
    ("Fabric DA", .85, 2.2, DA),
    ("Step03 Notebook", 3.42, 2.82, NOTEBOOK),
    ("Ontology", 6.62, 2.2, ONTOLOGY),
    ("Workspace", 9.2, 2.54, WORKSPACE)]:
    pill(s, label, x, 5.9, w, link)

published = json.loads((PROJECT / "reports/da_qa_published.json").read_text())
saved_question = published["messages"][0]["content"][0]["text"]
saved_answer = published["messages"][1]["content"][0]["text"]
s = new_slide(
    "保存済みDA応答の実例",
    "ここは再作成グラフではなく、実際に保存されたDAの入力と応答の抜粋です。\n"
    "本編の入力①と②をまとめた、数値確認用の質問です。",
    "付録E  |  公開済みDAの保存記録",
    foundation_notes + "\n【保存された入力全文】\n" + saved_question +
    "\n【保存されたDA応答全文】\n" + saved_answer +
    "\n【注意】過去の実行記録であり、この改訂作業中のライブ応答ではありません。"
    "スライド本文では読みやすさのため回答の一部だけを引用しています。全文はこのノートに残しています。",
    ["reports/da_qa_published.json:messages[0:2]"],
    "入力全文と応答全文をノートに収録。保存時点の回答であり、今回の再実行結果ではない")
box(s, .65, 2.77, 5.83, 3.46, WHITE, rounded=True)
text(s, "実際に入力したテキスト（全文）", .9, 2.98, 5.3, .4, 18, TEAL, True)
text(s, saved_question, .9, 3.58, 5.3, 2.3, 17)
box(s, 6.85, 2.77, 5.83, 3.46, PALE, rounded=True)
text(s, "実際の回答（原文の一部を抜粋）", 7.1, 2.98, 5.3, .4, 18, TEAL, True)
text(s, "対象期間は2025-10-01〜2026-09-30（両端含む）、シナリオはactualです。"
     "\n\n全額連結EBITDA：\n44,757,399,732.84円（約447.57億円）"
     "\n持分管理寄与EBITDA：\n33,547,898,914.09円（約335.48億円）",
     7.1, 3.58, 5.3, 2.3, 16)

s = new_slide(
    "社内にないイベントを集める方法",
    "イベントを一覧にしたデータは、多くの会社でまだ整っていません。\n"
    "既にある文書と業務データから拾い、小さな台帳として育てます。",
    "付録F  |  お客様データへの当てはめ",
    """【目安】準備用。お客様から「そんなデータは社内にない」と言われたときに使います。
【話す】「整ったイベントデータが最初から社内にないのは普通です。デモの10件は構造を見せるための設計データで、実際は既にある文書や業務データから拾います。」
【拾い先】①差分の理由コメント：月次の予算・見通しとの差異分析、経営会議や営業会議の資料に「何が起きたか」が文章で書かれていることが多く、最も手軽です。②事故や契約の記録：事故やクレームの報告、納期遅延、フォースマジュールや契約変更の通知。③業務データの異常：納期遅延、価格の乖離、歩留り、与信格付の変更などをルールで検知し、出来事の候補にします。④外部情報：ニュース、港湾や気象、地政学リスクの情報。
【進め方】差分から始める：デモのStep01のように基準値と実績の差を出し、差が大きい月と会社だけ「何が起きたか」を聞いて登録します。全部は網羅しません。実務ではbaselineを予算や見通しに置き換えます。下書きはAI、承認は人：文書から候補をAIで抽出し、担当者が確認して登録します。元の文書の権限や秘密度ラベルを引き継ぐ設計が前提です。最初は20〜30件：過去1〜2年の主要な出来事を、既存の資料から棚卸しします。
【単独と横断】別の種類として管理せず、1つの台帳に、影響を受ける会社、商品、地域、契約を紐づけます。複数の業種に及ぶものを横断と判定します。このデモはprimary_sector='all'で簡略化しています。
【金額の注意】実務では、イベントが原因だと証明することはできません。「根拠との紐づけ」と「影響額の推定」を分けて持ち、推定には方法（予算差異の配賦、前後比較など）と確度を添えます。デモの金額は設計値です。
【実装の例（案）】台帳はFabricのLakehouseかSharePointリスト。登録はTeamsやForms。異常検知はFabricのEventhouseとActivator。文書からの候補抽出はCopilotやエージェント。いずれも提案段階の構成で、このデモでは実装していません。
【避ける】「このデモのイベントが実際に社内にある」「AIが原因を特定する」と言いません。""",
    ["提案段階の構成（このデモでは未実装）", "data/demo_dataset.json:semantic_risk_events"],
    "影響額は推定とし、方法と確度を添える。実務ではbaselineを予算や見通しに置き換える")
text(s, "拾い先", .65, 2.62, 5.9, .34, 17, TEAL, True)
for i, (a, b) in enumerate([
    ("差分の理由コメント", "予実差異の分析、経営会議・営業会議の資料"),
    ("事故と契約の記録", "事故・クレーム報告、納期遅延、フォースマジュール、契約変更の通知"),
    ("業務データの異常", "納期遅延、価格の乖離、歩留り、与信格付の変更をルールで検知"),
    ("外部情報", "ニュース、港湾や気象、地政学リスクの情報"),
]):
    y = 3.02 + i * .68
    box(s, .65, y, 5.9, .6, WHITE, rounded=True)
    text(s, a, .82, y + .16, 1.95, .3, 14, TEAL, True)
    text(s, b, 2.78, y + (.17 if len(b) <= 21 else .08), 3.65, .45, 12, INK)
text(s, "進め方", 6.85, 2.62, 5.8, .34, 17, TEAL, True)
for i, (n_, a, b) in enumerate([
    ("1", "差分から始める", "基準値と実績の差が大きい月と会社だけ、理由を聞いて登録する。"),
    ("2", "下書きはAI、承認は人", "文書から候補をAIで抽出し、担当者が確認して登録する。"),
    ("3", "最初は20〜30件", "過去1〜2年の主要な出来事を、既存の資料から棚卸しする。"),
]):
    y = 3.02 + i * .9
    box(s, 6.85, y, 5.84, .8, WHITE, rounded=True)
    text(s, n_, 7.03, y + .15, .4, .45, 22, TEAL, True)
    text(s, a, 7.55, y + .07, 5.0, .3, 14, INK, True)
    text(s, b, 7.55, y + .37, 5.0, .42, 12, INK)
box(s, .65, 5.9, 12.04, .5, WHITE, rounded=True)
text(s, "単独と横断：影響を受ける会社、商品、地域、契約を台帳に紐づけ、複数の業種に及ぶものを横断と判定する。",
     .85, 6.02, 11.65, .3, 13, NAVY)

# Keep the business walkthrough together and place implementation material in the appendix.
for technical_title in ["原本を分離した分析構成", "4つの用語を食品の例で区別", "関係照会と金額照合を分離"]:
    technical_index = next(i for i, meta in enumerate(slide_metadata) if meta["title"] == technical_title)
    technical_slide_id = prs.slides._sldIdLst[technical_index]
    prs.slides._sldIdLst.remove(technical_slide_id)
    prs.slides._sldIdLst.append(technical_slide_id)
    slide_metadata.append(slide_metadata.pop(technical_index))
for i, (slide, meta) in enumerate(zip(prs.slides, slide_metadata), 1):
    meta["slide"] = i
    for shape in slide.shapes:
        if shape.has_text_frame and shape.left == Inches(12.17) and shape.top == Inches(7.06):
            shape.text_frame.paragraphs[0].runs[0].text = f"{i:02}"

assert len(prs.slides) == 31
prs.save(OUT)
(HERE / "slide_sources.json").write_text(
    json.dumps(slide_metadata, ensure_ascii=False, indent=2))
prompt_catalog = [
    ("Q1 年間と月次の稼ぎ", Q1),
    ("Q2 増減の理由を比較", Q2),
    ("Q3 食品損失の根拠", Q3),
    ("Q4 影響点の特定と対応案", Q_ACT),
    ("追加A ENE_POSの好影響", Q4),
    ("追加B 横断2件のセクター比較", Q5),
    ("Q1が崩れた場合の追い指示",
     "期間合計をグラフから外し、12か月だけ、縦軸を億円にして作り直してください。"),
]
(PROJECT / "prompts" / "presenter_prompts_ja.txt").write_text(
    "公開済みFabric Data Agentへ入力する質問の全文です。説明者ガイド（decks/）の入力①～④と同じ内容で、"
    "presentation/build_presenter_deck.py から生成されます。\n\n" +
    "\n\n".join(f"【{name}】\n{body}" for name, body in prompt_catalog) + "\n")
(QA / "slide_text_and_notes.txt").write_text(
    "\n\n".join(
        f"=== SLIDE {i} ===\n" +
        "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame) +
        "\n[NOTES]\n" + slide.notes_slide.notes_text_frame.text
        for i, slide in enumerate(prs.slides, 1)))
print(f"Saved {OUT} ({len(prs.slides)} slides)")
