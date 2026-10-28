"""Build the Japanese customer-facing Ontology deck from the verified Trading demo artifacts.

Run with python3 (python-pptx, Pillow and budoux are required; budoux breaks Japanese lines at phrase
boundaries). Writes decks/TradingOntology_Customer_Deck_JA.pptx
and presentation/customer_slide_sources.json. No Fabric API is called. Every figure on a slide is computed
from data/ and reports/ and asserted, nothing is typed in by hand. The data is synthetic; only the FX rates
are real ECB reference rates. The deck holds no workspace links, tenant identifiers or customer names.
"""
from collections import defaultdict
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import json
import re
import shutil
import tempfile
from pathlib import Path
import zipfile

import budoux
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OUT = PROJECT / "decks" / "TradingOntology_Customer_Deck_JA.pptx"
SOURCES_JSON = HERE / "customer_slide_sources.json"
OUT.parent.mkdir(exist_ok=True)


def load(path):
    return json.loads((PROJECT / path).read_text())


subsidiaries = load("config/subsidiaries.json")
dataset = load("data/demo_dataset.json")["LH_Group_SAP"]
events = load("reports/qa_expected_event_totals.json")
audit = load("reports/step3_live_audit.json")
fix = load("reports/da_traversal_fix_2026-10-27.json")
wide = load("reports/da_group_wide_2026-10-27.json")
graph_paths = {r["event_id"]: int(r["effects_with_complete_path"])
               for r in load("reports/graph_all_event_paths.json")["result"]["data"]}
node_counts = {r["entity_type"]: r["instance_count"]
               for r in load("reports/graph_node_counts.json")["result"]["data"]}
edge_counts = {r["relationship_type"]: r["edge_count"]
               for r in load("reports/graph_edge_counts.json")["result"]["data"]}
cloud = load("reports/cloud_validation.json")
app = load("reports/whatif_app_live_verification_2026-10-28.json")

OKU = Decimal(10) ** 8
MINUS = "\u2212"


def oku(v, places="0.01"):
    return (v / OKU).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def fmt(v, places="0.01", sign=True):
    """Format a JPY amount in oku-yen with a real minus sign."""
    d = len(places.split(".")[1])
    s = format(oku(v, places), f"+.{d}f" if sign else f".{d}f")
    return s.replace("-", MINUS)


def num(v, places="0.01"):
    """Format an already-in-oku number."""
    return format(Decimal(str(v)).quantize(Decimal(places), rounding=ROUND_HALF_UP), "+.2f").replace("-", MINUS)


# ---- ontology structure (types) -------------------------------------------------------------------------
ONT = PROJECT / "ontology_tmdl"
entity_names, relationships = [], []
for f in sorted((ONT / "entities").glob("*.tmdl")):
    entity_names.append(re.search(r"^entity (\w+)", f.read_text(), re.M).group(1))
for block in re.split(r"\n(?=entityRelationship )", (ONT / "entityRelationships.tmdl").read_text()):
    m = re.search(r"label: (\w+)\n\s+fromEntity: (\w+)\n\s+toEntity: (\w+)", block)
    if m:
        relationships.append(m.groups())
assert len(entity_names) == 17 and len(relationships) == 39
assert sum(node_counts.values()) == 33960 and sum(edge_counts.values()) == 65684
CORE_REL = [r for r in relationships if "Extension" not in r[1] + r[2]]
assert len(CORE_REL) == 15 and len(relationships) - len(CORE_REL) == 24
rel_pair = {name: (a, b) for name, a, b in relationships}

# ---- headline numbers -----------------------------------------------------------------------------------
tot = defaultdict(Decimal)
monthly = defaultdict(lambda: defaultdict(Decimal))
for r in dataset["semantic_financial_metrics_daily"]:
    if r["metric_code"] == "EBITDA":
        tot[r["scenario_tag"]] += Decimal(r["amount_group"])
        monthly[r["metric_date"][:7]][r["scenario_tag"]] += Decimal(r["amount_group"])
ACTUAL, BASELINE = tot["actual"], tot["baseline"]
GAP = ACTUAL - BASELINE
GAP_PCT = (GAP / BASELINE * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
assert (oku(ACTUAL), oku(BASELINE), oku(GAP)) == (Decimal("447.57"), Decimal("448.60"), Decimal("-1.03"))
assert GAP_PCT == Decimal("-0.23")
MONTHS = sorted(monthly)
assert len(MONTHS) == 12 and MONTHS[0] == "2025-10" and MONTHS[-1] == "2026-09"
DEV = {m: monthly[m]["actual"] - monthly[m]["baseline"] for m in MONTHS}
WORST = min(DEV, key=DEV.get)
BEST = max(DEV, key=DEV.get)
assert (WORST, BEST) == ("2026-05", "2026-09")
assert (fmt(DEV[WORST]), fmt(DEV[BEST])) == (MINUS + "6.83", "+5.84")

revenue = sum((Decimal(r["amount_group"]) for r in dataset["semantic_financial_metrics_daily"]
               if r["metric_code"] == "REVENUE" and r["scenario_tag"] == "actual"), Decimal(0))
assert (round(revenue / OKU), round(ACTUAL / OKU)) == (3111, 448)

EVENT_ORDER = ["MTL_NEG", "ENE_NEG", "FOD_NEG", "FIN_NEG", "CROSS_NEG",
               "MTL_POS", "ENE_POS", "FOD_POS", "FIN_POS", "CROSS_POS"]
EVENT_JP = {"MTL_NEG": "製錬停止", "ENE_NEG": "LNG基地の整備遅れ", "FOD_NEG": "食品損失", "FIN_NEG": "取引先対応コスト増",
            "CROSS_NEG": "横断混乱（港湾・流動性）", "MTL_POS": "再生合金契約", "ENE_POS": "貯蔵配分の最適化",
            "FOD_POS": "調達改善", "FIN_POS": "ヘッジ手数料の増収", "CROSS_POS": "横断回復（物流・資金）"}
EV = {k: Decimal(v["full_jpy"]) for k, v in events.items()}
EV_MGMT = {k: Decimal(v["management_jpy"]) for k, v in events.items()}
NEG_SUM = sum(v for k, v in EV.items() if k.endswith("_NEG"))
POS_SUM = sum(v for k, v in EV.items() if k.endswith("_POS"))
assert (fmt(NEG_SUM), fmt(POS_SUM), fmt(NEG_SUM + POS_SUM)) == (MINUS + "13.17", "+12.14", MINUS + "1.03")
assert oku(NEG_SUM + POS_SUM) == oku(GAP)
assert sum(graph_paths.values()) == 1344 == len(dataset["semantic_event_financial_effects"])
assert all(graph_paths[k] == events[k]["effects"] for k in events)
_pf = fix["verification"]["graph"]
assert (_pf["complete_evidence_to_kpi_paths"], _pf["food_loss_path_query_rows"],
        _pf["food_loss_path_query_unique_effects"]) == (1344, 84, 84)
assert (_pf["nodes"], _pf["edges"], _pf["node_and_edge_counts_per_type_equal_to_before"]) == (33960, 65684, True)

# ---- food loss by contract ------------------------------------------------------------------------------
contract = {c["contract_id"]: c for c in dataset["semantic_contracts"]}
entity_name = {s["entity_id"]: s["entity_name"] for s in subsidiaries}
fod = defaultdict(lambda: [Decimal(0), Decimal(0)])
for r in dataset["semantic_event_financial_effects"]:
    if r["event_id"] == "FOD_NEG":
        fod[r["contract_id"]][0] += Decimal(r["delta_ebitda_full_jpy"])
        fod[r["contract_id"]][1] += Decimal(r["delta_management_jpy"])
FOD_ROWS = sorted(fod.items(), key=lambda kv: (kv[1][0], kv[0]))
assert len(FOD_ROWS) == 6
assert sum(v[0] for _, v in FOD_ROWS) == EV["FOD_NEG"] == Decimal(audit["exact_full_event_jpy"])
assert Decimal(str(_pf["food_loss_effect_sum_jpy"])) == EV["FOD_NEG"].quantize(Decimal("0.01")) == Decimal("-114461186.25")
assert sum(v[1] for _, v in FOD_ROWS) == EV_MGMT["FOD_NEG"] == Decimal(audit["exact_management_event_jpy"])
assert {contract[k]["commodity"] for k, _ in FOD_ROWS} == {"milling_wheat"}

# ---- cross-sector event by company ----------------------------------------------------------------------
sector_of = {s["entity_id"]: s["sector_code"] for s in subsidiaries}
cross_co, cross_ct, ebitda_co = defaultdict(Decimal), defaultdict(set), defaultdict(Decimal)
for r in dataset["semantic_event_financial_effects"]:
    if r["event_id"] == "CROSS_NEG":
        cross_co[r["entity_id"]] += Decimal(r["delta_ebitda_full_jpy"])
        cross_ct[r["entity_id"]].add(r["contract_id"])
for r in dataset["semantic_financial_metrics_daily"]:
    if r["metric_code"] == "EBITDA" and r["scenario_tag"] == "actual":
        ebitda_co[r["entity_id"]] += Decimal(r["amount_group"])
assert len(cross_co) == 8 and sum(cross_co.values()) == EV["CROSS_NEG"]
CROSS_CONTRACTS = len(set().union(*cross_ct.values()))
assert CROSS_CONTRACTS == 26
cross_pct = {k: -cross_co[k] / ebitda_co[k] * 100 for k in cross_co}
PCT_LO, PCT_HI = min(cross_pct.values()), max(cross_pct.values())
assert Decimal("1.4") <= PCT_LO and PCT_HI <= Decimal("1.6")
CROSS_ANNUAL = (-EV["CROSS_NEG"] / ACTUAL * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
FOOD_ANNUAL = (-EV["FOD_NEG"] / ACTUAL * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
assert (CROSS_ANNUAL, FOOD_ANNUAL) == (Decimal("1.52"), Decimal("0.26"))
SECTOR_KEYS = ("metals", "energy", "foods", "finance")
sector_cross = defaultdict(Decimal)
for _k, _v in cross_co.items():
    sector_cross[sector_of[_k]] += _v
_fix_runs = {r["id"]: r for r in fix["runs"]}
_tbl = _fix_runs["B_sector"]["result_tables"][0]
_cols = _tbl["columns"]
for _row in _tbl["rows"]:
    _d = dict(zip(_cols, _row))
    if _d["event_id"] == "CROSS_NEG" and _d["sector_code"] in SECTOR_KEYS:
        assert Decimal(str(_d["full_consolidated_ebitda_impact_jpy_oku"])) == oku(sector_cross[_d["sector_code"]]), _d
# the DA answered the per-company question; its table must equal the saved data
_wide = {r["id"]: r for r in wide["runs"]}
_ex = next(x for x in reversed(_wide["company"]["sql_executions"])
           if x["is_success"] and "subsidiary_name" in x["columns"])
_da = {row[_ex["columns"].index("subsidiary_name")]: Decimal(str(row[_ex["columns"].index(
    "full_consolidated_impact_oku_jpy")])) for row in _ex["rows"]}
for _s in subsidiaries:
    assert _da[_s["entity_name"]] == oku(cross_co[_s["entity_id"]]), _s["entity_name"]

# ---- priority table from the Data Agent's action question (checked against the saved data) --------------
q_act = next(q for q in fix["demo_questions"] if q["id"] == "Q_ACT")["extracted"]["table"]
NEG_EVENTS = {k for k in EV if k.endswith("_NEG")}
per_contract, per_events = defaultdict(Decimal), defaultdict(set)
for r in dataset["semantic_event_financial_effects"]:
    if r["event_id"] in NEG_EVENTS:
        per_contract[r["contract_id"]] += Decimal(r["delta_ebitda_full_jpy"])
        per_events[r["contract_id"]].add(r["event_id"])
for row in q_act:
    assert oku(per_contract[row["contract_id"]]) == Decimal(str(row["full_oku"])), row["contract_id"]
    assert per_events[row["contract_id"]] == set(row["events"]), row["contract_id"]
assert [r["priority"] for r in q_act] == ["高"] * 4 + ["中"] * 3

# ---- Step03 path (the saved, Graph-verified example) ------------------------------------------------------
path = audit["representative_path"]
assert (audit["diagram_nodes"], audit["diagram_edges"]) == (8, 7)
assert Decimal(audit["exact_representative_effect_jpy"]) == Decimal(str(path["graph_effect_jpy"]))
REP_EFFECT = Decimal(audit["exact_representative_effect_jpy"])
SUB_DAILY = Decimal(audit["exact_subsidiary_daily_actual_ebitda_jpy"])
GROUP_DAILY = Decimal(audit["exact_group_daily_actual_ebitda_jpy"])
OBS = audit["cold_chain_observation"]
assert (OBS["temperature_c"], OBS["spoilage_percent"]) == (-18.0, 3.5)
assert path["contract_id"] == "SUB_FOD_JP_01_C04" and path["commodity"] == "milling_wheat"


def yen(v):
    return format(v, ",.2f").replace("-", MINUS) + "円"


# ---- demo scale -----------------------------------------------------------------------------------------
N_CONTRACTS = len(dataset["semantic_contracts"])
N_ACTIVITIES = len(dataset["semantic_business_activities"])
N_EVENTS = len(dataset["semantic_risk_events"])
N_EVIDENCE = len(dataset["semantic_event_evidence"])
N_EFFECTS = len(dataset["semantic_event_financial_effects"])
assert (N_CONTRACTS, N_ACTIVITIES, N_EVENTS, N_EVIDENCE, N_EFFECTS) == (96, 8760, 10, 64, 1344)
SECTOR_JP = {"metals": "金属", "energy": "エネルギー", "foods": "食品", "finance": "金融"}
COMMODITY_JP = {"copper_alloy": "銅合金", "LNG": "LNG", "milling_wheat": "製粉用小麦", "trade_finance": "貿易金融"}
commodity_of = {c["entity_id"]: c["commodity"] for c in dataset["semantic_contracts"]}
assert [s["sector_code"] for s in subsidiaries] == ["metals"] * 2 + ["energy"] * 2 + ["foods"] * 2 + ["finance"] * 2
assert sorted(s["ownership_ratio"] for s in subsidiaries) == ["0.51"] * 4 + ["1.00"] * 4
lh_tables = defaultdict(int)
for _key in cloud["counts"]:
    lh_tables[_key.split(".")[0]] += 1
assert (cloud["tables"], lh_tables["LH_Group_SAP"]) == (95, 17)


# ---- Rayfin app (live check on 2026-10-28) ---------------------------------------------------------------
# The what-if figures come from the saved live-check report. Each one is checked against numbers this deck
# already derives from data/ and reports/, so a typo in the report cannot reach a slide.
APP_SC = app["scenarios"]
APP_BOTH = APP_SC["food_loss_50_and_yen_up_10"]
APP_FULL = Decimal(APP_BOTH["delta_full_jpy"])
APP_MGMT = Decimal(APP_BOTH["delta_management_jpy"])
APP_STEP_EVENTS = Decimal(APP_BOTH["steps_full_jpy"]["events"])
APP_STEP_FX = Decimal(APP_BOTH["steps_full_jpy"]["fx"])
APP_FOOD_ONLY = Decimal(APP_SC["food_loss_50"]["delta_full_jpy"])
APP_YEN_ONLY = Decimal(APP_SC["yen_up_10"]["delta_full_jpy"])
APP_BASE_FULL = Decimal(app["probe"]["base_annual_ebitda_jpy"]["full"])
assert app["status"] == "verified_live_with_limits" and app["environment"]["identifiers_recorded"] is False
assert app["probe"]["reconciliation"] == {"ok": True, "group_mismatches": 0, "management_mismatches": 0,
                                          "effect_mismatches": 0}
assert (app["probe"]["counts"]["effects"], app["probe"]["counts"]["events"]) == (N_EFFECTS, N_EVENTS)
assert APP_BASE_FULL == ACTUAL.quantize(Decimal("0.01")) == Decimal("44757399732.84")  # to the yen
# 50% of the food-loss total, rounded per row by the app, equals half the total to the yen
assert abs(APP_FOOD_ONLY - (-EV["FOD_NEG"] / 2)) < Decimal("0.01")
assert APP_FOOD_ONLY == APP_STEP_EVENTS
assert APP_STEP_EVENTS + APP_STEP_FX == APP_FULL
assert sum(Decimal(v) for v in APP_BOTH["steps_management_jpy"].values()) == APP_MGMT
assert (fmt(APP_FULL, "0.1"), fmt(APP_MGMT, "0.1")) == (MINUS + "22.7", MINUS + "13.7")
# the two changes interact: the food-loss relief is also translated at the new rate
APP_SUM_OF_SINGLES = APP_FOOD_ONLY + APP_YEN_ONLY
assert APP_SUM_OF_SINGLES != APP_FULL and abs(APP_FULL - APP_SUM_OF_SINGLES) > Decimal(1_000_000)
APP_PATHS = app["graph_paths_per_event"]
assert set(APP_PATHS) == set(EVENT_ORDER)
for _ev, _row in APP_PATHS.items():
    assert _row["graph_effects_equal_lakehouse_effects"] is True
    assert _row["FinancialEffect"] == graph_paths[_ev] == events[_ev]["effects"], _ev
assert sum(r["FinancialEffect"] for r in APP_PATHS.values()) == N_EFFECTS
assert APP_PATHS["FOD_NEG"]["Contract"] == len(FOD_ROWS) == 6
assert APP_PATHS["CROSS_NEG"]["Contract"] == CROSS_CONTRACTS == 26
assert app["not_verified"] and len(app["learn_sources"]) == 5
APP_IMG = {k: HERE / "assets" / f"whatif_app_{k}.png" for k in ("result", "waterfall", "path")}
assert all(p_.exists() for p_ in APP_IMG.values()), APP_IMG


def mil(v, places="0.1"):
    """A JPY amount in million yen with a real minus sign (the app's breakdown unit)."""
    return format((v / Decimal(10) ** 6).quantize(Decimal(places), rounding=ROUND_HALF_UP), f"+,.{len(places.split('.')[1])}f").replace("-", MINUS)


# =====================================================================================================
# Drawing helpers
# =====================================================================================================
NAVY, TEAL, CORAL, PURPLE = "17334A", "087F83", "BD4354", "7352AD"
INK, MUTED, BG, WHITE = "21374A", "566A78", "F4F7F7", "FFFFFF"
PALE, GRAY, LINE = "E6F2EF", "E5EBEE", "D3DFE4"
STEEL = "6B7F8E"
MINT, BODY_ON_NAVY = "A9DCD9", "E6EEF2"
ZERO_FILL, MAT_FILL = "D8EDE9", "ECE6F6"
CORAL_PALE = "F8E7EA"
FONT = "Yu Gothic"
SW, SH = 13.333333, 7.5
CENTER, RIGHT, MIDDLE = PP_ALIGN.CENTER, PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE

prs = Presentation()
_OLD_W = prs.slide_width
prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
for _holder in [prs.slide_master] + list(prs.slide_layouts):
    for _shp in _holder.shapes:
        if _shp.left is not None and _shp.width is not None:
            _shp.left, _shp.width = int(_shp.left * prs.slide_width / _OLD_W), int(_shp.width * prs.slide_width / _OLD_W)
prs.core_properties.title = "Fabric IQ Ontology によるEBITDA要因分析（お客様向け）"
prs.core_properties.subject = "総合商社モデル（架空データ）のデモと導入の進め方"
prs.core_properties.author = "Microsoft"
prs.core_properties.keywords = "Fabric IQ, Ontology, Data Agent, Japanese, Synthetic"
prs.core_properties.comments = "Synthetic demo data. Ontology and Data Agent are Preview."
prs.core_properties.last_modified_by = "Microsoft"
prs.core_properties.category = "Customer presentation"
prs.core_properties.language = "ja-JP"
_NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
prs.core_properties.created = _NOW
prs.core_properties.modified = _NOW
prs.core_properties.revision = 1
slide_metadata, WARN = [], []


_JA = budoux.load_default_japanese_parser()
_NO_START = set("、。，．）」』】〕〉》！？：；・ーぁぃぅぇぉっゃゅょァィゥェォッャュョ〜…%％")
_NO_END = set("（「『【〔〈《")


def _em(c):
    """Rough advance width in em for Yu Gothic; Latin is estimated on the wide side so lines never overflow."""
    o = ord(c)
    if o < 0x80:
        if c == " ":
            return .3
        if c.isdigit():
            return .58
        if c.isupper():
            return .66
        if c in ".,:;'!|il":
            return .32
        return .54
    if o in (0x2212, 0x2013, 0xD7):
        return .8
    if 0xFF61 <= o <= 0xFF9F:
        return .5
    return 1.0


_GLUE = ("結び付", "結びつ", "取り込", "使い回", "使い分", "組み合わ", "読み解", "見つけ", "引き継")


def _phrases(plain):
    out = []
    for ph in _JA.parse(plain):
        if out and any((out[-1] + ph).startswith(g) or g in (out[-1][-3:] + ph[:3]) for g in _GLUE) and \
                len(out[-1]) <= 3:
            out[-1] += ph
            continue
        if out and (len(out[-1]) == 1 or len(ph) == 1 or ph[0] in _NO_START or out[-1][-1] in _NO_END):
            out[-1] += ph
        else:
            out.append(ph)
    return out


def _pack(widths, limit):
    lines, cur, w = [], [], 0.0
    for i, uw in enumerate(widths):
        if cur and w + uw > limit:
            lines.append(cur)
            cur, w = [], 0.0
        cur.append(i)
        w += uw
    if cur:
        lines.append(cur)
    return lines


def layout_lines(runs, width, size):
    """Break one paragraph (a list of (text, style)) at phrase boundaries; return [(start, end)] char offsets.

    Lines are balanced, so the last line is never a one- or two-character orphan.
    """
    plain, sizes = "", []
    for txt, st in runs:
        plain += txt
        sizes += [st.get("size", size)] * len(txt)
    if not plain:
        return [(0, 0)]
    limit = width * 72 * .96
    units, widths, pos = [], [], 0
    for ph in _phrases(plain):
        chunk, cw, cs = "", 0.0, pos
        for i, ch in enumerate(ph):
            wch = _em(ch) * sizes[pos + i]
            if chunk and cw + wch > limit:
                units.append((cs, cs + len(chunk)))
                widths.append(cw)
                chunk, cw, cs = "", 0.0, pos + i
            chunk += ch
            cw += wch
        units.append((cs, cs + len(chunk)))
        widths.append(cw)
        pos += len(ph)
    lines = _pack(widths, limit)
    n = len(lines)
    if n > 1:
        lo, hi = max(max(widths), sum(widths) / n), limit
        for _ in range(26):
            mid = (lo + hi) / 2
            if len(_pack(widths, mid)) <= n:
                hi = mid
            else:
                lo = mid
        lines = _pack(widths, hi)
    out = []
    for ln in lines:
        s0, e0 = units[ln[0]][0], units[ln[-1]][1]
        while s0 < e0 and plain[s0] == " ":
            s0 += 1
        while e0 > s0 and plain[e0 - 1] == " ":
            e0 -= 1
        out.append((s0, e0))
    return out


def est_lines(value, width, size):
    """Number of lines a plain string needs in a box of the given width (inches) at the given size (pt)."""
    return sum(len(layout_lines([(para, {})], width, size)) for para in value.split("\n"))


_ADEC = "http://schemas.microsoft.com/office/drawing/2017/decorative"


def _decorative(shape):
    """Mark a text-less shape as decorative so that screen readers skip it."""
    cnv = shape._element.xpath("./*[1]/p:cNvPr")[0]
    ext_lst = OxmlElement("a:extLst")
    ext = OxmlElement("a:ext")
    ext.set("uri", "{C183D7F6-B498-43B3-948B-1728B52AA6E4}")
    dec = etree.SubElement(ext, "{%s}decorative" % _ADEC, nsmap={"adec": _ADEC})
    dec.set("val", "1")
    ext_lst.append(ext)
    cnv.append(ext_lst)


def _flat(shape):
    shape.shadow.inherit = False
    for ref in shape._element.xpath(".//a:effectRef"):
        ref.set("idx", "0")


def _fill(shape, color):
    if color is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)


def box(slide, x, y, w, h, fill=WHITE, line=LINE, rounded=True, radius=.08, dash=False, lw=.75):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    _flat(shp)
    _fill(shp, fill)
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = RGBColor.from_string(line)
        shp.line.width = Pt(lw)
        if dash:
            shp.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    if rounded:
        shp.adjustments[0] = min(.5, radius / min(w, h))
    _decorative(shp)
    return shp


def oval(slide, cx, cy, r, fill, line=None, lw=1.0):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - r), Inches(cy - r), Inches(2 * r), Inches(2 * r))
    _flat(shp)
    _fill(shp, fill)
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = RGBColor.from_string(line)
        shp.line.width = Pt(lw)
    _decorative(shp)
    return shp


_DATE_FULL = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_DATE_YM = re.compile(r"(?<![\d-])(\d{4})-(\d{2})(?![\d-])")


def jdate(s):
    """2026-10-27 -> 2026年10月27日, 2026-05 -> 2026年5月 (prose and labels use Japanese dates)."""
    s = _DATE_FULL.sub(lambda m: f"{m[1]}年{int(m[2])}月{int(m[3])}日", s)
    return _DATE_YM.sub(lambda m: f"{m[1]}年{int(m[2])}月", s)


def _run(p, value, size, color, bold=False):
    r = p.add_run()
    r.text = jdate(value)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = RGBColor.from_string(color)
    rPr = r._r.get_or_add_rPr()
    ea = OxmlElement("a:ea")
    ea.set("typeface", FONT)
    rPr.append(ea)
    rPr.set("lang", "ja-JP")
    return r


def _break(p, size):
    br = OxmlElement("a:br")
    rpr = OxmlElement("a:rPr")
    rpr.set("lang", "ja-JP")
    rpr.set("sz", str(int(round(size * 100))))
    br.append(rpr)
    p._p.append(br)


def _fill_frame(tf, value, w, h, size, color, bold, align, anchor, spacing, after, label_slide):
    """Write paragraphs into a text frame. A paragraph is a string, a list of (text, style) runs, or
    {"runs": [...], "after": pt}. Long paragraphs are broken at phrase boundaries (see layout_lines)."""
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if anchor is not None:
        tf.vertical_anchor = anchor
    paras = value if isinstance(value, list) else value.split("\n")
    need, first = 0.0, ""
    for i, para in enumerate(paras):
        p_after = after
        if isinstance(para, dict):
            p_after = para.get("after", after)
            para = para["runs"]
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        runs = para if isinstance(para, list) else [(para, {})]
        psize = max([st.get("size", size) for _, st in runs] + [0])
        p.line_spacing = Pt(round(psize * spacing, 1))
        p.space_after = Pt(p_after)
        if align is not None:
            p.alignment = align
        lines = layout_lines(runs, w, size)
        for li, (s0, e0) in enumerate(lines):
            if li:
                _break(p, psize)
            pos = 0
            for txt, st in runs:
                a, b = max(s0, pos), min(e0, pos + len(txt))
                if a < b:
                    _run(p, txt[a - pos:b - pos], st.get("size", size), st.get("color", color), st.get("bold", bold))
                pos += len(txt)
        need += len(lines) * psize * spacing / 72 + (p_after / 72 if i < len(paras) - 1 else 0)
        if not first:
            first = "".join(txt for txt, _ in runs)
    if need > h + .08:
        WARN.append((label_slide, first[:26], round(need, 2), round(h, 2)))


def text(slide, value, x, y, w, h, size=14, color=INK, bold=False, align=None, anchor=None,
         spacing=1.3, after=0):
    """Plain text box. A paragraph may mix styles via [(text, {"bold":..,"color":..}), ...]."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    _fill_frame(tb.text_frame, value, w, h, size, color, bold, align, anchor, spacing, after, len(prs.slides))
    return tb


def title_text(slide, value, x, y, w, h, size, color, bold=True, spacing=1.15):
    """The slide title lives in the layout's title placeholder so outline view and screen readers find it."""
    ph = slide.shapes.title
    ph.left, ph.top, ph.width, ph.height = Inches(x), Inches(y), Inches(w), Inches(h)
    tf = ph.text_frame
    _fill_frame(tf, value, w, h, size, color, bold, PP_ALIGN.LEFT, MSO_ANCHOR.TOP, spacing, 0, len(prs.slides))
    tf.auto_size = MSO_AUTO_SIZE.NONE
    return ph


def arrow(slide, x1, y1, x2, y2, color=TEAL, dashed=False, width=2.0, head=True):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = RGBColor.from_string(color)
    c.line.width = Pt(width)
    if dashed:
        c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    if head:
        tail = OxmlElement("a:tailEnd")
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
        c.line._get_or_add_ln().append(tail)
    _decorative(c)
    return c


def chip(slide, label, x, y, w, color=TEAL, fill=PALE, size=11, h=.3, bold=True):
    box(slide, x, y, w, h, fill, None, radius=h / 2)
    text(slide, label, x, y, w, h, size, color, bold, CENTER, MIDDLE, spacing=1.0)


def numdot(slide, label, cx, cy, r=.22, fill=TEAL, color=WHITE, size=13):
    oval(slide, cx, cy, r, fill)
    text(slide, label, cx - r, cy - r, 2 * r, 2 * r, size, color, True, CENTER, MIDDLE, spacing=1.0)


def node(slide, x, y, w, h, head, body="", accent=TEAL, fill=WHITE, head_size=13, body_size=11,
         dash=False, line=LINE):
    box(slide, x, y, w, h, fill, line, radius=.07, dash=dash)
    box(slide, x + .02, y + .09, .07, h - .18, accent, None, radius=.035)
    text(slide, head, x + .22, y + .1, w - .32, .3, head_size, accent if accent != STEEL else INK, True,
         spacing=1.15)
    if body:
        text(slide, body, x + .22, y + .1 + head_size * 1.15 / 72 + .06, w - .32,
             h - .2 - head_size * 1.15 / 72, body_size, INK, spacing=1.25)


def motif(slide, x, y, s=1.0, color=TEAL, fill=None):
    """Small three-node graph mark used on every slide."""
    pts = [(x + .07 * s, y + .06 * s), (x + .36 * s, y + .15 * s), (x + .17 * s, y + .38 * s)]
    for a, b in ((0, 1), (1, 2), (0, 2)):
        arrow(slide, pts[a][0], pts[a][1], pts[b][0], pts[b][1], color, width=1.25, head=False)
    for px, py in pts:
        oval(slide, px, py, .065 * s, fill or color)


def set_background(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_string(color)


FOOT = "デモのデータは架空です（為替のみECB公表値）  |  Ontology、Ontologyと連携するData Agent、Fabric AppsはPreview"
FOOT_APP = "デモのデータは架空です（為替のみECB公表値）  |  Fabric AppsとOntologyはPreview。グラフのクエリ用APIはbeta"


def finish_notes(slide, notes, sources):
    slide.notes_slide.notes_text_frame.text = jdate(notes.strip() + (
        "\n\n【出典】\n" + "\n".join(sources) if sources else ""))


def base_slide(bg):
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    set_background(slide, bg)
    return slide


def new_slide(kicker, title, lead, notes, sources, takeaway=None, trace=None, foot=None):
    slide = base_slide(BG)
    n = len(prs.slides)
    title_text(slide, title, .6, .72, 12.13, .62, 30, NAVY)
    motif(slide, .6, .34, .8)
    text(slide, kicker, 1.02, .33, 11.2, .26, 11.5, TEAL, True, spacing=1.0)
    if est_lines(title, 12.13, 30) != 1:
        WARN.append((n, "TITLE WRAPS " + title, est_lines(title, 12.13, 30), 1))
    text(slide, lead, .62, 1.44, 12.0, .7, 16, MUTED, spacing=1.35)
    if est_lines(lead, 12.0, 16) > 2:
        WARN.append((n, "LEAD>2 " + lead[:20], est_lines(lead, 12.0, 16), 2))
    if takeaway:
        box(slide, .6, 6.38, 12.13, .54, PALE, None, radius=.1)
        text(slide, takeaway, .82, 6.38, 11.7, .54, 13, NAVY, True, anchor=MIDDLE, spacing=1.25)
        if est_lines(takeaway, 11.7, 13) > 2:
            WARN.append((n, "BAR>2 " + takeaway[:20], est_lines(takeaway, 11.7, 13), 2))
    text(slide, foot or FOOT, .62, 7.1, 10.8, .22, 10.5, MUTED, spacing=1.0)
    text(slide, f"{n:02}", 12.13, 7.04, .6, .3, 13, TEAL, True, RIGHT, spacing=1.0)
    finish_notes(slide, notes, sources)
    slide_metadata.append({"slide": n, "title": title, "sources": sources, "trace": trace or []})
    return slide


LIGHT_ON_NAVY = MINT


# =====================================================================================================
# Structure: the divider pages and the agenda are generated from this table so page numbers stay correct
# =====================================================================================================
T_TITLE = "EBITDAの増減理由を根拠までたどる"
T_AGENDA = "本日の内容"
T_Q = "増減の理由と根拠が経営会議で問われる"
T_STRUCT = "理由の説明に手間がかかる3つの構造"
T_WHAT = "Ontology：業務の概念と関係を定義する層"
T_PARTS = "このデモのOntology：主な8概念と関係"
T_SETTING = "デモの設定：架空の総合商社グループ"
T_FLOW = "4つの質問で全体から打ち手まで進む"
T_Q1 = f"年間の差は{fmt(GAP)}億円、月次の最大差は{fmt(-DEV[WORST], sign=False)}億円"
T_Q2 = "10件のイベントに分解すると増減の中身が見える"
T_Q3 = f"食品損失は6契約に効き、合計{fmt(EV['FOD_NEG'])}億円"
T_PATH = "根拠記録から全社KPIまでの経路が見える"
T_Q4 = "手を打つ契約の候補を、優先度つきで一覧にできる"
T_RIPPLE = "全社に及ぶイベントも同じ経路で追える"
T_DIFF = "定義とつながりを1か所で管理し、共有できる"
T_DATA = "各社の原本は残し、分析用の表とGraphを作成する"
T_GOV = "Fabricの権限の仕組みの上で動き、版も管理できる"
T_SCALE = "拡張の機能：名前空間、継承、共有プロパティ、ルール"
T_APP_ROLES = "つながりはOntology、金額はLakehouse、計算はアプリ"
T_APP_SCREEN = "為替とイベントを変えた差額と内訳を確認"
T_APP_PATH = "イベントからKPIまでの経路をアプリで取得"
T_APP_SCOPE = "確認できたこと、記載に基づくこと、未確認のこと"
T_SMALL = "質問1つから小さく始めて広げる"
T_POC = "PoCで確認する項目とご準備いただく情報"
T_CAVEAT = "現時点の提供状況とご留意いただく点"
T_NEXT = "貴社の質問とデータでPoCを設計する"
T_A_ENV = "付録1 デモ環境の構成"
T_A_MAP = "付録2 概念17種類と関係39種類の一覧"
T_A_QA = "付録3 デモで使った質問と回答の要点"
T_A_FAQ = "付録4 よくあるご質問"
T_A_GLOSS = "付録5 用語集"

CHAPTERS = [
    {"n": 1, "name": "課題と考え方",
     "lead": "経営会議の問いと理由を出しにくい構造、\nOntologyの役割を整理します。",
     "agenda": "経営の問い、理由を出しにくい構造、Ontologyとは",
     "pages": [T_Q, T_STRUCT, T_WHAT, T_PARTS]},
    {"n": 2, "name": "デモで確認",
     "lead": "架空の総合商社グループで、4つの質問を\n日本語で入力し、答えと根拠を確認します。",
     "agenda": "4つの質問で、全体、原因、根拠、打ち手を確認",
     "pages": [T_SETTING, T_FLOW, T_Q1, T_Q2, T_Q3, T_PATH, T_Q4, T_RIPPLE]},
    {"n": 3, "name": "価値と仕組み",
     "lead": "従来の手段との違い、既存データの活用、\n権限、拡張の仕組みを示します。",
     "agenda": "従来との違い、既存データの活用、権限、拡張",
     "pages": [T_DIFF, T_DATA, T_GOV, T_SCALE]},
    {"n": 4, "name": "業務アプリで使う",
     "lead": "Data Agentとは別に、業務アプリ\n（Fabric Apps、Preview）から\nOntologyのグラフを使う例です。",
     "agenda": "アプリでの役割分担、実画面、経路の取得、確認範囲",
     "pages": [T_APP_ROLES, T_APP_SCREEN, T_APP_PATH, T_APP_SCOPE]},
    {"n": 5, "name": "進め方",
     "lead": "小さく始める進め方、PoCの確認項目、\n現時点の留意点、次のステップです。",
     "agenda": "小さく始める、PoCの確認項目、留意点、次のステップ",
     "pages": [T_SMALL, T_POC, T_CAVEAT, T_NEXT]},
]
APPENDIX = {"n": 0, "name": "付録",
            "lead": "デモ環境、概念と関係の一覧、質問と回答、\nよくあるご質問、用語集です。",
            "agenda": "環境、概念と関係の一覧、質問と回答、FAQ、用語集",
            "pages": [T_A_ENV, T_A_MAP, T_A_QA, T_A_FAQ, T_A_GLOSS]}
FINAL_TITLES = [T_TITLE, T_AGENDA]
for _ch in CHAPTERS + [APPENDIX]:
    _ch["divider"] = f"第{_ch['n']}章 {_ch['name']}" if _ch["n"] else "付録"
    FINAL_TITLES.append(_ch["divider"])
    FINAL_TITLES.extend(_ch["pages"])
assert len(FINAL_TITLES) == len(set(FINAL_TITLES))
PAGE_OF = {t: i + 1 for i, t in enumerate(FINAL_TITLES)}
KICKER = {}
for _ch in CHAPTERS + [APPENDIX]:
    for _t in _ch["pages"]:
        KICKER[_t] = _ch["divider"]


def page_range(ch):
    return f"p.{PAGE_OF[ch['pages'][0]]}〜{PAGE_OF[ch['pages'][-1]]}"


def expect(title):
    """Each slide builder calls this first so the page order cannot drift from the table above."""
    assert FINAL_TITLES[len(prs.slides)] == title, (len(prs.slides) + 1, title)


def k(title, sub):
    return f"{KICKER[title]}  |  {sub}"


# =====================================================================================================
# 1 Title
# =====================================================================================================
def net_graph(slide, ox=0.0, oy=0.0, labels=True):
    """The ontology as a small network, used on the title page."""
    nodes = {
        "event": (7.9, 2.05, .66, PURPLE, "イベント"), "effect": (9.6, 2.95, .72, CORAL, "影響額"),
        "evidence": (7.65, 4.55, .6, STEEL, "根拠"), "contract": (11.55, 2.0, .64, "2D6A8F", "契約"),
        "company": (11.8, 4.2, .64, TEAL, "会社"), "metric": (10.35, 4.7, .6, "2F8F90", "日次指標"),
        "kpi": (10.4, 6.25, .66, "3E9C9A", "全社KPI"),
    }
    edges = [("event", "effect"), ("evidence", "effect"), ("effect", "contract"), ("contract", "company"),
             ("effect", "metric"), ("metric", "kpi"), ("metric", "company")]
    for a, b in edges:
        ax, ay, ar = nodes[a][:3]
        bx, by, br = nodes[b][:3]
        arrow(slide, ax + ox, ay + oy, bx + ox, by + oy, "5C8BA3", width=1.75, head=False)
    for key, (x, y, r, color, label) in nodes.items():
        oval(slide, x + ox, y + oy, r, color, MINT, 1.25)
        text(slide, label, x + ox - r, y + oy - r, 2 * r, 2 * r, 13, WHITE, True, CENTER, MIDDLE, spacing=1.0)


expect(T_TITLE)
s = base_slide(NAVY)
title_text(s, "EBITDAの増減理由を\n根拠までたどる", .8, 2.0, 6.6, 1.9, 44, WHITE, spacing=1.3)
net_graph(s)
motif(s, .8, .78, 1.15, MINT)
text(s, "Microsoft Fabric IQ  |  Ontology（Preview）", 1.5, .82, 6.0, .3, 14, MINT, True, spacing=1.0)
text(s, "総合商社モデル（架空データ）で確認する\nOntologyのデモと、導入の進め方", .82, 4.25, 6.4, .9, 19,
     BODY_ON_NAVY, spacing=1.45)
text(s, "2026年10月", .82, 6.5, 3.0, .3, 14, MINT, True, spacing=1.0)
text(s, "デモのデータは架空です。為替のみ、ECBが公表する日次の参考レートを使っています。", .82, 6.9, 9.0, .25, 11,
     BODY_ON_NAVY, spacing=1.0)
finish_notes(s, """【話す】今日は、総合商社を模した架空のデータを使い、経営会議で問われる「EBITDAが動いた理由と根拠」に、Microsoft Fabric IQのOntologyでどう答えるかをお見せします。前半で考え方、中盤でデモ、後半で価値と進め方をお話しします。
【前提】データはすべて架空です。為替だけは、ECBが公表している日次の参考レートを使っています。デモの金額や会社の動きは、実在の企業の実績を表すものではありません。
【補足】Ontology、Data Agent、第4章のFabric AppsはPreviewの機能です。本資料の記載は、2026年10月時点のMicrosoft Learnと、デモ環境で確認した内容に基づきます。""",
             ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）", "デモ環境の検証記録（2026-10-27）"])
slide_metadata.append({"slide": 1, "title": T_TITLE, "sources": ["デモ環境の検証記録（2026-10-27）"]})

# =====================================================================================================
# 2 Agenda
# =====================================================================================================
expect(T_AGENDA)
s = new_slide(
    "はじめに  |  構成",
    T_AGENDA,
    "デモを中心に、Ontologyが経営の問いにどう答えるかを確認します。\n最後に、貴社のデータで試す進め方をご提案します。",
    """【話す】5つの章で進みます。第1章で経営会議の問いと課題を整理し、第2章で4つの質問を実際に入力して答えと根拠を確認します。第3章で従来の手段との違いや仕組みを整理し、第4章で、Data Agentとは別の使い方として、画面を持つ業務アプリからOntologyのグラフを使う例を示します。第5章で貴社で試す進め方をご提案します。付録に、環境、一覧、質問と回答、FAQ、用語集があります。
【指す】章ごとの行を上から順に。ページ番号はスライド番号です。""",
    ["本資料の構成"])
ROW_H, ROW_P = .64, .74
assert 2.35 + len(CHAPTERS) * ROW_P + ROW_H <= 6.9
for i, ch in enumerate(CHAPTERS + [APPENDIX]):
    y = 2.35 + i * ROW_P
    box(s, .6, y, 12.13, ROW_H, WHITE if ch["n"] else GRAY)
    if ch["n"]:
        numdot(s, str(ch["n"]), 1.05, y + ROW_H / 2, .22, TEAL)
    text(s, ch["name"], 1.5, y, 2.7, ROW_H, 19, NAVY, True, anchor=MIDDLE, spacing=1.0)
    text(s, ch["agenda"], 4.3, y, 6.6, ROW_H, 14, INK, anchor=MIDDLE, spacing=1.2)
    text(s, page_range(ch), 11.0, y, 1.5, ROW_H, 15, TEAL, True, RIGHT, MIDDLE, spacing=1.0)


# =====================================================================================================
# Chapter dividers
# =====================================================================================================
def deco_network(slide, left=False):
    """Low-contrast network at the bottom of dark pages (left: below the chapter lead, clear of the list card)."""
    pts = [(7.6, 6.6), (8.9, 5.9), (10.4, 6.7), (11.7, 5.6), (12.7, 6.8), (9.9, 5.15), (11.0, 6.9)]
    if left:
        pts = [(x - 6.8, 5.9 + (y - 5.15) * .6) for x, y in pts]
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 3), (2, 6), (6, 4)):
        arrow(slide, pts[a][0], pts[a][1], pts[b][0], pts[b][1], "2C516B", width=1.5, head=False)
    for i, (x, y) in enumerate(pts):
        oval(slide, x, y, .17 + .03 * (i % 3), "2C516B")


def divider(ch):
    expect(ch["divider"])
    s = base_slide(NAVY)
    n = len(prs.slides)
    if ch["n"]:
        title_text(s, [{"runs": [(f"第{ch['n']}章", {"size": 44, "color": MINT})], "after": 28},
                       {"runs": [(ch["name"], {"size": 40, "color": WHITE})]}], .8, 2.0, 6.0, 2.0, 44, WHITE,
                   spacing=1.0)
    else:
        title_text(s, "付録", .8, 2.3, 5.6, .9, 44, WHITE, spacing=1.0)
    deco_network(s, left=True)
    motif(s, .8, .78, 1.15, MINT)
    text(s, "章立て" if ch["n"] else "付録", 1.5, .82, 4.0, .3, 14, MINT, True, spacing=1.0)
    text(s, ch["lead"], .82, 4.5, 5.9, max(1.0, .4 * (ch["lead"].count("\n") + 1)), 18, BODY_ON_NAVY, spacing=1.5)
    cy = .75
    ch_pages = ch["pages"]
    LS, LW = 14, 4.35
    rows = [est_lines(t, LW, LS) for t in ch_pages]
    heights = [r * LS * 1.3 / 72 for r in rows]
    card_h = sum(heights) + .2 * len(rows) + 1.0
    assert cy + card_h < 7.0, (ch["divider"], card_h)
    box(s, 7.15, cy, 5.58, card_h, WHITE, None, radius=.16)
    text(s, f"この章のページ（{len(ch_pages)}枚）", 7.5, cy + .3, 4.8, .32, 16, TEAL, True, spacing=1.0)
    y = cy + .95
    for t_, hh in zip(ch_pages, heights):
        text(s, f"p.{PAGE_OF[t_]}", 7.5, y, .7, .3, LS, TEAL, True, spacing=1.3)
        text(s, t_, 8.25, y, LW, hh + .02, LS, INK, spacing=1.3)
        y += hh + .2
    text(s, f"{n:02}", 12.13, 7.04, .6, .3, 13, MINT, True, RIGHT, spacing=1.0)
    finish_notes(s, f"【話す】{ch['lead'].replace(chr(10), '')}", [])
    slide_metadata.append({"slide": n, "title": ch["divider"], "sources": ["本資料の構成"]})


def picture(slide, path, x, y, w, alt, frame=True, crop_top=0.0, crop_bottom=0.0):
    """A screenshot at width w (height follows the aspect ratio after the crop) with alt text and a thin frame.
    Returns its height."""
    from PIL import Image
    iw, ih = Image.open(path).size
    h = w * ih * (1 - crop_top - crop_bottom) / iw
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
    if crop_top:
        pic.crop_top = crop_top
    if crop_bottom:
        pic.crop_bottom = crop_bottom
    pic._element.xpath("./p:nvPicPr/p:cNvPr")[0].set("descr", alt)
    if frame:
        pic.line.color.rgb = RGBColor.from_string(LINE)
        pic.line.width = Pt(.75)
    return h


def fix_app_xml(path, n_slides):
    """python-pptx keeps the template's app.xml (4:3, 0 slides); write the real format and counts."""
    tmp = Path(tempfile.mkdtemp()) / "deck.pptx"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                x = data.decode("utf-8")
                x = re.sub(r"<PresentationFormat>.*?</PresentationFormat>", "<PresentationFormat>Widescreen</PresentationFormat>", x)
                x = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{n_slides}</Slides>", x)
                x = re.sub(r"<Notes>\d+</Notes>", f"<Notes>{n_slides}</Notes>", x)
                x = re.sub(r"<HeadingPairs>.*?</HeadingPairs>", "", x, flags=re.S)
                x = re.sub(r"<TitlesOfParts>.*?</TitlesOfParts>", "", x, flags=re.S)
                data = x.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(str(tmp), str(path))
    shutil.rmtree(tmp.parent, ignore_errors=True)


def finalize():
    prs.save(OUT)
    fix_app_xml(OUT, len(prs.slides))
    SOURCES_JSON.write_text(json.dumps(slide_metadata, ensure_ascii=False, indent=2))
    print(json.dumps({"slides": len(prs.slides), "out": str(OUT), "warnings": len(WARN)}, ensure_ascii=False))
    for w in WARN:
        print("WARN", w)
    assert len(prs.slides) == len(FINAL_TITLES), (len(prs.slides), len(FINAL_TITLES))


# =====================================================================================================
# Chapter 1
# =====================================================================================================
divider(CHAPTERS[0])

# 4 ------------------------------------------------------------------------------------------------
expect(T_Q)
s = new_slide(
    k(T_Q, "経営の問い"), T_Q,
    "EBITDAが基準から動くと、どの事業のどのイベントが、どの契約を通じて効いたのかが問われます。\n"
    "答えるには、複数部門のデータを突き合わせる作業が要ります。",
    """【話す】経営会議では、EBITDAが基準から動いたとき、金額の大きさだけでなく、次の4つが問われます。どこで動いたか、どのイベントが効いたか、何が根拠か、どこから手を打つか、です。
【指す】4枚のカードを左から順に。下段は、それぞれに答えるために必要なデータです。
【補足】この4つの問いが、第2章のデモで、Data Agentに入力する4つの質問①〜④に対応します。""",
    ["デモの設計（質問①〜④）"],
    "この4つの問いが、第2章のデモの質問①〜④に対応します。")
steps = [
    ("どこで動いたか", "会社や事業ごとの損益を見て、動いた場所を特定します。", "会社別、事業別の損益"),
    ("何が効いたか", "イベントごとの増減を並べ、大きく効いたものを選びます。", "イベントの一覧と影響額"),
    ("根拠は何か", "影響額から、契約、取引、元の記録までさかのぼります。", "契約、取引、記録の関係"),
    ("何から手を打つか", "影響額と重なりを見て、対応する契約の順番を決めます。", "契約別の影響額と重なり"),
]
cw, gap = 2.85, (12.13 - 4 * 2.85) / 3
for i, (head, body, need) in enumerate(steps):
    x = .6 + i * (cw + gap)
    box(s, x, 2.4, cw, 3.75, WHITE, LINE)
    numdot(s, str(i + 1), x + .45, 2.92, .27, TEAL, size=15)
    text(s, head, x + .25, 3.45, cw - .5, .45, 18, NAVY, True, spacing=1.2)
    text(s, body, x + .25, 4.05, cw - .5, 1.2, 14.5, INK, spacing=1.4)
    box(s, x + .2, 5.4, cw - .4, .62, PALE, None, radius=.08)
    text(s, [[("必要なデータ", {"size": 10.5, "color": MUTED, "bold": True})],
             [(need, {"size": 12, "color": NAVY, "bold": True})]], x + .3, 5.45, cw - .6, .54, 12,
         spacing=1.2)
    if i < 3:
        arrow(s, x + cw + .02, 2.92, x + cw + gap - .02, 2.92, TEAL, width=2.0)

# 5 ------------------------------------------------------------------------------------------------
expect(T_STRUCT)
s = new_slide(
    k(T_STRUCT, "理由を出しにくい構造"), T_STRUCT,
    "金額が揃っていても、理由を出すには、表のつなぎ方と言葉の意味を知る担当者の手が要ります。\n"
    "質問のたびに、この作業が繰り返されます。",
    """【話す】金額そのものは、各システムやBIにあります。難しいのは理由です。理由を出すには、表をどうつなぐか、この言葉が何を指すかを知っている担当者の手が要り、質問のたびに繰り返されます。
【指す】3つのカードを左から順に。各カードの下段は、このデモで該当する場面です。
【補足】本資料の「Ontology」は、②と③を、データの外に定義して共有する層として説明します。""",
    ["デモ環境の設計", "Data Agentの指示文（用語と既定値の定義）"],
    trace=["prompts/da_instructions_ja.txt"],
    takeaway="②のつながりと③の言葉の意味を、データの外に定義して共有する層が、次ページのOntologyです。")
causes = [
    ("データが分散している", "会社、事業、通貨ごとに別の表やシステムにあり、全体を見るたびに集め直します。",
     "デモ：8社の原本を、\n会社ごとの別Lakehouseに保持"),
    ("つながりの記録がない",
     "イベントから契約、会社、全社の数字へのつながりは、詳しい担当者の頭の中や、個別のクエリの中にあることが多くなります。",
     "デモ：イベント、影響額、契約、\n会社、全社KPIのつながり"),
    ("言葉の意味が揺れる",
     "同じEBITDAでも、全額連結か持分管理か、基準が予算か見通しかは、部門や資料によって異なります。",
     "デモ：持分51%の会社を、\n全額で見るか持分で見るか"),
]
for i, (head, body, demo) in enumerate(causes):
    x = .6 + i * 4.09
    box(s, x, 2.4, 3.95, 3.75, WHITE, LINE)
    numdot(s, str(i + 1), x + .45, 2.92, .27, CORAL if i else TEAL, size=15)
    text(s, head, x + .25, 3.4, 3.45, .4, 19, NAVY, True, spacing=1.2)
    text(s, body, x + .25, 3.95, 3.45, 1.5, 14.5, INK, spacing=1.4)
    box(s, x + .2, 5.4, 3.55, .62, PALE, None, radius=.08)
    text(s, demo, x + .35, 5.4, 3.3, .62, 11.5, NAVY, True, anchor=MIDDLE, spacing=1.2)

# 6 ------------------------------------------------------------------------------------------------
expect(T_WHAT)
s = new_slide(
    k(T_WHAT, "Ontologyとは"), T_WHAT,
    "定義を、データの置き場所と切り離して管理できます。\n"
    "その定義を一度作り、人もAIも同じ形で参照できるようにします。",
    """【話す】Ontologyは、Microsoft Fabric IQの機能で、会社、契約、イベントといった業務の言葉と、それらのつながりを定義する層です。データそのものは持たず、定義とデータへの結び付けだけを持ちます。人もAIエージェントも、同じ定義を参照して答えを出せます。
【指す】左の図を、下のデータから上の使う側へ。参照するデータはそれぞれの場所に残り、Ontologyが結び付けを持ち、その定義を使う側が参照します。右の2枚は、Ontologyが持つものと持たないものです。
【補足】Microsoft Learnは、Ontologyを「ビジネスの共有された、機械が理解できる表現」と説明しています。Ontology自体は汎用のクエリエンジンではなく、利用する側が、結び付けたデータに対して実行します。使う側として対応しているエージェントは、Data Agent、Operations agent、Foundry IQ、Copilot Studio、MCP接続のカスタムエージェントなどです（対応状況は製品ごとに異なります）。
【注意】Previewの機能です。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）",
     "Microsoft Learn：fabric/iq/ontology/concepts-agent-integration（2026-09-15更新）"],
    "使う側として対応しているかどうかは、製品ごとに異なります。Previewの機能で、仕様は変わる場合があります。")
LX, LW = 1.95, 6.5
layers = [("使う側", 2.35, .95), ("意味の層", 3.85, 1.15), ("データ", 5.5, .7)]
for label, y, h in layers:
    text(s, label, .6, y, 1.2, h, 15, TEAL, True, anchor=MIDDLE, spacing=1.0)
users = [("Data Agent", "日本語で質問"), ("Copilot Studioなど", "対応は製品ごと"), ("独自のエージェント", "MCPで接続")]
for i, (a, b) in enumerate(users):
    bx = LX + i * (2.05 + .175)
    box(s, bx, 2.35, 2.05, .95, WHITE, LINE)
    text(s, [[(a, {"bold": True, "size": 13, "color": NAVY})], [(b, {"size": 11, "color": MUTED})]],
         bx + .12, 2.35, 1.85, .95, 13, anchor=MIDDLE, spacing=1.25)
for _ux in (2.975, 5.2, 7.425):
    arrow(s, _ux, 3.82, _ux, 3.33, TEAL, width=2.25)
text(s, "同じ定義を参照", 3.3, 3.42, 1.8, .3, 12, TEAL, True, CENTER, spacing=1.0)
box(s, LX, 3.85, LW, 1.15, WHITE, TEAL, lw=2.0)
text(s, "Ontology", LX + .2, 3.92, 2.5, .34, 18, TEAL, True, spacing=1.0)
text(s, "業務の言葉で、一度だけ定義する", LX + 1.95, 3.97, 4.4, .3, 12.5, INK, spacing=1.0)
for i, name in enumerate(["概念", "属性", "関係", "ルール・指標"]):
    chip(s, name, LX + .2 + i * 1.55, 4.46, 1.4 if i < 3 else 1.55, TEAL, PALE, 12, .36)
arrow(s, 5.2, 5.47, 5.2, 5.03, TEAL, width=2.25)
text(s, "結び付け（参照するデータは移さない）", 5.35, 5.1, 3.1, .3, 12, TEAL, True, spacing=1.0)
sources_data = ["Lakehouse、\nWarehouse", "Eventhouse", "SQLデータベース", "Power BI\nセマンティック\nモデル"]
for i, name in enumerate(sources_data):
    bx = LX + i * 1.65
    box(s, bx, 5.5, 1.55, .7, GRAY, None)
    text(s, name, bx + .05, 5.5, 1.45, .7, 10.5, INK, True, CENTER, MIDDLE, spacing=1.15)
box(s, 8.8, 2.35, 3.93, 1.85, WHITE, LINE)
text(s, "Ontologyが持つもの", 9.05, 2.5, 3.5, .32, 16, TEAL, True, spacing=1.0)
text(s, "・概念、属性、関係の定義\n・ルールと指標（Preview）\n・データへの結び付け", 9.05, 2.95, 3.5, 1.15, 13.5, INK,
     spacing=1.45)
box(s, 8.8, 4.35, 3.93, 1.85, WHITE, LINE)
text(s, "Ontologyが持たないもの", 9.05, 4.5, 3.5, .32, 16, CORAL, True, spacing=1.0)
text(s, "・データそのもの（元の場所に残る）\n・問い合わせの実行（利用側が行う）", 9.05, 4.95, 3.5, 1.2, 13.5,
     INK, spacing=1.45)

# 7 ------------------------------------------------------------------------------------------------
expect(T_PARTS)
s = new_slide(
    k(T_PARTS, "Ontologyの構成要素"), T_PARTS,
    "左は、Ontologyの4つの部品と、このデモでの例です。\n"
    "右は、このデモの定義のうち、イベントから全社KPIまでの主な関係です。",
    """【話す】Ontologyは、概念、属性、関係、ルールの4つで業務を表します。このデモでは、会社、契約、イベント、影響額など17種類の概念と、それらをつなぐ39種類の関係を定義しています。ルールと指標は新しい機能で、このデモではまだ使っていません。
【指す】左の4枚で部品の意味を、右の図で、このデモの定義のうち主な関係を示します。矢印は関係の向きです。
【補足】右の図は種類（型）の定義です。実際のデータで同じ関係をたどった例は、第2章の「根拠記録から全社KPIまでの経路が見える」のページにあります。""",
    ["デモのOntology定義（17種類の概念、39種類の関係）", "Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）"],
    trace=["ontology_tmdl/entities", "ontology_tmdl/entityRelationships.tmdl"],
    takeaway=f"このデモの全体は、17種類の概念と39種類の関係です（p.{PAGE_OF[T_A_MAP]}）。"
    "質問ごとに必要な範囲は、第5章で示します。")
parts = [
    ("概念（エンティティ）", TEAL, "業務に登場する「もの」や「こと」", "例：会社、契約、イベント、影響額（17種類）"),
    ("属性（プロパティ）", PURPLE, "概念が持つ項目", "例：契約ID、日付、金額、通貨、所有比率"),
    ("関係", CORAL, "概念どうしのつながり", "例：イベントが影響額を生む（39種類）"),
    ("ルール・指標", NAVY, "業務の決まりと、共通の計算（Preview）", "例：全額連結と持分管理の区別。デモでは未実装"),
]
for i, (name, color, desc, ex) in enumerate(parts):
    y = 2.35 + i * 1.0
    box(s, .6, y, 5.2, .9, WHITE, LINE)
    box(s, .62, y + .09, .07, .72, color, None, radius=.035)
    text(s, name, .88, y + .08, 4.8, .28, 15, color, True, spacing=1.0)
    text(s, desc, .88, y + .38, 4.8, .22, 12, INK, spacing=1.0)
    text(s, ex, .88, y + .63, 4.8, .22, 11, MUTED, spacing=1.0)
box(s, 6.0, 2.35, 6.73, 3.9, WHITE, LINE)
text(s, "このデモの定義（主な関係のみ）", 6.25, 2.5, 5.0, .3, 13, TEAL, True, spacing=1.0)
NW, NH, GX, X0, Y0, GY = 1.3, .66, .44, 6.2, 3.0, .45


def tnode(col, row, jp, en, color):
    x, y = X0 + col * (NW + GX), Y0 + row * (NH + GY)
    box(s, x, y, NW, NH, WHITE, color, lw=1.75, radius=.07)
    text(s, [[(jp, {"bold": True, "size": 12.5, "color": INK})], [(en, {"size": 10, "color": MUTED})]],
         x, y, NW, NH, 12, align=CENTER, anchor=MIDDLE, spacing=1.15)
    return x, y


def harrow(c1, c2, row, label):
    x1 = X0 + c1 * (NW + GX) + NW + .03
    x2 = X0 + c2 * (NW + GX) - .03
    ym = Y0 + row * (NH + GY) + NH / 2
    arrow(s, x1, ym, x2, ym, STEEL, width=1.75)
    text(s, label, x1 - .12, ym - .3, x2 - x1 + .24, .22, 10, STEEL, True, CENTER, spacing=1.0)


def varrow(col, r1, r2, label):
    xm = X0 + col * (NW + GX) + NW / 2
    y1 = Y0 + r1 * (NH + GY) + (0 if r2 < r1 else NH) + (-.03 if r2 < r1 else .03)
    y2 = Y0 + r2 * (NH + GY) + (NH if r2 < r1 else 0) + (.03 if r2 < r1 else -.03)
    arrow(s, xm, y1, xm, y2, STEEL, width=1.75)
    text(s, label, xm + .12, (y1 + y2) / 2 - .1, .9, .22, 10, STEEL, True, spacing=1.0)


tnode(0, 1, "イベント", "RiskEvent", PURPLE)
tnode(1, 1, "影響額", "FinancialEffect", CORAL)
tnode(2, 1, "取引活動", "Activity", NAVY)
tnode(3, 1, "契約", "Contract", NAVY)
tnode(1, 0, "根拠", "Evidence", STEEL)
tnode(3, 0, "会社", "Company", TEAL)
tnode(1, 2, "日次指標", "FinancialMetric", TEAL)
tnode(2, 2, "全社KPI", "GroupKPI", TEAL)
harrow(0, 1, 1, "生む")
harrow(1, 2, 1, "対象")
harrow(2, 3, 1, "属する")
harrow(1, 2, 2, "集約")
varrow(1, 1, 0, "根拠で説明")
varrow(1, 1, 2, "反映")
varrow(3, 1, 0, "所有者")
text(s, "矢印は関係の向き。全体の一覧は付録2", 6.25, 5.9, 6.2, .24, 11, MUTED, spacing=1.0)


# =====================================================================================================
# Chapter 2
# =====================================================================================================
divider(CHAPTERS[1])


def ask_card(s, x, y, w, h, question, size=18):
    """The text typed into the Data Agent."""
    box(s, x, y, w, h, WHITE, TEAL, lw=1.75)
    text(s, "Data Agentへの入力", x + .22, y + .13, w - .44, .22, 11, TEAL, True, spacing=1.0)
    text(s, question, x + .22, y + .44, w - .44, h - .52, size, NAVY, True, spacing=1.3)


def label_value_rows(s, x, y, w, rows, row_h=.62, size=22, label_size=12):
    for i, (label, value, color) in enumerate(rows):
        yy = y + i * row_h
        text(s, label, x, yy, w * .46, row_h, label_size, MUTED, True, anchor=MIDDLE, spacing=1.0)
        text(s, value, x + w * .3, yy, w * .7, row_h, size, color, True, RIGHT, MIDDLE, spacing=1.0)
        if i:
            box(s, x, yy, w, .01, LINE, None, rounded=False)


# 9 ------------------------------------------------------------------------------------------------
expect(T_SETTING)
s = new_slide(
    k(T_SETTING, "デモの設定"), T_SETTING,
    "事業、通貨、所有比率が異なる8社の数字を、同じ定義でJPYに揃えて扱う設定です。\n"
    "データはすべて架空で、為替だけがECBの公表する実データです。",
    f"""【話す】今日のデモは、架空の総合商社グループです。金属、エネルギー、食品、金融の4事業に、日本と米国の会社が1社ずつ、合計8社あります。通貨は円とドル、所有比率は100%と51%が混在しています。月次の経営会議で、EBITDAが基準から動いた理由を問われる場面を想定しています。
【指す】左の表で8社を、右で規模を示します。EBITDAは年間で約{round(ACTUAL / OKU)}億円、売上は約{round(revenue / OKU):,}億円です（実績、全額連結、JPY）。
【金額の見方】全額連結は、支配する8社を100%で合算した値です。持分管理は、各社の値に所有比率（100%または51%）を掛けて合算した値です。いずれも、連結財務諸表の数値ではなく、デモ用の管理値です。
【前提】会社、契約、イベント、影響額は架空です。為替だけは、ECBが公表する日次の参考レートです。実在の企業の実績や業界の標準的な規模を表すものではありません。""",
    ["デモ環境の設計", "ECB公表の日次参考レート"],
    takeaway="デモで示すのは分析の進め方です。金額や会社の動きは、実在の企業の実績を表すものではありません。",
    trace=["config/subsidiaries.json", "data/demo_dataset.json:semantic_financial_metrics_daily"])
rows = []
for sub in subsidiaries:
    rows.append([SECTOR_JP[sub["sector_code"]], sub["entity_name"],
                 f"{'日本' if sub['country_code'] == 'JP' else '米国'}／{sub['currency_code']}",
                 f"{int(Decimal(sub['ownership_ratio']) * 100)}%"])
TX, TW = .6, 7.3
box(s, TX, 2.35, TW, 3.9, WHITE, LINE)
cols = [(.25, 1.25, "事業"), (1.5, 3.3, "会社名"), (4.85, 1.35, "国／通貨"), (6.3, .85, "所有比率")]
for cx, cwid, label in cols:
    text(s, label, TX + cx, 2.47, cwid, .26, 11.5, TEAL, True, spacing=1.0)
for i, row in enumerate(rows):
    y = 2.82 + i * .42
    if (i // 2) % 2 == 1:
        box(s, TX + .08, y - .02, TW - .16, .4, PALE, None, radius=.06)
    for (cx, cwid, _), val, bold, color in zip(cols, row, (True, True, False, True), (TEAL, NAVY, INK, INK)):
        text(s, val, TX + cx, y + .02, cwid, .34, 13, color, bold, anchor=MIDDLE, spacing=1.0)
tiles = [(f"約{round(ACTUAL / OKU)}億円", "年間EBITDA\n（実績、全額連結）", TEAL),
         (f"約{round(revenue / OKU):,}億円", "年間売上\n（実績）", NAVY),
         (f"{N_EVENTS}件", "イベント\n（プラス5・マイナス5）", PURPLE),
         (f"{N_EFFECTS:,}件", "影響額の明細\n（イベントと取引の組）", CORAL)]
for i, (big, small, color) in enumerate(tiles):
    x = 8.15 + (i % 2) * 2.33
    y = 2.35 + (i // 2) * 1.32
    box(s, x, y, 2.25, 1.22, WHITE, LINE)
    text(s, big, x + .18, y + .12, 2.0, .42, 21, color, True, spacing=1.0)
    text(s, small, x + .18, y + .6, 1.95, .55, 11, MUTED, spacing=1.2)
box(s, 8.15, 5.05, 4.58, 1.2, PALE, None)
text(s, "2つの金額の見方", 8.35, 5.15, 4.2, .26, 13, TEAL, True, spacing=1.0)
text(s, "全額連結：8社の値を100%で合算\n持分管理：8社の値に所有比率を掛けて合算", 8.35, 5.5, 4.2, .7, 12.5, NAVY, spacing=1.4)

# 10 -----------------------------------------------------------------------------------------------
expect(T_FLOW)
s = new_slide(
    k(T_FLOW, "デモの流れ"), T_FLOW,
    "経営会議の流れと同じ順に、Data Agentへ日本語で質問します。\n"
    "前半の2問は集計で答え、後半の2問は、Ontologyの関係から表のつなぎ方を決めて答えます。",
    """【話す】質問は4つです。①全体の動き、②効いたイベント、③その根拠、④どこから手を打つか。経営会議で問われる順に、短い日本語で入力します。
【指す】各カードの上段が入力する質問、中段が回答の要点、下段が答えの出し方です。②は、最大の押し下げと最大の押し上げを続けて2問入力します。①と②は、集計で答えられる質問です。③と④では、Data AgentがOntologyの関係から、表のつなぎ方を決めて答えました。
【補足】今回の確認では、Data Agentが③と④で、Ontologyの経路探索を使い、イベントから全社KPIまで、またイベントから会社までの経路を見つけました（2026-10-27、公開済みのData Agent、各1回）。①と②では、経路探索は使われていません。回答の金額は、元データの集計と一致することを確認しています。ただし、Data Agentは言語モデルのため、回答の文面は実行ごとに変わる場合があります。
【注意】実際の答えは、Ontologyの関係から決めた表のつなぎ方で、元のデータに対するSQLの集計として出しています。Graphへの問い合わせは使っていません。""",
    ["デモ環境での確認（2026-10-27、公開済みのData Agent）"],
    takeaway="回答の金額は、元データの集計と一致しました（2026-10-27、各質問1回）。文面は実行ごとに変わります。",
    trace=["reports/da_traversal_fix_2026-10-27.json", "reports/da_casual_after_2026-10-26.json"])
flow = [
    ("全体", "今期のEBITDAって、\n予算に対して\nどうだった？",
     f"想定値との差{fmt(GAP)}億円\n（{str(GAP_PCT).replace(chr(45), MINUS)}%）", False),
    ("原因", [[("一番足を引っ張った", {})], [("イベントは？", {})],
            [("※プラス側も続けて質問", {"size": 11, "color": MUTED, "bold": False})]],
     f"横断混乱（港湾・流動性）\n{fmt(EV['CROSS_NEG'])}億円", False),
    ("根拠", "食品の損失は、\nどの契約に響いたの？",
     f"6契約に効き、\n合計{fmt(EV['FOD_NEG'])}億円", True),
    ("打ち手", "いま手を打つべき\n契約ってどれ？", "貿易金融の4契約を\n高優先と提案", True),
]
for i, (name, ask, ans, rel) in enumerate(flow):
    x = .6 + i * (cw + gap)
    box(s, x, 2.35, cw, 3.85, WHITE, LINE)
    numdot(s, str(i + 1), x + .42, 2.85, .24, TEAL, size=14)
    text(s, name, x + .8, 2.58, 1.8, .55, 20, NAVY, True, anchor=MIDDLE, spacing=1.0)
    text(s, "入力する質問", x + .25, 3.3, cw - .5, .22, 10.5, MUTED, True, spacing=1.0)
    text(s, ask, x + .25, 3.56, cw - .5, .95, 14, INK, True, spacing=1.35)
    box(s, x + .25, 4.58, cw - .5, .01, LINE, None, rounded=False)
    text(s, "回答の要点", x + .25, 4.67, cw - .5, .22, 10.5, MUTED, True, spacing=1.0)
    text(s, ans, x + .25, 4.93, cw - .5, .7, 13.5, CORAL if i < 3 else NAVY, True, spacing=1.3)
    chip(s, "関係から表を結んで回答" if rel else "集計で回答", x + .25, 5.68, cw - .5,
         TEAL if rel else STEEL, PALE if rel else GRAY, 11.5, .36)
    if i < 3:
        arrow(s, x + cw + .02, 2.85, x + cw + gap - .02, 2.85, TEAL, width=2.0)

# 11 -----------------------------------------------------------------------------------------------
expect(T_Q1)
s = new_slide(
    k(T_Q1, "質問① 全体"), T_Q1,
    "年間の差だけを見ると小さくても、月次では大きな差が出ている場合があります。\n"
    "最初に、全体の動きと差の大きい月を押さえてから、原因に進みます。",
    f"""【入力】「今期のEBITDAって、予算に対してどうだった？」と日本語で入力します。
【回答の要点】今期（2025-10-01〜2026-09-30）の全額連結EBITDAは{oku(ACTUAL)}億円、基準値は{oku(BASELINE)}億円（イベントの影響を加える前の想定値で、デモでは予算に相当）で、差は{fmt(GAP)}億円（{str(GAP_PCT).replace('-', MINUS)}%）です。
【指す】右の折れ線は、月次の基準値（点線）と実績（実線）です。差が最も大きい月は2026-05（{fmt(DEV[WORST])}億円）と2026-09（{fmt(DEV[BEST])}億円）です。この2か月は、次の質問で見る横断イベント（5月11日〜31日、9月1日〜21日）の期間と重なります。
【補足】この質問は集計で答えられる範囲で、Ontologyの関係を使わなくても答えが出ます。基準値は、イベントの影響を加える前の想定値、実績は、イベントの影響を反映した値です。デモでは、予算を基準値として扱っています。
【注意】回答は、Data Agentの実行ごとに文面や表示が変わる場合があります。金額は、元データの集計と一致することを確認しています。""",
    ["デモ環境での確認（2026年10月26日、公開済みのData Agent、3回中3回で同じ金額）", "デモデータの月次集計"],
    takeaway="差が大きい2026-05と2026-09は、横断イベント（5月11日〜31日、9月1日〜21日）の期間と重なります。次の質問で分解します。",
    trace=["reports/da_casual_after_2026-10-26.json:final_checks_published.casual", "data/demo_dataset.json"])
ask_card(s, .6, 2.35, 4.15, 1.3, "今期のEBITDAって、\n予算に対してどうだった？", 18)
box(s, .6, 3.8, 4.15, 2.45, WHITE, LINE)
text(s, "回答の要点", .82, 3.93, 3.7, .22, 11, TEAL, True, spacing=1.0)
label_value_rows(s, .82, 4.2, 3.7, [
    ("実績（全額連結）", f"{oku(ACTUAL)}億円", NAVY),
    ("基準値", f"{oku(BASELINE)}億円", NAVY),
    (f"差（{str(GAP_PCT).replace(chr(45), MINUS)}%）", f"{fmt(GAP)}億円", CORAL)], row_h=.54, size=20)
text(s, "基準値は、イベントの影響を加える前の想定値です。デモでは予算に相当します。", .82, 5.82, 3.7, .4, 11, MUTED,
     spacing=1.2)
# line chart drawn with shapes so that every renderer shows the same picture
box(s, 4.95, 2.35, 7.78, 3.9, WHITE, LINE)
text(s, "月次のEBITDA（億円、全額連結）", 5.2, 2.48, 4.0, .28, 13, TEAL, True, spacing=1.0)
arrow(s, 9.15, 2.62, 9.6, 2.62, STEEL, dashed=True, width=2.25, head=False)
text(s, "基準値", 9.68, 2.5, 1.5, .24, 11.5, MUTED, True, spacing=1.0)
arrow(s, 11.15, 2.62, 11.6, 2.62, TEAL, width=2.75, head=False)
text(s, "実績", 11.68, 2.5, 0.8, .24, 11.5, MUTED, True, spacing=1.0)
PX0, PX1, PYT, PYB, VMIN, VMAX = 5.95, 12.3, 3.0, 5.35, 28.0, 44.0


def px(i):
    return PX0 + i * (PX1 - PX0) / 11


def py(v):
    return PYB - (v - VMIN) / (VMAX - VMIN) * (PYB - PYT)


for gv in (28, 32, 36, 40, 44):
    box(s, PX0 - .15, py(gv), PX1 - PX0 + .3, .008, LINE, None, rounded=False)
    text(s, str(gv), 5.2, py(gv) - .1, .55, .2, 10.5, MUTED, False, RIGHT, spacing=1.0)
base = [float(oku(monthly[m]["baseline"])) for m in MONTHS]
act = [float(oku(monthly[m]["actual"])) for m in MONTHS]
for i in range(11):
    arrow(s, px(i), py(base[i]), px(i + 1), py(base[i + 1]), STEEL, dashed=True, width=2.25, head=False)
    arrow(s, px(i), py(act[i]), px(i + 1), py(act[i + 1]), TEAL, width=2.75, head=False)
for i in range(12):
    oval(s, px(i), py(base[i]), .045, STEEL)
    oval(s, px(i), py(act[i]), .06, TEAL, WHITE, 1.0)
    label = f"{int(MONTHS[i][5:])}月"
    text(s, label, px(i) - .3, PYB + .1, .6, .22, 10.5, INK, False, CENTER, spacing=1.0)
text(s, "2025年", px(1) - .4, PYB + .36, .8, .22, 10.5, MUTED, True, CENTER, spacing=1.0)
text(s, "2026年", px(6) - .4, PYB + .36, .8, .22, 10.5, MUTED, True, CENTER, spacing=1.0)
wi, bi = MONTHS.index(WORST), MONTHS.index(BEST)
arrow(s, px(wi), py(base[wi]) + .07, px(wi), py(act[wi]) - .08, CORAL, width=1.75, head=False)
text(s, f"2026-05　差 {fmt(DEV[WORST])}", px(wi) - 1.0, py(act[wi]) + .1, 2.0, .24, 11.5, CORAL, True, CENTER,
     spacing=1.0)
arrow(s, px(bi), py(base[bi]) - .07, px(bi), py(act[bi]) + .08, TEAL, width=1.75, head=False)
text(s, f"2026-09　差 {fmt(DEV[BEST])}", px(bi) - 2.05, py(act[bi]) - .36, 2.0, .24, 11.5, TEAL, True, RIGHT,
     spacing=1.0)

# 12 -----------------------------------------------------------------------------------------------
expect(T_Q2)
CHART_LABEL = {"CROSS_NEG": "横断混乱（全事業）", "MTL_NEG": "製錬停止（金属）",
               "ENE_NEG": "LNG基地の整備遅れ（エネルギー）",
               "FIN_NEG": "取引先対応コスト増（金融）", "FOD_NEG": "食品損失（食品）",
               "CROSS_POS": "横断回復（全事業）", "ENE_POS": "貯蔵配分の最適化（エネルギー）",
               "MTL_POS": "再生合金契約（金属）", "FOD_POS": "調達改善（食品）", "FIN_POS": "ヘッジ手数料の増収（金融）"}
neg_keys = sorted([e for e in EV if e.endswith("_NEG")], key=lambda e: EV[e])
pos_keys = sorted([e for e in EV if e.endswith("_POS")], key=lambda e: -EV[e])
assert neg_keys[0] == "CROSS_NEG" and pos_keys[0] == "CROSS_POS" and len(neg_keys) == len(pos_keys) == 5
s = new_slide(
    k(T_Q2, "質問② 原因"), T_Q2,
    f"年間の差{fmt(GAP)}億円は、{fmt(NEG_SUM)}億円の押し下げと{fmt(POS_SUM)}億円の押し上げが重なった結果です。\n"
    "合計だけでは、どのイベントが効いたのかが分かりません。",
    f"""【入力】「一番足を引っ張ったイベントは？」「逆に、一番プラスになったのは？」と続けて入力します。
【回答の要点】最大の押し下げは横断混乱（港湾・流動性の混乱）で{fmt(EV['CROSS_NEG'])}億円、最大の押し上げは横断回復（物流・資金の回復）で{fmt(EV['CROSS_POS'])}億円です。どちらも4事業8社に及ぶイベントです。
【指す】右の棒グラフは、全10イベントの影響額（全額連結）です。マイナス5件の合計が{fmt(NEG_SUM)}億円、プラス5件の合計が{fmt(POS_SUM)}億円で、差し引きが年間の差{fmt(NEG_SUM + POS_SUM)}億円になります。残りの8件は、1つの事業の2社に限られるイベントです。
【補足】合計では小さく見える差も、押し下げと押し上げが打ち消し合っている場合があります。イベントごとに分けて見ると、手を打つ対象が分かります。
【注意】影響額は、デモのために設計した配賦で、実世界の因果の証明ではありません。Data Agentの回答では、「取引先対応コスト増」が「与信費増」と表記される場合があります。""",
    ["デモ環境での確認（2026年10月27日、公開済みのData Agent）", "デモデータ（10件のイベントと影響額）"],
    takeaway="最大の押し下げは横断混乱です。次の質問では、食品損失を例に、根拠の記録まで影響額をさかのぼります。",
    trace=["reports/qa_expected_event_totals.json", "reports/da_traversal_fix_2026-10-27.json:demo_questions.Q2"])
box(s, .6, 2.35, 3.95, 1.75, WHITE, TEAL, lw=1.75)
text(s, "Data Agentへの入力（続けて2問）", .82, 2.48, 3.5, .22, 11, TEAL, True, spacing=1.0)
text(s, "一番足を引っ張った\nイベントは？", .82, 2.8, 3.5, .6, 15, NAVY, True, spacing=1.3)
box(s, .82, 3.47, 3.5, .01, LINE, None, rounded=False)
text(s, "逆に、一番プラスに\nなったのは？", .82, 3.55, 3.5, .6, 15, NAVY, True, spacing=1.3)
box(s, .6, 4.25, 3.95, 2.0, WHITE, LINE)
text(s, "回答の要点", .82, 4.37, 3.5, .22, 11, TEAL, True, spacing=1.0)
text(s, f"横断混乱　{fmt(EV['CROSS_NEG'])}億円", .82, 4.68, 3.55, .34, 16, CORAL, True, spacing=1.2)
text(s, "港湾・流動性の混乱。4事業8社に影響", .82, 5.06, 3.55, .24, 11.5, INK, spacing=1.2)
text(s, f"横断回復　{fmt(EV['CROSS_POS'])}億円", .82, 5.5, 3.55, .34, 16, TEAL, True, spacing=1.2)
text(s, "物流・資金の回復。4事業8社に影響", .82, 5.88, 3.55, .24, 11.5, INK, spacing=1.2)
box(s, 4.8, 2.35, 7.93, 3.9, WHITE, LINE)
text(s, "全10イベントの影響額（億円、全額連結）", 5.05, 2.45, 5.5, .28, 13, TEAL, True, spacing=1.0)
text(s, "括弧は影響が及ぶ事業。横断の2件は4事業8社、他の8件は1事業の2社", 5.05, 2.73, 7.5, .22, 10.5, MUTED, spacing=1.0)
ZX, SCALE, NAME_X, NAME_W = 10.3, 1.9 / 6.8, 5.05, 2.6
ROW = .235
y = 3.0


def group_header(label, color):
    global y
    text(s, label, NAME_X, y, 6.0, ROW, 11.5, color, True, anchor=MIDDLE, spacing=1.0)
    y += ROW


def bar_row(key, color):
    global y
    v = float(oku(EV[key]))
    text(s, CHART_LABEL[key], NAME_X, y, NAME_W, ROW, 11, INK, False, anchor=MIDDLE, spacing=1.0)
    length = abs(v) * SCALE
    bx = ZX - length if v < 0 else ZX
    box(s, bx, y + .04, length, ROW - .08, color, None, radius=.03)
    if v < 0:
        text(s, fmt(EV[key]), bx - .72, y, .66, ROW, 11, color, True, RIGHT, MIDDLE, spacing=1.0)
    else:
        text(s, fmt(EV[key]), bx + length + .06, y, .7, ROW, 11, color, True, anchor=MIDDLE, spacing=1.0)
    y += ROW


group_header(f"マイナス5件　合計 {fmt(NEG_SUM)}", CORAL)
for key in neg_keys:
    bar_row(key, CORAL)
y += .08
group_header(f"プラス5件　合計 {fmt(POS_SUM)}", TEAL)
for key in pos_keys:
    bar_row(key, TEAL)
box(s, NAME_X, y + .04, 7.4, .01, LINE, None, rounded=False)
text(s, [[(f"差し引き　{fmt(NEG_SUM + POS_SUM)}億円（実績 − 基準値）", {"size": 12, "bold": True, "color": NAVY}),
          ("　丸めのため、行の和と一致しない場合があります", {"size": 10, "bold": False, "color": MUTED})]],
     NAME_X, y + .06, 7.4, ROW, 12, anchor=MIDDLE, spacing=1.0)
box(s, ZX - .005, 3.0 + ROW, .01, ROW * 11 + .08, STEEL, None, rounded=False)

# 13 -----------------------------------------------------------------------------------------------
expect(T_Q3)
s = new_slide(
    k(T_Q3, "質問③ 根拠"), T_Q3,
    "金額の原因が分かったら、次は根拠の確認です。多くの場合、詳しい担当者が表をつなぎ直して調べます。\n"
    "ここでは日本語の質問だけで、影響した契約を特定します。次のページで根拠記録まで進みます。",
    f"""【入力】「食品の損失は、どの契約に響いたの？」と日本語で入力します。
【回答の要点】食品損失は6つの契約に効き、全額連結で{fmt(EV['FOD_NEG'])}億円、持分管理で{fmt(EV_MGMT['FOD_NEG'])}億円です。6契約は、持分51%の日本の食品会社と、持分100%の米国の食品会社の契約で、すべて製粉用小麦です。
【指す】右の表は、6契約の影響額です。日本の会社の契約は、持分51%を掛けた持分管理の額が、全額連結の約半分になります。
【補足】この回答では、Data AgentがOntologyの関係（イベント、影響額、根拠、取引活動、契約、日次指標、全社KPI）から、表のつなぎ方を見つけました。金額は、別の集計とも一致しています（2026年10月26日、Notebookでグラフをたどった84件の影響額の合計と、Deltaテーブルの集計の突合）。
【注意】影響額は、デモのために設計した配賦で、実世界の因果の証明ではありません。回答の文面は、実行ごとに変わる場合があります。""",
    ["デモ環境での確認（2026-10-27、公開済みのData Agent。6契約の金額を元データと照合）"],
    takeaway="Data Agentの金額は、元データの集計と一致しました。次のページで、根拠記録までの経路を示します。",
    trace=["reports/da_traversal_fix_2026-10-27.json:demo_questions.Q3", "reports/step3_live_audit.json",
           "data/demo_dataset.json:semantic_event_financial_effects"])
ask_card(s, .6, 2.35, 4.15, 1.3, "食品の損失は、\nどの契約に響いたの？", 18)
box(s, .6, 3.8, 4.15, 2.45, WHITE, LINE)
text(s, "回答の要点", .82, 3.93, 3.7, .22, 11, TEAL, True, spacing=1.0)
label_value_rows(s, .82, 4.2, 3.7, [("効いた契約", "6件", NAVY),
                                    ("全額連結", f"{fmt(EV['FOD_NEG'])}億円", CORAL),
                                    ("持分管理", f"{fmt(EV_MGMT['FOD_NEG'])}億円", CORAL)], row_h=.56, size=20)
text(s, "差は、持分51%の日本の会社を含むため", .82, 5.94, 3.7, .26, 11, MUTED, spacing=1.0)
box(s, 4.95, 2.35, 7.78, 3.9, WHITE, LINE)
text(s, "影響を受けた6契約（億円）", 5.2, 2.47, 5.0, .28, 13, TEAL, True, spacing=1.0)
text(s, "すべて製粉用小麦の契約。小数第3位まで表示するため、丸めで合計が合わない場合があります", 5.2, 2.74, 7.4, .24,
     11, MUTED, spacing=1.0)
TC = [(.25, 2.35, "契約ID", None), (2.65, 2.45, "会社", None), (5.1, .65, "持分", RIGHT),
      (5.85, .95, "全額連結", RIGHT), (6.8, .85, "持分管理", RIGHT)]
for cx, cwid, label, al in TC:
    text(s, label, 4.95 + cx, 3.1, cwid, .24, 11.5, TEAL, True, al, spacing=1.0)
for i, (cid, (full, mgmt)) in enumerate(FOD_ROWS):
    yy = 3.4 + i * .4
    if i % 2:
        box(s, 5.05, yy - .03, 7.58, .38, PALE, None, radius=.05)
    own = int(Decimal(next(x for x in subsidiaries if x["entity_id"] == contract[cid]["entity_id"])["ownership_ratio"]) * 100)
    vals = [cid, entity_name[contract[cid]["entity_id"]], f"{own}%", fmt(full, "0.001"), fmt(mgmt, "0.001")]
    for (cx, cwid, _, al), val, color in zip(TC, vals, (INK, INK, MUTED, CORAL, CORAL)):
        text(s, val, 4.95 + cx, yy + .02, cwid, .3, 12, color, color == CORAL, al, MIDDLE, spacing=1.0)
box(s, 5.05, 5.82, 7.58, .012, LINE, None, rounded=False)
text(s, "合計", 4.95 + .25, 5.86, 1.0, .3, 12.5, NAVY, True, anchor=MIDDLE, spacing=1.0)
text(s, fmt(EV["FOD_NEG"], "0.001"), 4.95 + 5.85, 5.86, .95, .3, 12.5, CORAL, True, RIGHT, MIDDLE, spacing=1.0)
text(s, fmt(EV_MGMT["FOD_NEG"], "0.001"), 4.95 + 6.8, 5.86, .85, .3, 12.5, CORAL, True, RIGHT, MIDDLE, spacing=1.0)

# 14 -----------------------------------------------------------------------------------------------
expect(T_PATH)
s = new_slide(
    k(T_PATH, "質問③ 根拠"), T_PATH,
    "金額だけでは、数字が正しい記録に基づくかを確認できません。\n"
    "関係をたどると、1件の影響額から根拠、取引、契約、全社の数字までを順に確認できます。",
    f"""【話す】前のページの金額が、どの記録に基づくのかを、Ontologyの関係をたどって確認します。ここでは、食品損失の影響額84件のうち、代表の1件を例にしています。
【指す】左上の「根拠記録」から、イベント、影響額へ進みます。影響額から、取引活動、契約へ、また日次の指標、全社のKPIへ進みます。取引活動には、観測記録（温度{MINUS}{abs(OBS['temperature_c']):.0f}℃、廃棄率{OBS['spoilage_percent']}%）が結び付いています。矢印の種類は、左上の凡例のとおりです。
【数字】代表の影響額は{yen(REP_EFFECT)}、同じ日（2026-02-11）の子会社の日次EBITDAは{yen(SUB_DAILY)}、全社の日次EBITDAは{yen(GROUP_DAILY)}です。食品損失の84件の合計は、前のページの{fmt(EV['FOD_NEG'])}億円と一致します。
【確認した範囲】全10イベント、{N_EFFECTS:,}件の影響額のすべてで、根拠から全社KPIまでの経路が、Graphで確認できました。2026年10月27日に関係を有効にしてGraphを更新した後の確認で、種類ごとのノード数とエッジ数は更新前と同じで、根拠から全社KPIまでの経路が完全な影響額は1,344件でした。食品損失の84件は、合計が前のページの金額と一致しました。
【補足】Graphは、経路そのものが重要な問い（複数のつながりを順にたどる、依存関係、到達可能性など）のための、Ontologyの任意の実行層です。集計や指標は、元のデータで実行できます。
【注意】金額は、デモのために設計した配賦で、実世界の因果の証明ではありません。""",
    ["デモ環境での確認（Graphの照会結果とDeltaテーブルの突合、2026年10月26日〜27日）",
     "Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）"],
    takeaway="表示したのは、食品損失の影響額84件のうち、代表の1件の経路です。金額は架空の設計配賦で、因果の証明ではありません。",
    trace=["reports/step3_live_audit.json", "reports/graph_all_event_paths.json"])
NW2, NH2, PITCH, RPITCH, X00, Y00 = 2.3, .92, 3.2, 1.32, .62, 2.4


def gx(c):
    return X00 + c * PITCH


def gy(r):
    return Y00 + r * RPITCH


def pnode(c, r, head, body, color, dash=False):
    node(s, gx(c), gy(r), NW2, NH2, head, body, color, WHITE, 12.5, 11, dash=dash)


def hedge(c1, c2, r, label, color, dashed=False):
    x1, x2, ym = gx(c1) + NW2 + .04, gx(c2) - .04, gy(r) + NH2 / 2
    arrow(s, x1, ym, x2, ym, color, dashed, 2.0)
    text(s, label, x1, ym - .29, x2 - x1, .22, 10.5, color if color != STEEL else MUTED, True, CENTER, spacing=1.0)


def vedge(c, r1, r2, label, color, dashed=False):
    xm = gx(c) + NW2 / 2
    y1 = gy(r1) + (NH2 + .04 if r2 > r1 else -.04)
    y2 = gy(r2) + (-.04 if r2 > r1 else NH2 + .04)
    arrow(s, xm, y1, xm, y2, color, dashed, 2.0)
    text(s, label, xm + .14, (y1 + y2) / 2 - .1, 1.8, .22, 10.5, color if color != STEEL else MUTED, True, spacing=1.0)


pnode(0, 0, "根拠記録", "業務ログ（架空）\n記録日 2026-02-09", STEEL)
pnode(0, 1, "イベント", "食品損失\n廃棄事故", PURPLE)
pnode(1, 1, "影響額", f"{yen(REP_EFFECT)}\n（84件のうち代表の1件）", CORAL)
pnode(2, 1, "取引活動", "外部販売 2026-02-11\n" + entity_name[path["entity_id"]], NAVY)
pnode(3, 1, "契約", f"{path['contract_id']}\n製粉用小麦", NAVY)
pnode(2, 0, "観測記録", f"温度 {MINUS}{abs(OBS['temperature_c']):.0f}℃、廃棄率 {OBS['spoilage_percent']}%\n（食品会社の観測値）", STEEL)
pnode(1, 2, "子会社の日次EBITDA", f"{yen(SUB_DAILY)}\n2026-02-11（実績）", TEAL)
pnode(2, 2, "全社の日次EBITDA", f"{yen(GROUP_DAILY)}\n2026-02-11（実績）", TEAL)
vedge(0, 0, 1, "裏付け", STEEL, True)
hedge(0, 1, 1, "生む", PURPLE)
hedge(1, 2, 1, "対象の活動", STEEL, True)
hedge(2, 3, 1, "属する", STEEL, True)
vedge(2, 0, 1, "活動の観測", STEEL, True)
vedge(1, 1, 2, "日次指標に反映", TEAL)
hedge(1, 2, 2, "集約", TEAL)
box(s, gx(1), gy(0), NW2, NH2, WHITE, LINE)
for i, (color, dashed, label) in enumerate([(STEEL, True, "つながり（関係）"),
                                            (PURPLE, False, "配賦（金額の割当）"),
                                            (TEAL, False, "集約（金額の合算）")]):
    yy = gy(0) + .2 + i * .27
    arrow(s, gx(1) + .2, yy, gx(1) + .6, yy, color, dashed, 2.0, head=True)
    text(s, label, gx(1) + .72, yy - .1, 1.5, .22, 10.5, INK, False, spacing=1.0)
box(s, gx(3), gy(0), NW2, 1.2, PALE, TEAL, lw=1.25)
text(s, [[(f"全10イベント・{N_EFFECTS:,}件の影響額で、同じ経路をたどれました", {"size": 11, "bold": True, "color": NAVY})],
         [("Graphで確認（2026年10月27日）", {"size": 11, "bold": False, "color": MUTED})]],
     gx(3) + .15, gy(0) + .06, NW2 - .3, 1.08, 11, anchor=MIDDLE, spacing=1.25, after=3)

# 15 -----------------------------------------------------------------------------------------------
expect(T_Q4)
HIGH = [r for r in q_act if r["priority"] == "高"]
hi_lo = min(Decimal(str(r["full_oku"])) for r in HIGH)
hi_hi = max(Decimal(str(r["full_oku"])) for r in HIGH)
assert all(r["commodity"] == "trade_finance" and set(r["events"]) == {"CROSS_NEG", "FIN_NEG"} for r in HIGH)
net_contract = defaultdict(Decimal)
for r in dataset["semantic_event_financial_effects"]:
    net_contract[r["contract_id"]] += Decimal(r["delta_ebitda_full_jpy"])
OFFSET_ID = "SUB_MTL_JP_01_C07"
assert OFFSET_ID in {r["contract_id"] for r in q_act}
assert (oku(per_contract[OFFSET_ID]), oku(net_contract[OFFSET_ID])) == (Decimal("-0.37"), Decimal("-0.09"))
NET_OFFSET = num(oku(net_contract[OFFSET_ID]))
s = new_slide(
    k(T_Q4, "質問④ 打ち手"), T_Q4,
    "原因と根拠が分かっても、すべての契約に同時には対応できません。\n"
    "Data Agentが、影響額と重なりを手がかりに、優先度の案を示しました。",
    f"""【入力】「いま手を打つべき契約ってどれ？」と日本語で入力します。
【回答の要点】Data Agentは、契約ごとに影響額と影響したイベントをまとめ、高優先4契約、中優先3契約を提案しました。高優先の4契約は、すべて貿易金融の契約で、横断混乱と取引先対応コスト増の両方の影響を受け、{num(hi_lo)}〜{num(hi_hi)}億円です。
【指す】右の表が、提案された契約の一覧です。金額は、マイナスのイベントだけの合計（全額連結）です。左下の2枚は、データから言えることと、仮説としての打ち手の例を分けています。
【補足】この回答では、Data Agentが、イベント、影響額、契約、会社の関係から表のつなぎ方を決めて集計しました（2026-10-27の確認、1回）。{OFFSET_ID}は、マイナスのイベントだけで見ると{num(oku(per_contract[OFFSET_ID]))}億円ですが、プラスのイベント（再生合金契約）と合わせると{NET_OFFSET}億円です。マイナスだけを見るか、差し引きで見るかで、対応の順番は変わります。
【注意】どの契約を載せるかと、優先度の線引きは、Data Agentの判断です。指示文の方針（影響額と複数イベントの影響の有無で、高・中・低に分ける）に沿っていますが、規則どおりの機械的な並びではありません。確認した実行の中でも、線引きは変わりました（同じ2契約が、ある回は低優先、別の回は中優先）。表の金額と、重なったイベントは、元データと一致しています。契約データに取引先名の項目がないため、契約IDで示しています。打ち手は仮説で、実際の対応は、担当部門が契約条件と取引先の状況を確認して決めます。""",
    ["デモ環境での確認（2026年10月26日〜27日、公開済みのData Agent。金額を元データと照合）"],
    takeaway="載せる契約と優先度は、Data Agentの判断で、金額順ではなく、実行ごとに変わります。実際に手を打つかは、契約条件を確認して決めます。",
    trace=["reports/da_traversal_fix_2026-10-27.json:demo_questions.Q_ACT", "reports/da_casual_after_2026-10-26.json:known_limits",
           "data/demo_dataset.json:semantic_event_financial_effects"])
ask_card(s, .6, 2.35, 4.4, .95, "いま手を打つべき契約ってどれ？", 17)
box(s, .6, 3.45, 4.4, 1.75, WHITE, LINE)
text(s, "データから言えること", .8, 3.55, 4.0, .24, 12, TEAL, True, spacing=1.0)
text(s, ["・金額は、マイナスのイベントだけの合計（全額連結）です。",
         f"・高優先の4契約は、すべて貿易金融で、2つのイベントが重なり、{num(hi_lo)}〜{num(hi_hi)}億円です。",
         f"・{OFFSET_ID}は、プラスのイベントと相殺すると{NET_OFFSET}億円です。"],
     .8, 3.85, 4.0, 1.3, 11, INK, spacing=1.3, after=2)
box(s, .6, 5.3, 4.4, .95, WHITE, PURPLE, lw=1.25)
text(s, "仮説としての打ち手の例", .8, 5.37, 4.0, .24, 12, PURPLE, True, spacing=1.0)
text(s, "契約別の信用枠、担保・ヘッジ条件、例外承認ルールを優先して点検し、2つのイベントが重なった場合の早期エスカレーション条件を設ける。",
     .8, 5.65, 4.0, .58, 10.5, INK, spacing=1.25)
box(s, 5.2, 2.35, 7.53, 3.9, WHITE, LINE)
QC = [(.2, .65, "優先度", None), (.8, 1.8, "契約ID", None), (2.6, 2.15, "会社", None),
      (4.8, 1.45, "影響したイベント", None), (6.2, 1.2, "影響額（億円）", RIGHT)]
for cx, cwid, label, al in QC:
    text(s, label, 5.2 + cx, 2.47, cwid, .24, 11.5, TEAL, True, al, spacing=1.0)
EV_SHORT = {"CROSS_NEG": "横断混乱", "FIN_NEG": "取引先対応コスト増", "MTL_NEG": "製錬停止"}
for i, r in enumerate(q_act):
    yy = 2.82 + i * .47
    if i % 2:
        box(s, 5.28, yy - .02, 7.37, .45, PALE, None, radius=.05)
    chip(s, r["priority"], 5.2 + .2, yy + .08, .5, WHITE, CORAL if r["priority"] == "高" else PURPLE, 11.5, .28)
    text(s, r["contract_id"], 5.2 + .8, yy, 1.8, .42, 11, INK, anchor=MIDDLE, spacing=1.0)
    text(s, r["subsidiary"], 5.2 + 2.6, yy, 2.15, .42, 10.5, INK, anchor=MIDDLE, spacing=1.15)
    text(s, "\n".join(EV_SHORT[e] for e in sorted(r["events"], key=lambda e: list(EV_SHORT).index(e))),
         5.2 + 4.8, yy, 1.45, .42, 10.5, INK, anchor=MIDDLE, spacing=1.1)
    text(s, num(r["full_oku"]), 5.2 + 6.2, yy, 1.2, .42, 12, CORAL, True, RIGHT, MIDDLE, spacing=1.0)

# 16 -----------------------------------------------------------------------------------------------
expect(T_RIPPLE)
reach = {}
for _eid in ("FOD_NEG", "CROSS_NEG"):
    _rows = [r for r in dataset["semantic_event_financial_effects"] if r["event_id"] == _eid]
    reach[_eid] = (len({r["entity_id"] for r in _rows}), len({r["contract_id"] for r in _rows}), len(_rows))
assert reach["FOD_NEG"] == (2, 6, 84) and reach["CROSS_NEG"] == (8, 26, 336)
s = new_slide(
    k(T_RIPPLE, "全社に及ぶイベント"), T_RIPPLE,
    "食品損失の影響は2社でしたが、港湾や流動性の混乱のようなイベントは、8社すべてに同時に当たります。\n"
    "影響額の明細は84件から336件に増えましたが、会社別、事業別の集計は、既存の関係で行えました。",
    f"""【話す】食品損失の影響は2社に限られました。このデモには、全社に同時に当たるイベントも2件入れてあります。港湾と流動性の混乱を想定した「横断混乱」は、8社すべてに当たり、EBITDAを{fmt(EV['CROSS_NEG'])}億円押し下げます。食品損失と同じ経路で、根拠から全社KPIまでたどれます。
【指す】左の表で、影響が2社から8社に、影響額の明細が84件から336件に増えています。右の図は、8社の影響額で、各社の年間EBITDAに対する比率は、約{MINUS}{PCT_LO.quantize(Decimal('0.1'))}〜{MINUS}{PCT_HI.quantize(Decimal('0.1'))}%でそろっています。
【数字】横断混乱は、全額連結で{fmt(EV['CROSS_NEG'])}億円、持分管理で{fmt(EV_MGMT['CROSS_NEG'])}億円、年間EBITDA（{oku(ACTUAL)}億円）の約{MINUS}{CROSS_ANNUAL}%です。事業別では、金属{fmt(sector_cross['metals'])}、エネルギー{fmt(sector_cross['energy'])}、食品{fmt(sector_cross['foods'])}、金融{fmt(sector_cross['finance'])}（億円）です。
【確認】会社別と事業別の金額は、公開済みのData Agentの回答が、元データの集計と小数第2位まで一致しました（2026-10-27）。
【未対応】ある会社の問題が、取引を通じて別の会社に伝わる「連鎖」は、会社と会社を結ぶ関係をOntologyにまだ持っていないため、今のデモでは扱えません。内部取引の表はありますが、関係として定義していません。
【注意】各社の比率がそろっているのは、データの設計によるもので、現実の波及の姿を示すものではありません。""",
    ["デモ環境での確認（2026-10-27、公開済みのData Agent。会社別、事業別の金額を元データと照合）"],
    takeaway="会社から会社へ連鎖する波及（取引を通じた影響）は、関係の追加が必要で、このデモでは未対応です。",
    trace=["reports/da_group_wide_2026-10-27.json", "reports/da_traversal_fix_2026-10-27.json",
           "reports/graph_all_event_paths.json"])
box(s, .6, 2.35, 5.55, 3.9, WHITE, LINE)
RC = [(.2, 1.85, "", None), (2.05, 1.65, "食品損失", RIGHT), (3.7, 1.7, "横断混乱", RIGHT)]
for cx, cwid, label, al in RC:
    text(s, label, .6 + cx, 2.48, cwid, .26, 12, TEAL, True, al, spacing=1.0)
ripple_rows = [
    ("影響を受けた会社", f"{reach['FOD_NEG'][0]}社", f"{reach['CROSS_NEG'][0]}社（4事業すべて）", False),
    ("契約", f"{reach['FOD_NEG'][1]}件", f"{reach['CROSS_NEG'][1]}件", False),
    ("影響額の明細", f"{reach['FOD_NEG'][2]}件", f"{reach['CROSS_NEG'][2]}件", False),
    ("全額連結EBITDA", f"{fmt(EV['FOD_NEG'])}億円", f"{fmt(EV['CROSS_NEG'])}億円", True),
    ("持分管理", f"{fmt(EV_MGMT['FOD_NEG'])}億円", f"{fmt(EV_MGMT['CROSS_NEG'])}億円", True),
    ("年間EBITDA比", f"{MINUS}{FOOD_ANNUAL}%", f"{MINUS}{CROSS_ANNUAL}%", True),
    ("全社KPIまでの経路", f"{graph_paths['FOD_NEG']}件すべて", f"{graph_paths['CROSS_NEG']}件すべて", False),
]
for i, (label, a, b, red) in enumerate(ripple_rows):
    yy = 2.85 + i * .455
    if i % 2:
        box(s, .68, yy - .03, 5.39, .43, PALE, None, radius=.05)
    text(s, label, .6 + .2, yy, 1.85, .38, 12, INK, True, anchor=MIDDLE, spacing=1.0)
    text(s, a, .6 + 2.05, yy, 1.65, .38, 12.5, CORAL if red else INK, red, RIGHT, MIDDLE, spacing=1.0)
    text(s, b, .6 + 3.7, yy, 1.7, .38, 12.5, CORAL if red else INK, True, RIGHT, MIDDLE, spacing=1.0)
text(s, "※経路の確認は、2026年10月27日のGraphでの確認", .8, 5.98, 5.2, .22, 11, MUTED, spacing=1.0)
box(s, 6.4, 2.35, 6.33, 3.9, WHITE, LINE)
text(s, "横断混乱：会社別の全額連結EBITDA影響（億円）", 6.65, 2.47, 5.8, .28, 13, TEAL, True, spacing=1.0)
text(s, f"各社の年間EBITDA比は約{MINUS}{PCT_LO.quantize(Decimal('0.1'))}〜{MINUS}{PCT_HI.quantize(Decimal('0.1'))}%",
     6.65, 2.77, 5.8, .22, 11, MUTED, spacing=1.0)
ZY, BSCALE, SLOT = 3.35, 1.25, 5.75 / 8
box(s, 6.6, ZY, 5.95, .012, STEEL, None, rounded=False)
for i, sub in enumerate(subsidiaries):
    v = cross_co[sub["entity_id"]]
    h = abs(float(oku(v))) * BSCALE
    cxm = 6.65 + SLOT * i + SLOT / 2
    box(s, cxm - .21, ZY + .012, .42, h, CORAL, None, radius=.03)
    text(s, fmt(v), cxm - .36, ZY + .012 + h + .03, .72, .22, 11, CORAL, True, CENTER, spacing=1.0)
    text(s, "日本" if sub["country_code"] == "JP" else "米国", cxm - .36, 5.02, .72, .22, 10.5, INK, False, CENTER,
         spacing=1.0)
for g, sector in enumerate(SECTOR_KEYS):
    gx0 = 6.65 + SLOT * 2 * g
    box(s, gx0 + .08, 5.3, SLOT * 2 - .16, .012, LINE, None, rounded=False)
    text(s, SECTOR_JP[sector], gx0, 5.36, SLOT * 2, .24, 12, NAVY, True, CENTER, spacing=1.0)
    text(s, fmt(sector_cross[sector]), gx0, 5.62, SLOT * 2, .24, 12, CORAL, True, CENTER, spacing=1.0)
text(s, "事業ごとの合計（億円）。丸めのため、会社別の和と一致しない場合があります", 6.65, 5.94, 5.95, .24, 11, MUTED, spacing=1.0)


# =====================================================================================================
# Chapter 3
# =====================================================================================================
divider(CHAPTERS[2])

# 18 -----------------------------------------------------------------------------------------------
expect(T_DIFF)
s = new_slide(
    k(T_DIFF, "従来の手段との違い"), T_DIFF,
    "集計の数字そのものは、SQLやBIなどの従来の手段でも出せます。\n"
    "Ontologyの違いは、定義とつながりを1か所にまとめ、他の利用者やツールが参照できる点です。",
    """【話す】このデモの集計だけなら、SQLやBIでも同じ数字を出せます。Ontologyが違うのは、業務の概念、関係、ルールを1か所で定義して、人にもエージェントにも同じ定義を渡せる点です。
【指す】3つの観点を上から順に。左が従来の手段でクエリやモデルごとに作る場合、右がOntologyで定義した場合です。右の小さい文字が、このデモでの確認内容です。
【補足】Microsoft Learnは、Ontologyの役割を、利用者ごとに表、列、メジャー、結合を解釈する代わりに、再利用できる業務の概念とデータへの結び付けを与えることと説明しています。Power BIのセマンティックモデルも、定義を共有する手段です。Ontologyは、そのモデルから生成して、業務の概念と関係を重ねることもできます（Preview）。
【留意点】このデモでは、全額連結などの言葉の定義の一部は、Data Agentの指示文に書いてあり、Ontologyのルールへの移行は未実施です。デモは4つの質問と1つのエージェントで確認しており、質問や利用者が増えた場合の効果の大きさは測っていません。PoCで、質問と利用者を増やして評価します。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、concepts-agent-integration（2026-09-15更新）、how-to-bind-data（2026-10-20更新）",
     "デモ環境での確認"],
    takeaway="このデモは4問のため、効果の大きさは測っていません。PoCで、質問と利用者を増やして評価します。")
dcols = [(.2, 1.65, "観点"), (1.95, 4.5, "従来の手段（クエリやモデルごとに作る場合）"), (6.6, 5.35, "Ontologyで定義した場合")]
box(s, .6, 2.35, 12.13, 3.9, WHITE, LINE)
for cx, cwid, label in dcols:
    text(s, label, .6 + cx, 2.47, cwid, .26, 12, TEAL, True, spacing=1.0)
diff_rows = [
    ("言葉の意味", "意味は、列名、計算式、メジャーなどに含まれ、利用者が読み解いて使います。",
     "概念、関係、ルールを業務の言葉で定義し、人もエージェントも同じ定義を参照できます。",
     "デモ：全額連結と持分管理の区別は、Data Agentの指示文に書いています。ルールへの移行は未実施です。"),
    ("つながり", "結合条件を、クエリやモデルごとに書きます。書き方によっては、金額が二重に数えられる場合があります（一般的なリスク）。",
     "関係に名前を付けて1か所に定義し、経路をたどる質問で再利用できます。",
     "デモ：39種類の関係を定義。質問③④で、Data Agentが関係から表のつなぎ方を決めました。"),
    ("データ元の種類", "データ元の種類が違うと、共通の言葉にそろえる作業は、データ元ごと、ツールごとになりがちです。",
     "種類の違うデータ元（Lakehouse、Eventhouseなど）の表を、同じ概念に結び付けられます。",
     "Learnの記載。デモ：Lakehouseのみ。8社の原本は会社ごとに残し、同じ定義で扱いました（全社分析用の表はコピー）。"),
]
for i, (name, old, new_, demo) in enumerate(diff_rows):
    yy = 2.85 + i * 1.13
    if i % 2 == 0:
        box(s, .68, yy - .05, 11.97, 1.08, PALE, None, radius=.05)
    text(s, name, .6 + .2, yy, 1.6, 1.0, 14, NAVY, True, anchor=MIDDLE, spacing=1.0)
    text(s, old, .6 + 1.95, yy, 4.4, 1.0, 12.5, INK, anchor=MIDDLE, spacing=1.35)
    text(s, [[(new_, {"size": 12.5, "color": INK})], [(demo, {"size": 11, "color": MUTED})]],
         .6 + 6.6, yy, 5.3, 1.0, 12.5, anchor=MIDDLE, spacing=1.3, after=3)

# 19 -----------------------------------------------------------------------------------------------
expect(T_DATA)
s = new_slide(
    k(T_DATA, "既存データの活用"), T_DATA,
    "ゼロコピーで参照するのは、事業固有の8表だけです。\n"
    "全社分析用の12表とGraphは、コピーして作っています。",
    f"""【話す】データを一か所に集め直す必要はありません。各社の原本は、会社ごとのLakehouseに残し、書き換えません。Ontologyは、データそのものを持たず、概念と関係の定義と、データへの結び付けを持ちます。
【指す】下の層から順に。原本（灰色）から、事業固有の8表は、コピーせずに参照します（青緑の点線）。全社分析用の12表は、8社分を1つにまとめるため、コピーして作ります（紫）。Graphも、経路をたどる問いのために、Ontologyの定義から作るコピーです（紫）。
【ゼロコピーの範囲】ゼロコピーは、事業固有の8表だけです。全社分析用の表とGraphは、コピーして作っています。
【結び付けられるデータ】Previewの間は、セマンティックモデル、Lakehouse、Eventhouse、Warehouse、SQLデータベース、ミラーリングデータベース、OneLakeのショートカット、ビュー、マテリアライズドビューです。
【注意】Power BIのセマンティックモデルからOntologyを生成できます（Preview）。ただし、現時点では、Graphの対象は、LakehouseまたはミラーリングデータベースのDeltaテーブルに限られます。セマンティックモデルに結んだOntologyは、Data Agentが動作しない既知の問題があり、グラフ化もできません（Microsoft Learn、2026年9月時点）。Data AgentやGraphを使う場合は、LakehouseなどのDeltaテーブルに結びます。デモは、Lakehouseの表に結んでいます。
【更新】コピーして作った表とGraphは、原本の変更が自動で反映されるとは限りません。更新のタイミングは、設計で決めます。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、how-to-bind-data（2026-10-20更新）",
     "Microsoft Learn：how-to-use-ontology-graph（2026-09-18更新）、how-to-create-data-agent（2026-09-13更新）",
     "デモ環境の構成（9つのLakehouse）"],
    takeaway="コピーして作る表とGraphは、原本の変更が自動で反映されるとは限りません。更新のタイミングは、設計で決めます。",
    trace=["docs/architecture.md", "config/deployment_manifest.json", "config/sector_shortcuts.json"])
LX, LW = 1.95, 6.55
layer4 = [("使う側", 2.35, .8), ("意味の層", 3.55, .95), ("データ", 4.8, .8), ("原本", 5.85, .4)]
for label, y, h in layer4:
    text(s, label, .6, y, 1.2, h, 14, TEAL, True, anchor=MIDDLE, spacing=1.0)
for i, (a_, b_) in enumerate([("Data Agent", "日本語の質問"), ("他のエージェント", "対応は製品ごと"), ("Notebook", "Graphの経路を表示")]):
    bx = LX + i * (2.05 + .2)
    box(s, bx, 2.35, 2.05, .8, WHITE, LINE)
    text(s, [[(a_, {"bold": True, "size": 12.5, "color": NAVY})], [(b_, {"size": 11, "color": MUTED})]],
         bx + .12, 2.35, 1.85, .8, 12, anchor=MIDDLE, spacing=1.25)
box(s, LX, 3.55, 3.75, .95, WHITE, NAVY, lw=2.0)
text(s, [[("Ontology", {"bold": True, "size": 15, "color": NAVY})],
         [("概念と関係の定義と、データへの結び付け", {"size": 11, "color": INK})],
         [("データそのものは持たない", {"size": 11, "color": MUTED})]],
     LX + .15, 3.55, 3.5, .95, 12, anchor=MIDDLE, spacing=1.25)
box(s, LX + 4.15, 3.55, 2.4, .95, MAT_FILL, PURPLE, lw=1.75)
text(s, [[("Graph（任意）", {"bold": True, "size": 13.5, "color": PURPLE})],
         [("定義から作成するコピー", {"size": 11, "color": INK})]],
     LX + 4.3, 3.55, 2.15, .95, 12, anchor=MIDDLE, spacing=1.25)
arrow(s, LX + 3.77, 4.03, LX + 4.13, 4.03, PURPLE, width=2.0)
box(s, LX, 4.8, 3.2, .8, MAT_FILL, PURPLE, lw=1.75)
text(s, [[("全社分析用の表（12表）", {"bold": True, "size": 12.5, "color": PURPLE})],
         [("8社分を1つにまとめ、コピーして作る", {"size": 11, "color": INK})]],
     LX + .12, 4.8, 3.0, .8, 12, anchor=MIDDLE, spacing=1.25)
box(s, LX + 3.35, 4.8, 3.2, .8, ZERO_FILL, TEAL, dash=True, lw=1.75)
text(s, [[("事業固有の表（8表）", {"bold": True, "size": 12.5, "color": TEAL})],
         [("原本を参照するだけ（ゼロコピー）", {"size": 11, "color": INK})]],
     LX + 3.47, 4.8, 3.0, .8, 12, anchor=MIDDLE, spacing=1.25)
box(s, LX, 5.85, LW, .4, GRAY, None)
text(s, "子会社の原本：8つのLakehouse（会社ごとに分離。書き換えない）", LX + .15, 5.85, LW - .3, .4, 11.5, INK, True,
     anchor=MIDDLE, spacing=1.0)
arrow(s, LX + 1.03, 3.53, LX + 1.03, 3.18, STEEL, width=2.0)
arrow(s, LX + 3.27, 3.53, LX + 3.27, 3.18, STEEL, width=2.0)
arrow(s, LX + 5.53, 3.53, LX + 5.53, 3.18, STEEL, width=2.0)
arrow(s, LX + 1.6, 4.78, LX + 1.6, 4.53, PURPLE, width=2.0)
arrow(s, LX + 4.95, 4.78, LX + 3.5, 4.53, TEAL, True, 2.0)
arrow(s, LX + 1.6, 5.83, LX + 1.6, 5.63, PURPLE, width=2.0)
arrow(s, LX + 4.95, 5.83, LX + 4.95, 5.63, TEAL, True, 2.0)
box(s, 8.85, 2.35, 3.88, 1.7, WHITE, LINE)
text(s, "結び付けられるデータ（Preview）", 9.05, 2.45, 3.5, .26, 12.5, TEAL, True, spacing=1.0)
text(s, "Lakehouse、Warehouse、Eventhouse\nSQLデータベース、ミラーリングDB\nPower BIセマンティックモデル\nOneLakeのショートカット、ビュー",
     9.05, 2.78, 3.55, 1.2, 11.5, INK, spacing=1.4)
box(s, 8.85, 4.15, 3.88, 1.12, WHITE, LINE)
for i, (fill, line, dashed, label) in enumerate([(GRAY, None, False, "原本（そのまま残す）"),
                                                 (ZERO_FILL, TEAL, True, "ゼロコピー（参照のみ）"),
                                                 (MAT_FILL, PURPLE, False, "コピーして作る"),
                                                 (WHITE, NAVY, False, "定義と利用側（データなし）")]):
    ly = 4.22 + i * .255
    box(s, 9.05, ly + .02, .34, .2, fill, line, radius=.04, dash=dashed, lw=1.5)
    text(s, label, 9.52, ly, 3.1, .24, 11, INK, spacing=1.0, anchor=MIDDLE)
box(s, 8.85, 5.37, 3.88, .88, CORAL_PALE, CORAL, lw=1.0)
text(s, "Graphの対象は、LakehouseとミラーリングDBのDeltaテーブルです。セマンティックモデルに結んだOntologyは、Graphを作れず、Data Agentも動作しない既知の問題があります（2026年9月時点）。",
     9.0, 5.37, 3.6, .88, 10.5, INK, anchor=MIDDLE, spacing=1.2)

# 20 -----------------------------------------------------------------------------------------------
expect(T_GOV)
s = new_slide(
    k(T_GOV, "権限と運用"), T_GOV,
    "経営データを扱うには、誰が何を見られるかを保つことが前提です。\n"
    "Ontologyは、Fabricの既存の権限の仕組みの上で動きます。",
    """【話す】Ontologyは、Fabricの権限の仕組みの上で動きます。Ontologyのアイテムへのアクセスは、ワークスペースとアイテムの権限で制御します。Microsoft Learnの記載では、結び付けたデータについて、作成時も問い合わせ時も、データ側の権限が尊重されます。
【3つのポイント】①アクセスの制御：Fabricのワークスペースとアイテムの権限。②データ側の権限：OneLake security、ソース側で強制される行レベル、オブジェクトレベル、列レベルのセキュリティ（Microsoft Learnの記載）。③変更の管理：名前付きの版の保存と復元、APIとCI/CD。Ontology agentによる変更は、提案を確認してから反映します。
【補足】バージョン履歴は、現在は手動で版を作ります。各版には、日時、作成者、名前、説明が付き、復元すると、現在の定義が保存した版に置き換わります。
【注意】このデモでは、権限の動作は検証していません。コピーして作った表（全社分析用の12表）とGraphに、データ側の権限が同じように及ぶかは、確認していません。権限の挙動は、結び付けるデータの種類で異なる場合があります。PoCで、対象のデータごとに確認します。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）"],
    takeaway="権限と版管理は、Microsoft Learnの記載で、このデモでは検証していません。PoCで、対象のデータごとに確認します。")
gov = [
    ("アクセスの制御", TEAL, "Fabricのワークスペースとアイテムの権限で、Ontologyにアクセスできる人を制御します。"),
    ("データ側の権限", PURPLE,
     "Microsoft Learnの記載では、結び付けたデータ側の権限（OneLake securityなど）が、作成時と問い合わせ時に尊重されます。このデモでは未検証です。コピーして作った表とGraphの権限は、別に確認が必要です。"),
    ("変更の管理", CORAL,
     "Microsoft Learnの記載では、名前付きの版を保存して、前の状態に戻せます。Ontology agentによる変更は、提案を確認してから反映します。APIとCI/CDにも対応します。"),
]
for i, (head, color, body) in enumerate(gov):
    x = .6 + i * 4.09
    box(s, x, 2.4, 3.95, 3.75, WHITE, LINE)
    box(s, x, 2.4, 3.95, .1, color, None, radius=.04)
    numdot(s, str(i + 1), x + .45, 2.95, .27, color, size=15)
    text(s, head, x + .25, 3.4, 3.45, .4, 19, NAVY, True, spacing=1.2)
    text(s, body, x + .25, 3.95, 3.45, 2.1, 13, INK, spacing=1.4)

# 21 -----------------------------------------------------------------------------------------------
expect(T_SCALE)
n_core = len(entity_names) - 8
assert n_core == 9
CUR6 = ["Activity", "Company", "Contract", "FinancialEffect", "FinancialMetric", "GroupKPI"]
s = new_slide(
    k(T_SCALE, "拡張の仕組み"), T_SCALE,
    "事業や部門が増えると、同じ名前の概念や共通の項目が増え、定義が重複しやすくなります。\n"
    "それらを整理する4つの機能があります。いずれもPreviewで、このデモでは使っていません。",
    """【話す】対象の事業や部門が増えると、同じ名前で意味の違う概念や、複数の概念に共通する項目が増えます。新しいOntologyの体験には、これを整理する機能が加わりました。このデモではまだ使っていません。
【指す】左から、名前空間、継承、共有プロパティ、ビジネスルールです。各カードの「このデモに当てはめた案」が、使う場合の例で、Fabricには反映していません。下段の「留意」が、Microsoft Learnに記載された制限です。
【案の内訳】名前空間：共通の9概念をcore、事業固有の8概念を4つの事業に分ける案。継承：事業固有の8概念が共通で持つ5つの項目（拡張ID、活動ID、会社ID、契約ID、観測日）を親に集める案。共有プロパティ：通貨コードを使う6つの概念で定義を1回にする案。ビジネスルール：全額連結と持分管理の区別などを、Data Agentの指示文からルールへ移す案です。
【留意】ルールは、エージェントが読む前提の文章で、Ontologyが処理を実行するものではありません。新しい体験は、Fabric Activatorとの直接の連携を、現時点では提供していません。名前空間を使ってグラフへ投影すると、ノードや辺のラベルに名前空間が接頭辞として付くため、ラベルを指定した既存のクエリは見直しが必要になる場合があります。継承は、親の概念を指定して、派生した概念の実例をまとめて取得する使い方が、MCPサーバーの既知の問題で、現時点では使えません（Microsoft Learn、2026年9月時点）。
【提案】最初のPoCでは、これらを使わずに始める進め方をご提案します。導入後に、質問を再実行して確認します。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、how-to-use-namespaces、how-to-use-inheritance、how-to-reuse-properties、how-to-use-rules",
     "デモのOntology定義に当てはめた提案（Fabricには反映していません）"],
    takeaway="最初のPoCでは、これらを使わずに始める進め方をご提案します。必要になった時点で追加します。",
    trace=["ontology_tmdl", "prompts/da_instructions_ja.txt"])
feat = [
    ("名前空間", TEAL, "同じ名前の概念を、領域ごとに区別して持てます。",
     f"共通の{n_core}概念をcore、事業固有の8概念を4つの事業に分ける。",
     "グラフ上のラベルに、名前空間が接頭辞として付く。"),
    ("継承", PURPLE, "共通の親を定義し、特化した概念を派生させます。",
     "事業固有の8概念に共通する\n5つの項目を、親に集める。",
     "親から派生した概念の実例の一括取得は、MCPで未提供（既知の問題）。"),
    ("共有プロパティ", CORAL, "1つの項目の定義を、複数の概念で参照します。",
     f"通貨コードを使う{len(CUR6)}つの概念で、定義を1回にする。",
     "共有プロパティの名前は、Ontologyの中で重複できない。"),
    ("ビジネスルール", NAVY, "業務の決まりを文章で定義し、概念や関係に結び付けます。",
     "全額連結と持分管理の区別を、指示文からルールへ移す。",
     "ルールは、エージェントが読む説明文で、実行はされない。"),
]
fw = (12.13 - 3 * .14) / 4
for i, (name, color, what, case, caution) in enumerate(feat):
    x = .6 + i * (fw + .14)
    box(s, x, 2.35, fw, 3.9, WHITE, LINE)
    box(s, x, 2.35, fw, .1, color, None, radius=.04)
    text(s, name, x + .2, 2.6, fw - .4, .36, 18, color, True, spacing=1.0)
    text(s, what, x + .2, 3.05, fw - .4, .8, 12.5, INK, spacing=1.4)
    box(s, x + .2, 3.9, fw - .4, .01, LINE, None, rounded=False)
    text(s, "このデモに当てはめた案", x + .2, 3.98, fw - .4, .22, 10.5, MUTED, True, spacing=1.0)
    text(s, case, x + .2, 4.24, fw - .4, .8, 12, NAVY, True, spacing=1.3)
    text(s, "留意", x + .2, 5.0, fw - .4, .2, 10.5, CORAL, True, spacing=1.0)
    text(s, caution, x + .2, 5.22, fw - .4, .62, 11, INK, spacing=1.25)
    chip(s, "Preview・デモでは未実装", x + .2, 5.88, fw - .4, color, PALE, 10.5, .28)


# =====================================================================================================
# Chapter 4: a business app (Rayfin) that reads the ontology graph
# =====================================================================================================
divider(CHAPTERS[3])

APP_LEARN = ["Microsoft Learn：fabric/apps/overview（2026-09-29更新）、fabric/apps/functions（2026-09-29更新）",
             "Microsoft Learn：fabric/graph/gql-query-api（2026-09-29更新）、fabric/iq/ontology/how-to-use-ontology-graph（2026-09-29更新）"]
APP_TRACE = ["reports/whatif_app_live_verification_2026-10-28.json"]
APP_ROWS = app["probe"]["counts"]["ebitda_rows"]
assert APP_ROWS == 2920
assert "Sign in required" in app["ui_observations"]["signed_out_access"]
APP_DONE_BY = "デモ環境での確認（Fabric Apps（Rayfin）のアプリ、2026年10月28日）"


def app_node(slide, x, y, w, h, jp, en, count, color):
    """A node of the path diagram. Same shape as the ontology diagram on p.7, plus the count the graph returned."""
    box(slide, x, y, w, h, WHITE, color, lw=1.75, radius=.07)
    text(slide, [[(jp, {"bold": True, "size": 13.5, "color": INK})], [(en, {"size": 10, "color": MUTED})],
                 [(f"{count:,}件", {"bold": True, "size": 17, "color": color})]],
         x, y, w, h, 12, align=CENTER, anchor=MIDDLE, spacing=1.15)


# 23 -----------------------------------------------------------------------------------------------
expect(T_APP_ROLES)
s = new_slide(
    k(T_APP_ROLES, "アプリでの役割分担"), T_APP_ROLES,
    f"Data Agentの円高の試算は、実行ごとの答えが安定しませんでした（p.{PAGE_OF[T_CAVEAT]}）。\n"
    "条件を動かすアプリでは、金額を言語モデルに任せず、決まった手順で計算します。",
    f"""【話す】ここまでは、Data Agentに日本語で質問して、答えと根拠を確認しました。この章は、別の使い方として、画面を持つ業務アプリからOntologyを使う例です。条件を画面で動かしながら、EBITDAがどう変わるかを見ます。
Data Agentの円高の試算は、実行ごとの答えが安定しませんでした（p.{PAGE_OF[T_CAVEAT]}）。画面で条件を動かす用途では、同じ条件には同じ答えを返してほしいので、金額の計算は言語モデルに任せず、決まった手順で行います。そのうえで、Ontologyには、つながりを担当してもらいます。
【指す】上の帯が、画面と、アプリの裏側（Functions）です。Functionsは、下の3つを使って答えを組み立てます。左がOntologyのグラフで、イベントが、どの影響額、契約、全社KPIにつながるかを返します。中央がLakehouseで、日次のEBITDA、影響額の金額、為替、持分を返します。右が計算で、条件を金額に当てはめ、差額と内訳を返します。計算は、Functionsの中で動きます。各カードの下段は、そのカードが返さないもの、または、守ることです。
【補足】Microsoft Learnは、OntologyとGraphの関係を「ontologyが意味を定義し、graphが関係を実行する」と説明しています。Graphは任意の層です。FunctionsがGraphとLakehouseを読むときは、アプリのID（現在は、アプリの所有者のID）を使います（p.{PAGE_OF[T_APP_SCOPE]}）。Fabric Appsのコネクタの対象は、Lakehouse、Warehouse、SQLデータベース、セマンティックモデルで、Ontologyは含まれません。このデモでは、FunctionsからGraphのクエリ用API（GQL Query API）を直接呼んでいます。
【注意】Ontologyが金額を計算したわけではありません。Ontologyが担うのは、つながりの定義と、Graphでの経路の取得です。GQL Query APIはbeta、Fabric AppsとOntologyはPreviewです。""",
    APP_LEARN + [APP_DONE_BY],
    takeaway="OntologyにつなぐFabric Appsの標準コネクタはなく、FunctionsからGraphのクエリ用API（beta）を直接呼んでいます。",
    trace=APP_TRACE + ["reports/da_casual_after_2026-10-26.json:known_limits"],
    foot=FOOT_APP)
CW, GAPX = 3.85, (12.13 - 3 * 3.85) / 2
CXS = [.6 + i * (CW + GAPX) + CW / 2 for i in range(3)]
# 上の帯: 画面 -> Functions
box(s, .6, 2.35, 12.13, .62, WHITE, LINE)
chip(s, "画面", .8, 2.51, .8, TEAL, PALE, 12, .3)
text(s, "条件を動かす（為替、イベントの影響）", 1.75, 2.35, 3.6, .62, 13, INK, anchor=MIDDLE, spacing=1.2)
arrow(s, 5.35, 2.66, CXS[1] - .72, 2.66, TEAL, width=2.0)
chip(s, "Functions", CXS[1] - .6, 2.51, 1.2, NAVY, PALE, 12, .3)
text(s, "アプリの裏側の処理。下の3つを使い、答えを組み立てる", CXS[1] + .78, 2.35, 5.15, .62, 13, INK, anchor=MIDDLE,
     spacing=1.2)
# Functions から3つへ分かれる
BUS_Y = 3.15
arrow(s, CXS[1], 2.81, CXS[1], BUS_Y, STEEL, width=1.75, head=False)
arrow(s, CXS[0], BUS_Y, CXS[2], BUS_Y, STEEL, width=1.75, head=False)
for cx in CXS:
    arrow(s, cx, BUS_Y, cx, 3.34, STEEL, width=1.75)
roles = [
    ("Ontologyのグラフ", TEAL, "つながり",
     "イベントが、どの影響額、契約、全社KPIにつながるか（経路と件数）", "返さないもの", "金額の計算", CORAL_PALE, CORAL),
    ("Lakehouse", NAVY, "金額",
     "日次のEBITDA、影響額の金額、為替、持分", "返さないもの", "条件の反映", CORAL_PALE, CORAL),
    ("計算（Functions内）", CORAL, "条件の反映",
     "為替とイベントの条件を金額に当てはめ、差額と内訳を返す", "守ること", "同じ条件には同じ答え", PALE, NAVY),
]
CY, CH = 3.38, 2.84
for i, (name, color, job, gives, flag, flag_val, flag_fill, flag_color) in enumerate(roles):
    x = .6 + i * (CW + GAPX)
    box(s, x, CY, CW, CH, WHITE, LINE)
    box(s, x, CY, CW, .1, color, None, radius=.04)
    text(s, name, x + .25, CY + .28, CW - .5, .36, 18, color, True, spacing=1.0)
    text(s, [[("担当", {"size": 10.5, "color": MUTED, "bold": True})],
             [(job, {"size": 16, "color": NAVY, "bold": True})]], x + .25, CY + .78, CW - .5, .62, 14, spacing=1.2)
    text(s, [[("返すもの", {"size": 10.5, "color": MUTED, "bold": True})],
             [(gives, {"size": 12.5, "color": INK})]], x + .25, CY + 1.5, CW - .5, .8, 12.5, spacing=1.3)
    box(s, x + .2, CY + 2.38, CW - .4, .34, flag_fill, None, radius=.07)
    text(s, [[(flag + "　", {"size": 10.5, "color": MUTED, "bold": True}),
              (flag_val, {"size": 12, "color": flag_color, "bold": True})]],
         x + .32, CY + 2.38, CW - .64, .34, 12, anchor=MIDDLE, spacing=1.0)

# 24 -----------------------------------------------------------------------------------------------
expect(T_APP_SCREEN)
assert (mil(APP_STEP_EVENTS), mil(APP_STEP_FX), mil(APP_FULL), mil(APP_SUM_OF_SINGLES)) == (
    "+57.2", MINUS + "2,331.8", MINUS + "2,274.6", MINUS + "2,271.6")
assert mil(APP_FULL - APP_SUM_OF_SINGLES) == mil(APP_STEP_FX - APP_YEN_ONLY) == MINUS + "3.0"
s = new_slide(
    k(T_APP_SCREEN, "実画面"), T_APP_SCREEN,
    "経営の場では、「この条件なら、全社のEBITDAはどう変わるか」という仮定の問いが出ます。\n"
    "条件を変えるたびに集計をやり直す運用では、その場で答えにくくなります。",
    f"""【話す】左が、実際に動かしている画面です。食品損失を50%軽減し、同時に円高を10%進めた条件で、全社のEBITDAの、実績との差額を出しています。全額連結で{fmt(APP_FULL, "0.1")}億円、持分管理で{fmt(APP_MGMT, "0.1")}億円です。条件はスライダーで連続的に変えられ、変えるたびに差額と内訳が再計算されます。
【指す】左上の2枚の枠が結果で、全額連結と持分管理の差額を並べています。左下の棒グラフが内訳で、全額連結の差額を、イベントの影響を変えた分と、為替を変えた分に分けています。右の枠は、画面の左側にある条件（この図には写っていません）と、内訳の読み取りです。
【数字】全額連結の差は{yen(APP_FULL)}、持分管理の差は{yen(APP_MGMT)}です。全額連結の内訳は、イベントが{yen(APP_STEP_EVENTS)}、為替が{yen(APP_STEP_FX)}で、合計は差額と一致します。画面の「実績」（変えない状態）は{yen(APP_BASE_FULL)}で、第2章の実績と同じ値です。p.{PAGE_OF[T_Q1]}の基準値（予算に相当する値）とは別です。
【円高10%の意味】USD建ての子会社の、円換算のレートだけを10%下げる仮定です。為替ヘッジ、価格への転嫁、取引量の変化は反映していません。実際のレートの予想ではありません。
【内訳の読み方】内訳は、イベント、為替の順に分けています。軽減した分（USD建ての食品会社の損失の減少）にも円高が掛かるので、為替の段階（{mil(APP_STEP_FX)}）は、円高だけの差（{mil(APP_YEN_ONLY)}）と{mil(APP_STEP_FX - APP_YEN_ONLY)}違います（いずれも百万円）。同じ理由で、食品損失の軽減だけの差（{mil(APP_FOOD_ONLY)}）と、円高だけの差の和は{mil(APP_SUM_OF_SINGLES)}で、合計（{mil(APP_FULL)}）と一致しません。順序を変えると各段階の金額は変わりますが、合計は変わりません。
【端数】日次の行ごとに、小数2桁へ丸めて合計しているため、手計算の比例計算とは、1円未満ずれることがあります。円高10%と円安10%の差額が、完全には対称にならないのも、この丸めによるものです（差は0.01円から0.15円）。
【注意】金額は、デモのために設計した配賦と、仮定の為替です。実世界の因果の証明でも、実際の損益の予測でもありません。""",
    [APP_DONE_BY, "デモのデータ（架空）"],
    takeaway="円高10%は、USD建ての子会社の円換算レートだけを10%下げる仮定です。為替ヘッジ、価格への転嫁、取引量の変化は反映していません。",
    trace=APP_TRACE, foot=FOOT_APP)
IMG_X, IMG_W = .6, 6.9
h1 = picture(s, APP_IMG["result"], IMG_X, 2.4, IMG_W,
             "アプリの結果表示。全額連結は22.7億円の減少、持分管理は13.7億円の減少。")
h2 = picture(s, APP_IMG["waterfall"], IMG_X, 2.4 + h1 + .18, IMG_W,
             "差の内訳。イベントは+57.2、為替は−2,331.8、合計の差は−2,274.6（百万円）。")
assert 2.4 + h1 + .18 + h2 <= 6.28, (h1, h2)
RX, RW = 7.75, 4.98
box(s, RX, 2.4, RW, 3.8, WHITE, LINE)


def card_head(y, label, color):
    box(s, RX + .25, y + .03, .07, .22, color, None, radius=.035)
    text(s, label, RX + .45, y, RW - .65, .28, 12.5, color, True, spacing=1.0)


card_head(2.55, "条件（画面の左側で操作）", TEAL)
text(s, [[("食品損失を50%軽減", {"size": 15, "color": NAVY, "bold": True})],
         [("円高10%", {"size": 15, "color": NAVY, "bold": True})],
         [("どちらもスライダーで連続的に変えられます", {"size": 10.5, "color": MUTED})]],
     RX + .45, 2.93, RW - .65, .86, 12, spacing=1.3)
card_head(3.95, "差の内訳（全額連結、百万円）", CORAL)
for yy, label, value, color, size in [(4.33, "イベント", mil(APP_STEP_EVENTS), NAVY, 15),
                                      (4.69, "為替", mil(APP_STEP_FX), CORAL, 15),
                                      (5.13, "合計の差", mil(APP_FULL), CORAL, 16)]:
    text(s, label, RX + .45, yy, 1.6, .34, 12.5, MUTED if yy < 5 else INK, yy > 5, anchor=MIDDLE, spacing=1.0)
    text(s, value, RX + 2.0, yy, RW - 2.3, .34, size, color, True, RIGHT, MIDDLE, spacing=1.0)
box(s, RX + .45, 5.07, RW - .75, .012, LINE, None, rounded=False)
text(s, "段階は、イベント、為替の順です。順序を変えると、各段階の金額は変わります。", RX + .45, 5.58, RW - .7, .5, 10.5, MUTED,
     spacing=1.3)

# 25 -----------------------------------------------------------------------------------------------
expect(T_APP_PATH)
_biz = [e for e in EVENT_ORDER if not e.startswith("CROSS")]
_cross = [e for e in EVENT_ORDER if e.startswith("CROSS")]
assert len(_biz) == 8 and len(_cross) == 2
assert {APP_PATHS[e]["FinancialEffect"] for e in _biz} == {84} and {APP_PATHS[e]["FinancialEffect"] for e in _cross} == {336}
assert {events[e]["effects"] for e in _biz} == {84} and {events[e]["effects"] for e in _cross} == {336}
assert 8 * 84 + 2 * 336 == N_EFFECTS == 1344
BIZ_CT = (min(APP_PATHS[e]["Contract"] for e in _biz), max(APP_PATHS[e]["Contract"] for e in _biz))
CROSS_CT = (min(APP_PATHS[e]["Contract"] for e in _cross), max(APP_PATHS[e]["Contract"] for e in _cross))
assert (BIZ_CT, CROSS_CT) == ((6, 8), (24, 26))
FOD_CHAIN = APP_PATHS["FOD_NEG"]
assert (FOD_CHAIN["FinancialEffect"], FOD_CHAIN["Activity"], FOD_CHAIN["Contract"], FOD_CHAIN["FinancialMetric"],
        FOD_CHAIN["GroupKPI"]) == (84, 84, 6, 28, 15)
s = new_slide(
    k(T_APP_PATH, "経路の取得"), T_APP_PATH,
    "画面の差額が、どのイベントに由来し、何件の契約や指標につながるかを、その場で示せる必要があります。",
    f"""【話す】画面で差額を見たあと、イベントを選ぶと、そのイベントがOntologyのグラフ上で何につながっているかが、同じ画面に表示されます。アプリは、Graphに問い合わせて、イベントから影響額、取引活動、契約、日次指標、全社KPIまでの経路と件数を取得しています。第2章で確認した経路と同じ種類です。
【指す】左の図は、食品損失（FOD_NEG）を選んだときにグラフが返した件数です。イベント1件から、影響額{FOD_CHAIN['FinancialEffect']}件、取引活動{FOD_CHAIN['Activity']}件、契約{FOD_CHAIN['Contract']}件へつながり、影響額から分かれて、日次指標{FOD_CHAIN['FinancialMetric']}件、全社KPI{FOD_CHAIN['GroupKPI']}件につながります。矢印の名前は、p.{PAGE_OF[T_PARTS]}と同じ関係です（画面では、EventHasEffectなどの英語の名前で表示します）。右の画像が、その実画面です。画面は、上から下へ1列に並べて表示するため、1本の鎖のように見えますが、日次指標は契約からではなく、影響額から分かれています（画面の関係名の横に「影響額から」と表示しています）。
【確認した範囲】全10イベントで、グラフが返した影響額の件数が、Lakehouseの件数と一致しました。業種別の8イベントは各84件、横断の2イベントは各336件で、合計は{N_EFFECTS:,}件です。グラフが返した契約は、業種別で{BIZ_CT[0]}〜{BIZ_CT[1]}件、横断で{CROSS_CT[0]}〜{CROSS_CT[1]}件です。以前にGraphを直接照会した検証（第2章）とも、10イベントすべてで件数が一致しました。一致しない場合は、画面が不一致と表示します。
【補足】確認したのは、影響額の件数です。どの契約につながるかといった中身は、第2章の検証で確認しています。金額は、Lakehouseの値で計算しており、Graphの結果は使っていません。画面の名称は、資料の用語にそろえています（影響額、取引活動、日次指標）。
【注意】GQL Query APIはbetaで、Microsoft Learnは本番利用を推奨していません。Graphは、Ontologyの任意の層で、Fabricは、利用者が選ぶまでGraphを作りません。""",
    APP_LEARN + [APP_DONE_BY + "、Graphの直接照会（2026年10月27日）"],
    takeaway="確認したのは影響額の件数で、契約など経路の中身は、第2章の検証で確認しています。",
    trace=APP_TRACE + ["reports/graph_all_event_paths.json"], foot=FOOT_APP)
LX, LW = .6, 9.45
box(s, LX, 2.4, LW, 3.82, WHITE, LINE)
text(s, "食品損失（FOD_NEG）を選んだときに、グラフが返した経路", LX + .25, 2.52, LW - .5, .28, 13, TEAL, True, spacing=1.0)
NW, NH, GX = 1.62, .92, .78
NX = [LX + .35 + c * (NW + GX) for c in range(4)]
ROW1, ROW2 = 3.0, 4.38
chain_ = [("イベント", "RiskEvent", 1, PURPLE), ("影響額", "FinancialEffect", FOD_CHAIN["FinancialEffect"], CORAL),
          ("取引活動", "Activity", FOD_CHAIN["Activity"], NAVY), ("契約", "Contract", FOD_CHAIN["Contract"], NAVY)]
for c, (jp, en, cnt, color) in enumerate(chain_):
    app_node(s, NX[c], ROW1, NW, NH, jp, en, cnt, color)
for c, label in enumerate(["生む", "対象", "属する"]):
    x1, x2 = NX[c] + NW + .04, NX[c + 1] - .04
    arrow(s, x1, ROW1 + NH / 2, x2, ROW1 + NH / 2, STEEL, width=1.75)
    text(s, label, x1 - .1, ROW1 + NH / 2 - .3, x2 - x1 + .2, .22, 10.5, STEEL, True, CENTER, spacing=1.0)
app_node(s, NX[1], ROW2, NW, NH, "日次指標", "FinancialMetric", FOD_CHAIN["FinancialMetric"], TEAL)
app_node(s, NX[2], ROW2, NW, NH, "全社KPI", "GroupKPI", FOD_CHAIN["GroupKPI"], TEAL)
arrow(s, NX[1] + NW / 2, ROW1 + NH + .04, NX[1] + NW / 2, ROW2 - .04, STEEL, width=1.75)
text(s, "反映", NX[1] + NW / 2 + .12, (ROW1 + NH + ROW2) / 2 - .11, .8, .22, 10.5, STEEL, True, spacing=1.0)
arrow(s, NX[1] + NW + .04, ROW2 + NH / 2, NX[2] - .04, ROW2 + NH / 2, STEEL, width=1.75)
text(s, "集約", NX[1] + NW - .06, ROW2 + NH / 2 - .3, GX + .2, .22, 10.5, STEEL, True, CENTER, spacing=1.0)
text(s, f"矢印は関係の向きで、p.{PAGE_OF[T_PARTS]}と同じです。数字は、グラフが返した件数です。", NX[0], ROW2 + .02, NW + .55, NH, 10.5,
     MUTED, anchor=MIDDLE, spacing=1.3)
box(s, LX + .2, 5.5, LW - .4, .012, LINE, None, rounded=False)
chip(s, "全10イベントで一致", LX + .25, 5.68, 2.1, TEAL, PALE, 12.5, .34)
text(s, f"グラフが返した影響額は、業種別の8イベントで各84件、横断の2イベントで各336件、合計{N_EFFECTS:,}件です。Lakehouseの件数と同じです。",
     LX + 2.6, 5.56, LW - 2.85, .56, 12, INK, anchor=MIDDLE, spacing=1.3)
PX, PW = 12.73 - 2.1, 2.1
ph = picture(s, APP_IMG["path"], PX, 2.4, PW,
             f"食品損失を選んだときの経路の表示。イベント1件から、影響額{FOD_CHAIN['FinancialEffect']}件、取引活動{FOD_CHAIN['Activity']}件、"
             f"契約{FOD_CHAIN['Contract']}件、日次指標{FOD_CHAIN['FinancialMetric']}件、全社KPI{FOD_CHAIN['GroupKPI']}件。"
             "グラフとLakehouseで影響額の件数が一致（84件）。")
assert 2.4 + ph <= 5.6, ph
text(s, [[("実画面（食品損失を選択）", {"size": 10.5, "color": MUTED, "bold": True})],
         [("画面は1列の表示です。日次指標は、影響額から分かれます。", {"size": 10.5, "color": MUTED})]],
     PX, 2.4 + ph + .05, PW, .72, 10.5, align=CENTER, spacing=1.25)

# 26 -----------------------------------------------------------------------------------------------
expect(T_APP_SCOPE)
_nv = " ".join(app["not_verified"])
assert all(w in _nv for w in ("利用者ごとの権限", "性能", "コスト", "リージョン", "beta", "鮮度"))
assert app["ui_observations"]["console_errors"] == 0
s = new_slide(
    k(T_APP_SCOPE, "確認範囲"), T_APP_SCOPE,
    "デモで動いたことと、記載に基づくことが混ざると、PoCで何を評価するかを決めにくくなります。\n"
    "確認の根拠ごとに分けると、PoCの評価項目が、未確認の列にそのまま並びます。",
    f"""【話す】この章で確認できたこと、Microsoft Learnの記載に基づくこと、まだ確認していないことを、分けてお示しします。確認できたのは4つです。1つ目は、アプリから10イベントすべての経路をGraphで取得でき、影響額の件数がLakehouseと一致したことです。2つ目は、アプリが実績を再計算した結果が、Lakehouseの保存値と1円単位で一致したことです（日次{APP_ROWS:,}行、不一致0件）。3つ目は、放置したあとの最初の呼び出しで、グラフの起動に約1分かかり、画面が待ち時間を表示して待つことです。2回目以降は、グラフへの問い合わせが約1.1〜1.6秒でした（一度だけ6.1秒）。4つ目は、サインインしていない利用者には、アプリの内容にもFunctionsにも届かないことです。
【記載に基づく前提】Microsoft Learnの記載で、このデモでは検証していない点です。Fabric AppsはPreviewです。GQL Query APIはbetaで、Learnは本番利用を推奨していません。FunctionsがFabricを呼び出すときのアイデンティティは、現在はアプリの所有者で、画面を見る利用者の権限は反映されません。Fabric Appsのリージョンは限定的で、割り当てた容量のCUを消費します。
【未確認】利用者数、同時アクセス、データ量を増やしたときの性能、容量の消費量とコスト、デモ環境以外のリージョンでの動作、グラフが古くなったときの挙動です。件数の一致は確認していますが、内容の鮮度は確認していません。いずれもPoCで確認します。
【権限について】p.{PAGE_OF[T_GOV]}の権限のページは、Ontologyのアイテムとデータ側の権限の話です。この章のアプリでは、別の話として、FunctionsがどのIDでFabricを呼び出すかが問題になります。現在の仕様では、呼び出しはアプリの所有者のIDで行われ、画面を見る全員に、同じ範囲が見えます。利用者ごとに見せる範囲を変える場合は、アプリ側の設計が要り、このデモでは検証していません。
【初回の待ち】放置したあとの最初の呼び出しは、グラフの起動に約1分かかりました（2026年10月27日と28日の実測、59秒から63秒）。Functionsの実行は、Learnの記載で最大240秒です。
【確認の仕方】確認した日は2026年10月28日で、Fabricのアプリを実際に開いて確認しました。保存した記録は、reportsフォルダの「whatif_app_live_verification」で始まるファイルです。""",
    APP_LEARN + ["Microsoft Learn：fabric/apps/pricing（2026-09-15更新）", APP_DONE_BY],
    takeaway="呼び出しは所有者のIDで行われます。画面を見る全員に同じ範囲を見せてよいかを、PoCの最初に決めます。",
    trace=APP_TRACE + ["reports/whatif_app_live_verification_2026-10-28.json:not_verified,learn_sources"],
    foot=FOOT_APP)
scope = [
    ("確認した", TEAL, "このデモで、実際に動かして確認", [
        "10イベントの経路をGraphで取得。影響額の件数がLakehouseと一致",
        f"実績EBITDAの再計算が、保存値と一致（日次{APP_ROWS:,}行、不一致0件）",
        "放置後の初回は約1分、2回目以降は約1.1〜1.6秒",
        "未サインインでは、アプリにもFunctionsにも届かない"]),
    ("記載に基づく前提", PURPLE, "Microsoft Learnの記載。デモでは未検証", [
        "Fabric AppsはPreview。クエリ用APIはbeta（本番利用は非推奨）",
        f"呼び出しは所有者のID。利用者ごとの権限は反映されない（p.{PAGE_OF[T_GOV]}のOntologyの権限とは別）",
        "リージョンは限定的。容量のCUを消費する"]),
    ("未確認", CORAL, "PoCで確認する項目", [
        "利用者数、同時アクセス、データ量を増やしたときの性能",
        "容量の消費量とコスト",
        "デモ環境以外のリージョンでの動作",
        "グラフが古くなったときの挙動"]),
]
for i, (head, color, sub_, items) in enumerate(scope):
    x = .6 + i * 4.09
    box(s, x, 2.4, 3.95, 3.82, WHITE, LINE)
    box(s, x, 2.4, 3.95, .1, color, None, radius=.04)
    numdot(s, str(i + 1), x + .45, 2.95, .27, color, size=15)
    text(s, head, x + .85, 2.7, 2.9, .4, 18, NAVY, True, spacing=1.2)
    text(s, sub_, x + .85, 3.08, 2.95, .24, 10.5, MUTED, True, spacing=1.0)
    yy = 3.55
    for it in items:
        nl = est_lines(it, 3.3, 12.5)
        hh = nl * 12.5 * 1.3 / 72
        box(s, x + .25, yy + .05, .07, hh - .02, color, None, radius=.035)
        text(s, it, x + .47, yy, 3.3, hh + .02, 12.5, INK, spacing=1.3)
        yy += hh + .2
    assert yy <= 6.2 + .1, (head, yy)


# =====================================================================================================
# Chapter 5
# =====================================================================================================
divider(CHAPTERS[4])

# 23 -----------------------------------------------------------------------------------------------
expect(T_SMALL)
assert [rel_pair[n] for n in ("EventHasEffect", "EffectOnContract", "ContractOwnedByCompany")] == [
    ("RiskEvent", "FinancialEffect"), ("FinancialEffect", "Contract"), ("Contract", "Company")]
assert audit["diagram_nodes"] == 8 and audit["diagram_edges"] == 7
assert len(entity_names) == 17 and len(relationships) == 39
s = new_slide(
    k(T_SMALL, "小さく始める"), T_SMALL,
    "最初から全体を作る必要はないと考えています。\n"
    "答えたい質問を1つ決め、質問に出てくる名詞を概念に、つなぐ動詞を関係にする進め方をご提案します。",
    """【話す】最初から17種類の概念と39種類の関係を作る必要はないと考えています。答えたい質問を1つ決め、その質問に出てくる名詞を概念に、名詞をつなぐ動詞を関係にする進め方をご提案します。
【指す】左の5ステップを上から。右は、このデモの定義のうち、質問ごとに使った範囲です。質問④に使った範囲は、4つの概念と3つの関係です。質問③の根拠までの経路は、8つの概念と7つの関係です。いずれも、このデモの17と39の一部で、単独では作成も検証もしていません。
【手間】工数は、データの状態で大きく変わります。キーをそろえる、8社分を統合した表を作る、リンク用の表を用意するといった、データ側の準備の有無を、PoCの前に確認します。
【近道】既存のPower BIセマンティックモデルがあれば、そこからOntologyを生成できます（Preview）。ただし、現時点ではセマンティックモデルに結んだOntologyは、Data Agentが動作しない既知の問題があり、グラフ化もできません。""",
    ["Microsoft Learn：fabric/iq/ontology（2026-09〜10更新）", "デモのOntology定義とGraphの検証結果"],
    takeaway="工数は、データの状態で大きく変わります。PoCの前に、キーや統合した表の有無を確認します。",
    trace=["ontology_tmdl/entityRelationships.tmdl", "reports/step3_live_audit.json:diagram_nodes,diagram_edges"])
box(s, .6, 2.35, 6.7, 3.9, WHITE, LINE)
text(s, "進め方（5ステップ）", .85, 2.47, 5.5, .3, 15, TEAL, True, spacing=1.0)
for i, (head, sub) in enumerate([
        ("質問を1つ決める", "例：どの契約が、どのイベントで減ったか"),
        ("名詞を概念にする", "質問に出てくる、イベント、影響額、契約、会社"),
        ("動詞を関係にする", "イベント → 影響額 → 契約 → 会社 のつながり"),
        ("表を1つずつ結び、質問で確かめる", "概念ごとに、Lakehouseの表とキー列を指定する"),
        ("足すのは、その後", "概念と関係を増やし、ルールなどの新機能を足す")]):
    yy = 2.95 + i * .65
    numdot(s, str(i + 1), 1.05, yy + .25, .2, TEAL, size=12)
    text(s, head, 1.4, yy, 5.7, .28, 14, NAVY, True, spacing=1.0)
    text(s, sub, 1.4, yy + .3, 5.7, .24, 11.5, MUTED, spacing=1.0)
box(s, 7.5, 2.35, 5.23, 3.9, WHITE, LINE)
text(s, "このデモの中で見ると", 7.75, 2.47, 4.7, .3, 15, TEAL, True, spacing=1.0)
for i, (big, color, head, detail) in enumerate([
        ("4 / 3", TEAL, "質問④で使った範囲", "イベント → 影響額 → 契約 → 会社"),
        ("8 / 7", PURPLE, "質問③の根拠までの経路", "根拠記録から全社KPIまで（食品の例）"),
        ("17 / 39", CORAL, "このデモの全体", "事業固有の観測、出荷、日次指標などを含む")]):
    yy = 2.9 + i * .88
    box(s, 7.75, yy, 4.75, .8, PALE, None, radius=.07)
    text(s, big, 7.9, yy, 1.45, .8, 21, color, True, anchor=MIDDLE, spacing=1.0)
    text(s, head, 9.4, yy + .1, 3.0, .26, 12.5, NAVY, True, spacing=1.0)
    text(s, detail, 9.4, yy + .42, 3.05, .34, 10.5, INK, spacing=1.15)
text(s, "数字は「概念の数 / 関係の数」です。4/3と8/7は、このデモの一部の範囲で、単独では作成も検証もしていません。",
     7.75, 5.58, 4.75, .6, 10.5, MUTED, spacing=1.3)

# 24 -----------------------------------------------------------------------------------------------
expect(T_POC)
s = new_slide(
    k(T_POC, "PoCの進め方"), T_POC,
    "PoCの目的は、貴社のデータと問いで、同じ形の答えと根拠が出るかを確かめることです。\n"
    "評価の基準を先に決めておくと、結果を判断しやすくなります。",
    f"""【話す】PoCの目的は、貴社のデータと、経営会議で実際に問われる問いで、今日と同じ形の答えと根拠が出るかを確かめることです。左が評価の観点、右がご準備いただきたい情報です。
【進め方の例】質問を5〜10問決め、最初は1事業、1〜2システムのデータで、最小のOntologyを作ります。既存のレポートの数字を正解として、金額が一致するかを確かめます。同じ質問を複数回実行して、回答のぶれも評価します。
【利用環境】Fabricの容量と、OntologyおよびData Agentを使うためのテナント設定の有効化が、前提になります（Microsoft Learnの前提条件）。
【アプリで使う場合】第4章のように、画面を持つアプリで使う場合は、呼び出しのID（権限の扱い）、性能、容量の消費量も、評価に加えます（p.{PAGE_OF[T_APP_SCOPE]}）。
【イベントの記録】整ったイベントの一覧が最初から社内にないのは普通です。基準値と実績の差が大きい月と会社から、差異分析のコメントや、事故、契約変更の記録を拾い、小さな台帳として育てます。AIで候補を抽出し、担当者が確認して登録する進め方もあります。20〜30件は、仮の目安です。
【注意】進め方、件数、期間は、対象の範囲とデータの状態によって調整します。""",
    ["Microsoft Learn：fabric/iq/ontology（2026-09〜10更新）、how-to-bind-data（2026-10-20更新）", "デモ環境での検証の進め方"],
    takeaway="イベントの記録が少なくても、基準値との差が大きい月から集めて始められます。")
poc_left = [
    ("答えの正確さ", "元データの集計と、金額が一致するか"),
    ("根拠への到達", "金額から、契約と記録まで関係をたどれるか"),
    ("質問の自由度", "現場の言葉の短い質問で、同じ答えが得られるか"),
    ("権限と秘密度", "既存の権限や秘密度ラベルのもとで、想定どおりに動くか"),
    ("再現性と運用", "同じ質問の回答のぶれ。定義の変更と更新の手順"),
    ("アプリでの利用（任意）", f"画面を持つアプリ：権限の扱い、性能、容量の消費量（p.{PAGE_OF[T_APP_SCOPE]}）"),
]
poc_right = [
    ("代表的な質問", "経営会議で実際に問われる質問を、5〜10問（仮）"),
    ("対象データ", "所在と担当者。最初は1事業、1〜2システム（仮）"),
    ("照合用の正解", "既存のレポートなど、金額を突き合わせる数字"),
    ("イベントの記録", "差異分析のコメントや事故の記録。20〜30件は仮の目安"),
    ("利用環境", "Fabricの容量と、Ontology・Data Agentのテナント設定"),
    ("評価に参加する方", "経営企画、事業部門、IT・データの担当者"),
]
for col, (title, items, color) in enumerate([("確認すること", poc_left, TEAL), ("ご準備いただくこと", poc_right, PURPLE)]):
    x = .6 + col * 6.15
    box(s, x, 2.35, 5.98, 3.9, WHITE, LINE)
    text(s, title, x + .25, 2.45, 5.0, .3, 15, color, True, spacing=1.0)
    for i, (head, body) in enumerate(items):
        yy = 2.88 + i * .56
        numdot(s, str(i + 1), x + .45, yy + .24, .19, color, size=11.5)
        text(s, head, x + .85, yy, 4.9, .26, 13.5, NAVY, True, spacing=1.0)
        text(s, body, x + .85, yy + .27, 4.95, .26, 11, INK, spacing=1.15)

# 25 -----------------------------------------------------------------------------------------------
expect(T_CAVEAT)
s = new_slide(
    k(T_CAVEAT, "留意点"), T_CAVEAT,
    "OntologyとData Agentに加えて、第4章のFabric Appsも、現在Previewです。\n"
    "次の点を前提に、PoCの範囲と評価の基準を決めることをお勧めします。",
    """【話す】OntologyとData Agent、第4章のFabric Appsは、現在Previewの機能です。デモで確認できたことと、まだ確認できていないこと、製品側の制限をお伝えします。PoCの範囲と評価の基準は、これらを前提に決めます。
【6つの点】①提供状況：Ontology、Data Agent、Fabric AppsはPreview、Graphのクエリ用APIはbetaで、仕様や制限が変わる場合があります。②日本語：日本語で動作を確認した範囲での対応で、公式のサポート保証ではありません。③回答のばらつき：言語モデルのため、文面や優先度の線引きは、実行ごとに変わります。デモの確認では、表の金額は元データと一致しましたが、周辺の説明文に誤りが出ることがありました。「円高になったら」のような試算の問いは、結果が不安定でした。④対応していない範囲：会社から会社への連鎖は、関係の追加が必要で未対応です。セマンティックモデルに結んだOntologyは、Data Agentが動作しない既知の問題があり、グラフ化もできません。⑤データ：デモは合成データです。規模、性能、コストは、貴社のデータで別途確認が必要です。⑥従来版の廃止：Ontologyの従来版（旧体験）は2027-01-31に廃止され、新しい体験へのコピーによる移行が必要です。
【補足】デモのOntologyは、新しい体験で作っているため、廃止の影響を受けません。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、how-to-create-data-agent（2026-09-13更新）",
     "Microsoft Learn：fabric/apps/overview（2026-09-29更新）",
     "デモ環境での確認（2026年10月26日〜27日）"],
    takeaway="回答のばらつきとデータの規模は、貴社のデータを使ったPoCで確かめられます。",
    trace=["README.md:検証の状況", "reports/da_casual_after_2026-10-26.json:known_limits",
           "reports/da_group_wide_2026-10-27.json"])
cav = [
    ("提供状況", CORAL, "Ontology、Data Agent、Fabric Apps（第4章）はPreview、Graphのクエリ用APIはbetaです。仕様や制限は変わる場合があります。"),
    ("日本語", PURPLE, "日本語の質問は、動作を確認した範囲での対応です。公式のサポート保証ではありません。"),
    ("回答のばらつき", CORAL, "言語モデルのため、文面や優先度の線引きは、実行ごとに変わります。表の金額は一致しましたが、説明文に誤りが出る場合があります。「円高になったら」のような試算は不安定でした。"),
    ("対応していない範囲", PURPLE, "会社から会社への連鎖は、関係の追加が必要で未対応です。セマンティックモデルに結んだOntologyは、Data Agentが動作しない既知の問題があり、グラフ化もできません。"),
    ("データ", TEAL, "デモのデータは合成データです。規模、性能、コストは、貴社のデータで別途確認が必要です。"),
    ("従来版の廃止", TEAL, "Ontologyの従来版（旧体験）は2027-01-31に廃止されます。お使いの場合は、新しい体験へのコピーによる移行が必要です。"),
]
for i, (head, color, body) in enumerate(cav):
    x = .6 + (i % 3) * 4.09
    y = 2.35 + (i // 3) * 1.99
    box(s, x, y, 3.95, 1.9, WHITE, LINE)
    box(s, x + .02, y + .15, .07, 1.6, color, None, radius=.035)
    text(s, head, x + .3, y + .14, 3.5, .3, 15, color, True, spacing=1.0)
    text(s, body, x + .3, y + .5, 3.5, 1.35, 12, INK, spacing=1.4)

# 26 closing -----------------------------------------------------------------------------------------
expect(T_NEXT)
s = base_slide(NAVY)
n = len(prs.slides)
title_text(s, T_NEXT, .8, 1.35, 11.8, .62, 30, WHITE)
motif(s, .8, .78, 1.15, MINT)
text(s, "第5章 進め方  |  次のステップ", 1.5, .82, 8.0, .3, 14, MINT, True, spacing=1.0)
if est_lines(T_NEXT, 11.8, 30) != 1:
    WARN.append((n, "TITLE WRAPS", T_NEXT, 1))
text(s, "本日確認した内容をもとに、貴社の問いとデータで、小さく検証する進め方をご提案します。", .82, 2.1, 11.6, .4, 16,
     BODY_ON_NAVY, spacing=1.35)
text(s, "本日の要点", .85, 2.95, 5.4, .32, 16, MINT, True, spacing=1.0)
for i, line in enumerate([
        "EBITDAの増減を、イベント、契約、根拠記録までたどって説明できました。",
        "各社の原本は残したまま、定義と関係をData Agentから参照できました（コピーした表とGraphを含みます）。",
        "業務アプリから、条件を変えた差額と、Ontologyのグラフ上の経路を確認できました（Preview）。",
        "小さな範囲から始める進め方を、ご提案します。Previewの留意点は、PoCの評価で確認します。"]):
    yy = 3.4 + i * .8
    numdot(s, str(i + 1), 1.1, yy + .39, .22, MINT, NAVY, 13)
    text(s, line, 1.5, yy, 4.75, .78, 14, BODY_ON_NAVY, anchor=MIDDLE, spacing=1.3)
box(s, 6.7, 2.95, 6.03, 3.5, WHITE, None, radius=.14)
text(s, "PoCの進め方", 7.0, 3.1, 5.4, .32, 16, TEAL, True, spacing=1.0)
for i, (head, body) in enumerate([
        ("質問とデータの確認", "代表的な質問を決め、対象データを棚卸しします（ワークショップ）"),
        ("最小のOntologyで検証", "5〜10問のうち、まず1事業・1問で、答え、根拠、再現性を確認します"),
        ("評価と拡張の判断", "結果をもとに、対象の事業や機能を広げるかを決めます")]):
    yy = 3.58 + i * .94
    numdot(s, str(i + 1), 7.25, yy + .3, .2, TEAL, WHITE, 12)
    text(s, head, 7.65, yy, 4.9, .28, 14.5, NAVY, True, spacing=1.0)
    text(s, body, 7.65, yy + .32, 4.9, .52, 12, INK, spacing=1.3)
text(s, "参考：Microsoft Learn「What is ontology (preview)?」  learn.microsoft.com/fabric/iq/ontology/overview",
     .85, 6.72, 11.0, .26, 11, BODY_ON_NAVY, spacing=1.0)
text(s, "デモのデータは架空です。Ontology、Data Agent、Fabric AppsはPreviewです。", .85, 7.1, 8.0, .22, 10.5, BODY_ON_NAVY,
     spacing=1.0)
text(s, f"{n:02}", 12.13, 7.04, .6, .3, 13, MINT, True, RIGHT, spacing=1.0)
finish_notes(s, """【話す】今日は、EBITDAの増減を、イベント、契約、根拠記録までたどって説明できることを確認しました。第4章では、画面を持つ業務アプリから、条件を変えた差額と、Ontologyのグラフ上の経路を確認する例もお見せしました。次は、貴社の問いとデータで、小さく検証することをご提案します。
【次のステップ】①代表的な質問を決め、対象データを棚卸しする（ワークショップ形式）。②1事業、1つの質問で、最小のOntologyを作り、答え、根拠、再現性を確認する（PoC）。③結果をもとに、対象の事業や機能を広げるかを決める。期間は、対象の範囲に応じて調整します。
【補足】Ontology、Data Agent、Fabric AppsはPreviewのため、仕様や制限は変わる場合があります。最新の情報は、Microsoft Learnをご確認ください。""",
             ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）"])
slide_metadata.append({"slide": n, "title": T_NEXT, "sources": ["Microsoft Learn：fabric/iq/ontology/overview"],
                       "trace": []})


# =====================================================================================================
# Appendix
# =====================================================================================================
divider(APPENDIX)

# 28 -----------------------------------------------------------------------------------------------
expect(T_A_ENV)
mf = load("config/deployment_manifest.json")
N_CHILD_TABLES = cloud["tables"] - lh_tables["LH_Group_SAP"]
assert (mf["storage"]["lakehouses"], mf["storage"]["zero_copy_shortcuts"], N_CHILD_TABLES) == (9, 8, 78)
assert mf["storage"]["copied_shortcut_rows"] == 0 and mf["storage"]["source_lakehouses_preserved"] is True
assert (mf["ontology"]["entity_types"], mf["ontology"]["relationship_types"]) == (17, 39)
assert (mf["ontology"]["backed_tables"], mf["ontology"]["runtime_verified_nodes"],
        mf["ontology"]["runtime_verified_edges"]) == (20, 33960, 65684)
_bind = [b["alter"]["partition"]["source"]["entityName"] for b in load("config/ontology_connection_bindings.json")]
shortcuts = load("config/sector_shortcuts.json")
_sc_tables = {v["table"] for v in shortcuts.values()}
assert len(shortcuts) == 8 and len(_bind) == 20 and _sc_tables <= set(_bind)
_parent_physical = {k_.split(".", 1)[1] for k_ in cloud["counts"] if k_.startswith("LH_Group_SAP.")}
_bound_physical = set(_bind) - _sc_tables
assert len(_bound_physical) == 12 and _bound_physical <= _parent_physical and len(_parent_physical) == 17
N_METRICS = node_counts["FinancialMetric"]
assert (N_ACTIVITIES, N_METRICS, N_EVIDENCE) == (8760, 17520, 64)
_rows_parent = sum(v for k_, v in cloud["counts"].items() if k_.startswith("LH_Group_SAP."))
_rows_child = sum(v for k_, v in cloud["counts"].items() if not k_.startswith("LH_Group_SAP."))
assert _rows_parent + _rows_child == cloud["rows"] == mf["storage"]["physical_rows"] == 90424
s = new_slide(
    k(T_A_ENV, "デモ環境"), T_A_ENV,
    "架空の総合商社グループを、Fabric上に再現した環境です。\n"
    "データは合成データで、為替だけが欧州中央銀行（ECB）の公表値です。",
    f"""【話す】本編で使ったデモ環境の構成です。左は、使う側から元のデータまでの層、右はデータの規模です。
【指す】下から順に。8社の原本は、会社ごとのLakehouseに残っています（78表）。親のLakehouseには、全社分析用の表（17表の一部）と、事業固有の観測を原本から参照する8本のショートカットがあります。その上に、Ontology（17概念、39関係）があり、Ontologyの定義から作ったGraph（ノード{sum(node_counts.values()):,}個、エッジ{sum(edge_counts.values()):,}本）が重なります。一番上が、使う側です。
【補足】Data Agentは、公開済みの版で確認しました。Notebookは、根拠から全社KPIまでの経路を表示するために使いました。Ontologyが結んでいる表は20表で、内訳は全社分析用の12表（コピーして作成）と、事業固有の8表（ショートカット、ゼロコピー）です。
【前提】会社、契約、イベント、金額は架空です。規模、性能、コストの目安にはなりません。""",
    ["デモ環境の設計と検証記録（2026年10月23日構築、10月27日確認）"],
    takeaway="この環境の規模は、性能やコストの参考になりません。実データでのPoCで確認します。",
    trace=["config/deployment_manifest.json", "reports/cloud_validation.json", "config/sector_shortcuts.json",
           "config/ontology_connection_bindings.json", "reports/graph_node_counts.json",
           "reports/graph_edge_counts.json"])
EX, EW = 1.95, 6.2
for label, y, h in [("使う側", 2.35, .95), ("意味と関係", 3.5, 1.0), ("データ", 4.75, 1.5)]:
    text(s, label, .6, y, 1.25, h, 14, TEAL, True, anchor=MIDDLE, spacing=1.0)
for i, (a, b) in enumerate([("Data Agent", "公開済み・Preview"), ("Notebook", "根拠から全社KPIまでの経路を表示")]):
    bx = EX + i * 3.15
    box(s, bx, 2.35, 3.05, .95, WHITE, LINE)
    text(s, [[(a, {"bold": True, "size": 14, "color": NAVY})], [(b, {"size": 11, "color": MUTED})]],
         bx + .15, 2.35, 2.8, .95, 13, anchor=MIDDLE, spacing=1.25)
box(s, EX, 3.5, 2.85, 1.0, WHITE, NAVY, lw=2.0)
text(s, [[("Ontology", {"bold": True, "size": 14.5, "color": NAVY})],
         [("17概念、39関係", {"size": 12, "color": INK})]], EX + .15, 3.5, 2.6, 1.0, 13, anchor=MIDDLE, spacing=1.25)
box(s, EX + 3.35, 3.5, 2.85, 1.0, MAT_FILL, PURPLE, lw=1.75)
text(s, [[("Graph（任意）", {"bold": True, "size": 14.5, "color": PURPLE})],
         [(f"ノード{sum(node_counts.values()):,}個\nエッジ{sum(edge_counts.values()):,}本", {"size": 11, "color": INK})]],
     EX + 3.5, 3.5, 2.6, 1.0, 13, anchor=MIDDLE, spacing=1.2)
box(s, EX, 4.75, 2.85, 1.5, GRAY, None)
text(s, [[("親のLakehouse", {"bold": True, "size": 13.5, "color": NAVY})],
         [(f"{len(_parent_physical)}表＋ショートカット8本", {"size": 12, "color": INK})],
         [("Ontologyに結ぶのは12表＋8本", {"size": 11, "color": MUTED})]],
     EX + .15, 4.75, 2.6, 1.5, 12, anchor=MIDDLE, spacing=1.35)
box(s, EX + 3.35, 4.75, 2.85, 1.5, GRAY, None)
text(s, [[("子会社8社のLakehouse", {"bold": True, "size": 13.5, "color": NAVY})],
         [(f"{N_CHILD_TABLES}表（原本）", {"size": 12, "color": INK})],
         [("会社ごとに分離。書き換えない", {"size": 11, "color": MUTED})]],
     EX + 3.5, 4.75, 2.6, 1.5, 12, anchor=MIDDLE, spacing=1.35)
arrow(s, EX + 1.42, 3.48, EX + 1.42, 3.32, STEEL, width=2.0)
arrow(s, EX + 4.77, 3.48, EX + 4.77, 3.32, STEEL, width=2.0)
arrow(s, EX + 1.42, 4.73, EX + 1.42, 4.52, STEEL, width=2.0)
arrow(s, EX + 2.87, 4.0, EX + 3.33, 4.0, PURPLE, width=2.0)
arrow(s, EX + 3.33, 5.5, EX + 2.87, 5.5, STEEL, width=2.0)
scale_tiles = [("期間", "365日", TEAL), ("契約", f"{N_CONTRACTS}件", TEAL),
               ("取引活動", f"{N_ACTIVITIES:,}件", NAVY), ("根拠記録", f"{N_EVIDENCE}件", PURPLE),
               ("日次指標", f"{N_METRICS:,}件", NAVY),
               ("Ontologyが結ぶ表\n（コピー12、参照8）", "20表", TEAL),
               ("全Lakehouseの行数\n（9個、95表）", f"{cloud['rows']:,}行", PURPLE),
               ("うち子会社の原本", f"{_rows_child:,}行", NAVY)]
for i, (label, value, color) in enumerate(scale_tiles):
    x = 8.45 + (i % 2) * 2.2
    y = 2.35 + (i // 2) * .98
    box(s, x, y, 2.1, .88, WHITE, LINE)
    text(s, label, x + .15, y + .07, 1.85, .36, 10, MUTED, True, spacing=1.1)
    text(s, value, x + .15, y + .45, 1.85, .38, 18, color, True, spacing=1.0)

# 29 -----------------------------------------------------------------------------------------------
expect(T_A_MAP)
ENT_JP = {"Company": "会社", "Contract": "契約", "Activity": "取引活動", "Shipment": "出荷", "RiskEvent": "イベント",
          "Evidence": "根拠", "FinancialEffect": "影響額", "FinancialMetric": "日次指標", "GroupKPI": "全社KPI"}
EXT_NAMES = [e for e in entity_names if e.endswith("Extension")]
assert len(EXT_NAMES) == 8 and set(ENT_JP) == set(entity_names) - set(EXT_NAMES)
assert all(sum(1 for r in relationships if r[1] == e) == 3 for e in EXT_NAMES)
assert {node_counts[e] for e in EXT_NAMES} == {365}
map_rows = [(ENT_JP[e], e, node_counts[e]) for e in
            ("Company", "Contract", "Activity", "Shipment", "RiskEvent", "Evidence", "FinancialEffect",
             "FinancialMetric", "GroupKPI")]
map_rows.append(("事業固有の観測×8種", "FoodsJPExtension など", sum(node_counts[e] for e in EXT_NAMES)))
assert sum(r[2] for r in map_rows) == sum(node_counts.values()) == 33960
s = new_slide(
    k(T_A_MAP, "概念と関係の一覧"), T_A_MAP,
    "デモのOntologyに定義した、概念と関係の一覧です。\n"
    "関係は、「どの概念から、どの概念へ」の向きで示しています。",
    f"""【話す】デモのOntologyが持つ17種類の概念と39種類の関係の一覧です。質問されたときの参照用に使ってください。
【指す】左の表が概念です。その右端の数字は、Graphに取り込んだ実例（ノード）の数で、合計は{sum(node_counts.values()):,}です。事業固有の観測は、事業と国ごとに1種類（8種類）で、各種類に365日分の実例があります。右側の表は、共通の15種類の関係です。英語の名前は、Fabricの画面に表示される名前です。
【補足】事業固有の観測8種は、取引活動、会社、契約への関係を3本ずつ持ち、合計24種類です。共通の15種類と合わせて、関係は39種類です。
【注意】デモ用に整理した定義です。貴社に適用する際は、質問に必要な範囲から定義します（第5章）。""",
    ["デモのOntology定義とGraphの件数（2026-10-27確認）"],
    takeaway="関係は全部で39種類です。共通の15種類に、事業固有の観測8種が持つ24種類（8種×3）が加わります。",
    trace=["ontology_tmdl/entities/*.tmdl", "ontology_tmdl/entityRelationships.tmdl", "reports/graph_node_counts.json"])
box(s, .6, 2.35, 5.95, 3.9, WHITE, LINE)
for cx, cwid, label, al in [(.2, 1.9, "概念", None), (2.15, 2.3, "名称", None), (3.9, 1.8, "実例の数", RIGHT)]:
    text(s, label, .6 + cx, 2.47, cwid, .24, 11.5, TEAL, True, al, spacing=1.0)
for i, (jp, en, cnt) in enumerate(map_rows):
    yy = 2.82 + i * .335
    if i % 2:
        box(s, .68, yy - .03, 5.79, .31, PALE, None, radius=.05)
    text(s, jp, .6 + .2, yy, 1.95, .27, 12, NAVY, True, anchor=MIDDLE, spacing=1.0)
    text(s, en, .6 + 2.15, yy, 2.3, .27, 11, MUTED, anchor=MIDDLE, spacing=1.0)
    text(s, f"{cnt:,}" + ("（365×8）" if i == len(map_rows) - 1 else ""), .6 + 3.9, yy, 1.8, .27,
         12 if i < len(map_rows) - 1 else 11, INK, True, RIGHT, MIDDLE, spacing=1.0)
box(s, 6.75, 2.35, 5.98, 3.9, WHITE, LINE)
text(s, "共通の関係（15種類）", 6.95, 2.47, 3.0, .24, 11.5, TEAL, True, spacing=1.0)
text(s, "Fabricの画面での名前", 9.95, 2.47, 2.6, .24, 11.5, TEAL, True, spacing=1.0)
for i, (name, a, b) in enumerate(CORE_REL):
    yy = 2.82 + i * .225
    if i % 2:
        box(s, 6.83, yy - .015, 5.82, .215, PALE, None, radius=.04)
    text(s, f"{ENT_JP[a]} → {ENT_JP[b]}", 6.95, yy, 2.9, .2, 11.5, NAVY, True, anchor=MIDDLE, spacing=1.0)
    text(s, name, 9.95, yy, 2.7, .2, 10.5, MUTED, anchor=MIDDLE, spacing=1.0)

# 30 -----------------------------------------------------------------------------------------------
expect(T_A_QA)
_q2 = next(q for q in fix["demo_questions"] if q["id"] == "Q2")["result_tables"][0]
_q2m = {row[0]: Decimal(str(row[1])) for row in _q2["rows"]}
assert num(_q2m["CROSS_NEG"]) == num(oku(EV["CROSS_NEG"])) and num(_q2m["CROSS_POS"]) == num(oku(EV["CROSS_POS"]))
_q1 = next(q for q in fix["demo_questions"] if q["id"] == "Q1")["result_tables"][0]["rows"][0]
assert Decimal(str(_q1[0])).quantize(Decimal("0.01"), ROUND_HALF_UP) == oku(ACTUAL) == Decimal("447.57")
_fin = {s_["entity_id"]: oku(ebitda_co[s_["entity_id"]]) for s_ in subsidiaries if s_["sector_code"] == "finance"}
assert (_fin["SUB_FIN_JP_01"], _fin["SUB_FIN_US_01"]) == (Decimal("41.25"), Decimal("44.61"))
assert len(FOD_ROWS) == 6 and oku(EV["FOD_NEG"]) == Decimal("-1.14")
_pct = (-EV["CROSS_NEG"] / ACTUAL * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
assert _pct == Decimal("1.52")
_casual_after = load("reports/da_casual_after_2026-10-26.json")["final_checks_published"]["casual"]
assert [c_["runs"] for c_ in _casual_after[:2]] == ["3 of 3 OK", "3 of 3 OK"]
assert "44.61" in _casual_after[1]["value"] and "41.25" in _casual_after[1]["value"]
n_hi = sum(1 for r_ in q_act if r_["priority"] == "高")
n_mid = sum(1 for r_ in q_act if r_["priority"] == "中")
assert (n_hi, n_mid) == (4, 3)
s = new_slide(
    k(T_A_QA, "質問と回答"), T_A_QA,
    "デモで入力した質問と、Data Agentの回答の要点です。\n"
    "金額は、元データの集計と照合して確認しました。",
    f"""【話す】本編で使った質問と、日常の言葉で入力した質問の一覧です。回答の金額は、すべて元データの集計と照合しました。
【指す】左の「区分」で、本編の質問①〜④と、追加で確認した質問を分けています。中央が回答の要点、右が元データとの照合結果です。「3回中3回」は、公開済みのData Agentに同じ質問を3回入力して（2026年10月26日）、毎回一致したという意味です。それ以外は、確認した回数が1〜数回です（2026年10月26日〜27日）。
【数字】①実績{oku(ACTUAL)}億円、基準値{oku(BASELINE)}億円、差{fmt(GAP)}億円。②横断混乱{fmt(EV['CROSS_NEG'])}億円（影響額336件）、横断回復{fmt(EV['CROSS_POS'])}億円。追加：金融の子会社は、日本41.25億円、米国44.61億円（年間EBITDA、全額連結）。③食品損失は6契約で{fmt(EV['FOD_NEG'])}億円。④高優先{n_hi}契約、中優先{n_mid}契約。追加：横断混乱は8社すべてに影響し、各社の年間EBITDAの約{MINUS}{PCT_LO.quantize(Decimal('0.1'))}〜{MINUS}{PCT_HI.quantize(Decimal('0.1'))}%。追加：横断混乱は、年間EBITDAの約{MINUS}{_pct}%。
【注意】文面は実行ごとに変わります。優先度の線引きは変わりました。会社別と事業別の回答は、金額は一致しましたが、周辺の説明文に誤りが出た回があります。確認した回数は少なく、性能の評価ではありません。""",
    ["デモ環境での確認（2026年10月26日〜27日、公開済みのData Agent。金額を元データの集計と照合）"],
    takeaway="確認の回数は少なく、文面は実行ごとに変わります。PoCでは、質問と正解を決めて、回数を増やして確かめます。",
    trace=["reports/da_casual_after_2026-10-26.json:final_checks_published",
           "reports/da_traversal_fix_2026-10-27.json:demo_questions", "reports/da_group_wide_2026-10-27.json"])
qa_rows = [
    ("①", "今期のEBITDAって、予算に対してどうだった？",
     f"実績{oku(ACTUAL)}億円、基準値{oku(BASELINE)}億円、差{fmt(GAP)}億円", "一致（3回中3回）"),
    ("②", "一番足を引っ張ったイベントは？\n逆に、一番プラスになったのは？",
     f"横断混乱 {fmt(EV['CROSS_NEG'])}億円（336件）、横断回復 {fmt(EV['CROSS_POS'])}億円", "一致"),
    ("追加", "金融の子会社は今期どうだった？", "日本41.25億円、米国44.61億円（年間EBITDA、全額連結）", "一致（3回中3回）"),
    ("③", "食品の損失は、どの契約に響いたの？", f"6契約、合計{fmt(EV['FOD_NEG'])}億円（食品損失）", "一致"),
    ("④", "いま手を打つべき契約ってどれ？", f"高優先{n_hi}契約（貿易金融）、中優先{n_mid}契約", "金額は一致。優先度は変動"),
    ("追加", "全社に同時に響いたマイナスの出来事は？\n会社ごとにどれくらい影響した？",
     f"横断混乱が8社すべてに影響。各社の年間EBITDAの約{MINUS}{PCT_LO.quantize(Decimal('0.1'))}〜{MINUS}{PCT_HI.quantize(Decimal('0.1'))}%",
     "金額は一致。\n説明文は要確認"),
    ("追加", "このデータで、グループのEBITDAにいちばん\n大きく響いた出来事は？年間の何%くらい？",
     f"横断混乱 {fmt(EV['CROSS_NEG'])}億円、年間EBITDAの約{MINUS}{_pct}%", "一致"),
]
QX = [(.2, .8, "区分"), (1.05, 3.8, "入力した質問"), (4.95, 4.7, "回答の要点"), (9.7, 2.3, "元データとの照合")]
box(s, .6, 2.35, 12.13, 3.9, WHITE, LINE)
for cx, cwid, label in QX:
    text(s, label, .6 + cx, 2.45, cwid, .24, 11.5, TEAL, True, spacing=1.0)
for i, (kind, q_, a_, c_) in enumerate(qa_rows):
    yy = 2.78 + i * .5
    if i % 2:
        box(s, .68, yy - .02, 11.97, .48, PALE, None, radius=.05)
    chip(s, kind, .6 + .2, yy + .1, .62, WHITE if kind != "追加" else INK, TEAL if kind != "追加" else GRAY, 10.5, .26)
    text(s, q_, .6 + 1.05, yy, 3.85, .44, 11.5, NAVY, True, anchor=MIDDLE, spacing=1.15)
    text(s, a_, .6 + 4.95, yy, 4.7, .44, 12, INK, anchor=MIDDLE, spacing=1.2)
    flag = c_.startswith("一致")
    text(s, c_, .6 + 9.7, yy, 2.3, .44, 11, TEAL if flag else CORAL, True, anchor=MIDDLE, spacing=1.15)

# 31 -----------------------------------------------------------------------------------------------
expect(T_A_FAQ)
s = new_slide(
    k(T_A_FAQ, "よくあるご質問"), T_A_FAQ,
    "検討の中で出やすいご質問を、6つにまとめました。\n"
    "回答は、デモでの確認と、Microsoft Learnの記載にもとづきます。",
    """【話す】検討の場で出やすいご質問です。デモで確認できたことと、まだ確認できていないことを分けてお答えします。
【SQLやBIでもできる？】集計の数字は、従来の手段でも出せます（第3章の比較）。Ontologyの狙いは、概念、関係、ルールを一度定義して、質問、利用者、ツールをまたいで使い回せるようにすることです。
【他のデータ基盤は使える？】OneLakeのショートカットやミラーリングで、外部のデータをFabricに参照または複製して取り込める場合があります。対象の基盤、提供状況、ネットワークの条件は、個別に確認が必要です。
【回答は正確？】デモでは、表の金額を元データの集計と照合して、一致しました。言語モデルのため、文面は実行ごとに変わり、説明文に誤りが出た回や、結果が安定しない問い（円高の試算など）もありました。PoCで、照合の方法と合格の基準を決めます。
【権限や秘密度ラベルは？】Microsoft Learnの記載では、結び付けたデータ側の権限は、作成時も問い合わせ時も尊重されます。このデモでは未検証で、コピーして作った表とGraphの権限は別に確認が必要です。秘密度ラベルの扱いも、PoCで、対象のデータごとに確認します。
【作るのは大変？】質問1つに必要な範囲から始める進め方をご提案します。工数は、キーの整備や、統合した表の用意など、データの状態で大きく変わります。
【日本語の質問は？】このデモでは、日本語で入力して、確認した範囲で動作しました。公式のサポート保証ではないため、PoCで確認します。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、how-to-create-data-agent（2026-09-13更新）",
     "デモ環境での確認（2026年10月26日〜27日）"],
    takeaway="ここにないご質問は、PoCの前のワークショップでお受けします。")
faq = [
    ("SQLやBIでもできる？", TEAL,
     "集計の数字は、従来の手段でも出せます。Ontologyは、概念、関係、ルールを一度定義して、質問、利用者、ツールをまたいで使い回せるようにします。"),
    ("他のデータ基盤は使える？", PURPLE,
     "OneLakeのショートカットやミラーリングで、外部のデータをFabricに参照または複製して取り込める場合があります。対象の基盤、提供状況、ネットワークの条件は、個別に確認します。"),
    ("回答は正確？", CORAL,
     "デモでは、表の金額が元データの集計と一致しました。ただし、文面は変わり、説明文に誤りが出た回や、結果が安定しない問いもありました。PoCで、合格の基準を決めます。"),
    ("権限や秘密度ラベルは？", NAVY,
     "Microsoft Learnの記載では、データ側の権限は尊重されます。このデモでは未検証で、コピーした表やGraphの権限、秘密度ラベルの扱いは、PoCで確認します。"),
    ("作るのは大変？", TEAL,
     "質問1つに必要な範囲から始める進め方をご提案します。工数は、キーの整備や統合した表の用意など、データの状態で大きく変わります。"),
    ("日本語の質問は使える？", PURPLE,
     "このデモでは、日本語で入力して、確認した範囲で動作しました。公式のサポート保証ではないため、PoCで確認します。"),
]
for i, (qq, color, aa) in enumerate(faq):
    x = .6 + (i % 3) * 4.09
    y = 2.35 + (i // 3) * 1.99
    box(s, x, y, 3.95, 1.9, WHITE, LINE)
    box(s, x, y, 3.95, .08, color, None, radius=.04)
    text(s, f"Q  {qq}", x + .22, y + .2, 3.55, .3, 14, color, True, spacing=1.0)
    text(s, aa, x + .22, y + .6, 3.55, 1.25, 12, INK, spacing=1.38)

# 32 -----------------------------------------------------------------------------------------------
expect(T_A_GLOSS)
s = new_slide(
    k(T_A_GLOSS, "用語集"), T_A_GLOSS,
    "本資料に出てくる主な用語を、短くまとめました。\n"
    "デモの数字に関する用語も含みます。",
    """【話す】本資料に出てくる主な用語の一覧です。説明の途中で用語が分からなくなったときの参照用です。
【補足】基準値は、デモの設計では、予算に当たる値として扱っています。Data Agentの回答では、「予算」と「基準値」が同じ意味で現れます。全額連結と持分管理は、いずれも管理用の数字で、連結財務諸表の数値ではありません。
【出典】Ontology、概念、関係、ルール、バインディング、Graphの説明は、Microsoft Learnの記載にもとづきます。""",
    ["Microsoft Learn：fabric/iq/ontology/overview（2026-10-16更新）、how-to-use-ontology-graph（2026-09-18更新）、how-to-use-rules（2026-09-15更新）",
     "デモ環境の設計"])
gloss_left = [
    ("Ontology", "業務の概念、関係、ルールを定義して、人とAIで共有する層（Preview）。"),
    ("概念", "業務に出てくる「もの」「こと」の種類。例：会社、契約。"),
    ("関係", "概念どうしのつながり。例：イベントは影響額を生む。"),
    ("ルール", "業務の決まりを文章で定義したもの。Ontologyは実行しない。"),
    ("バインディング", "概念や関係を、データの表や列に結び付けること（結び付け）。"),
    ("Graph", "概念の実例と関係を、点と線で持つ任意の層。経路をたどる問い用。"),
    ("Data Agent", "自然言語の質問に、Fabric内のデータで答えるエージェント。"),
]
gloss_right = [
    ("Lakehouse", "OneLake上で、表（Delta形式）とファイルを保管する場所。"),
    ("ショートカット", "別の場所のデータを、コピーせずに参照する仕組み。"),
    ("ゼロコピー", "データを複製せず、元の場所のデータを参照して使うこと。"),
    ("基準値／実績", "基準値は、イベントの影響を加える前の想定値。実績は、影響を反映した値。"),
    ("全額連結／持分管理", "全額連結は、8社を100%で合算。持分管理は、所有比率を掛けて合算。"),
    ("PoC", "小さな範囲で、実データと質問を使って効果を確かめる検証。"),
    ("Preview", "一般提供の前の段階。仕様や制限が変わる場合がある。"),
]
for col, rows_ in enumerate([gloss_left, gloss_right]):
    x = .6 + col * 6.15
    box(s, x, 2.35, 5.98, 4.55, WHITE, LINE)
    text(s, "用語", x + .2, 2.45, 1.8, .24, 11.5, TEAL, True, spacing=1.0)
    text(s, "意味", x + 2.05, 2.45, 3.0, .24, 11.5, TEAL, True, spacing=1.0)
    yy = 2.8
    for i, (term, meaning) in enumerate(rows_):
        nl = est_lines(meaning, 3.75, 11.5)
        rh = nl * 11.5 * 1.3 / 72 + .15
        if i % 2:
            box(s, x + .08, yy - .03, 5.82, rh, PALE, None, radius=.04)
        text(s, term, x + .2, yy, 1.8, rh - .12, 12, NAVY, True, anchor=MIDDLE, spacing=1.2)
        text(s, meaning, x + 2.05, yy, 3.75, rh - .12, 11.5, INK, anchor=MIDDLE, spacing=1.3)
        yy += rh
    assert yy <= 6.9, (col, yy)
