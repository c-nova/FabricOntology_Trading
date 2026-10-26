"""Fabric notebook runtime: live ontology-backed GQL paths, exact crosscheck, SVG."""
import base64
import datetime as dt
from decimal import Decimal
from html import escape
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import notebookutils
from IPython.display import HTML, display
from pyspark.sql import functions as F

API = "https://api.fabric.microsoft.com/v1/"
context = notebookutils.runtime.context
workspace_id = context["currentWorkspaceId"]
notebook_id = context["currentNotebookId"]
if EVENT_ID != "FOD_NEG":
    raise ValueError("この食品損失デモは EVENT_ID='FOD_NEG' 専用です。別事例を食品として描画しません。")
if workspace_id != EXPECTED_WORKSPACE:
    raise RuntimeError("Trading workspace以外では実行しません。")


def api(path, method="GET", body=None, skill="spark-cli"):
    url = path if path.startswith(API) else API + path
    if not url.startswith(API):
        raise RuntimeError("Unexpected API host")
    headers = {
        "Authorization": "Bearer " + notebookutils.credentials.getToken("pbi"),
        "Content-Type": "application/json", "Accept": "application/json",
        "x-ms-fabric-skill": skill,
    }
    request = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(),
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read()
            return (json.loads(content) if content else None,
                    {k.lower(): v for k, v in response.headers.items()})
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Fabric HTTP {error.code}: 認証・権限・API構成を確認してください。静的図には代替しません。"
        ) from None


def items(path):
    result = []
    for _ in range(20):
        page, _ = api(path)
        result.extend(page["value"])
        path = page.get("continuationUri")
        if not path:
            if page.get("continuationToken"):
                raise RuntimeError("Unresolved catalog pagination")
            return result
    raise RuntimeError("Catalog pagination exceeded limit")


def exactly_one(values, name):
    matches = [x for x in values if x["displayName"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one item: {name}")
    return matches[0]


catalog = items(f"workspaces/{workspace_id}/items")
ontology = exactly_one([x for x in catalog if x["type"] == "Ontology"], ONTOLOGY_NAME)
graph = exactly_one(items(f"workspaces/{workspace_id}/graphModels"),
                    ONTOLOGY_NAME + "_graph_" + ontology["id"].replace("-", ""))
lakehouse = exactly_one([x for x in catalog if x["type"] == "Lakehouse"], "LH_Group_SAP")
assert ontology["id"] == EXPECTED_ONTOLOGY and graph["id"] == EXPECTED_GRAPH
properties, _ = api(f"workspaces/{workspace_id}/lakehouses/{lakehouse['id']}")
schema = properties["properties"].get("defaultSchema")
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "").rstrip("/")
table_root = f"abfss://{workspace_id}@{endpoint}/{lakehouse['id']}/Tables/"
table_root += schema + "/" if schema else ""

graph_audit = []


def gql(query):
    rows, continuation = [], None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        path = f"workspaces/{workspace_id}/graphModels/{graph['id']}/executeQuery?beta=true"
        if continuation:
            path += "&continuationToken=" + urllib.parse.quote(continuation, safe="")
        result, _ = api(path, "POST", {"query": query}, "fabriciq-ontology-cli")
        status = result["status"]["code"]
        if status not in ("00000", "02000") or result.get("additionalStatuses"):
            raise RuntimeError(f"GQL failed or warned: {status}; static fallback disabled")
        rows.extend(result.get("result", {}).get("data", []))
        continuation = result.get("result", {}).get("nextPage")
        if not continuation:
            if not rows:
                raise RuntimeError("Live GQL returned no instances; no diagram generated")
            graph_audit.append({"query": query, "status": status, "rows": len(rows)})
            return rows
        time.sleep(2)
    raise TimeoutError("GQL continuation exceeded 180 seconds")


PATH_QUERY = """
MATCH (e:RiskEvent)-[:EventHasEffect]->(f:FinancialEffect)
      -[:EffectRealizedInMetric]->(m:FinancialMetric)
      -[:MetricRollsUpToGroupKPI]->(k:GroupKPI),
      (f)-[:EffectOnActivity]->(a:Activity)-[:ActivityUnderContract]->(c:Contract),
      (f)-[:EffectOnContract]->(c),
      (f)-[:EffectExplainedByEvidence]->(v:Evidence)-[:EvidenceSupportsEvent]->(e),
      (e)-[:EventImpactsActivity]->(a)
WHERE e.event_id='FOD_NEG'
  AND m.metric_code='EBITDA' AND m.scenario_tag='actual'
  AND k.kpi_code='EBITDA_FULL_CONSOLIDATED' AND k.scenario_tag='actual'
RETURN e.event_id AS event_id, e.narrative AS narrative,
       e.is_synthetic AS event_is_synthetic, v.evidence_id AS evidence_id,
       v.source_record AS source_record, v.excerpt AS excerpt,
       v.is_synthetic AS evidence_is_synthetic,
       a.activity_id AS activity_id, a.activity_type AS activity_type,
       a.activity_date AS activity_date, a.entity_id AS entity_id,
       c.contract_id AS contract_id, c.commodity AS commodity,
       f.effect_id AS effect_id, f.effect_date AS effect_date,
       f.delta_ebitda_full_jpy AS graph_effect_jpy,
       f.delta_management_jpy AS graph_management_jpy,
       m.metric_id AS metric_id, k.kpi_id AS kpi_id
ORDER BY f.effect_id LIMIT 1000
""".strip()
path_rows = gql(PATH_QUERY)
if len(path_rows) >= 1000:
    raise RuntimeError("Path limit reached; refusing a potentially incomplete total")
unique_paths = {}
for row in path_rows:
    prior = unique_paths.setdefault(row["effect_id"], row)
    assert prior["graph_effect_jpy"] == row["graph_effect_jpy"]
    assert prior["graph_management_jpy"] == row["graph_management_jpy"]
representative = unique_paths[min(unique_paths)]
assert representative["event_is_synthetic"] and representative["evidence_is_synthetic"]
activity_id = representative["activity_id"]
assert re.fullmatch(r"[A-Za-z0-9_]+", activity_id)
country = representative["entity_id"].split("_")[2]
extension_type = "Foods" + country + "Extension"
extension_relation = extension_type + "ForActivity"
EXTENSION_QUERY = f"""
MATCH (x:{extension_type})-[:{extension_relation}]->(a:Activity)
WHERE a.activity_id='{activity_id}'
RETURN x.extension_id AS extension_id, x.temperature_c AS temperature_c,
       x.spoilage_percent AS spoilage_percent, x.observation_date AS observation_date
LIMIT 2
""".strip()
observations = gql(EXTENSION_QUERY)
if len(observations) != 1:
    raise RuntimeError("Representative activity needs exactly one live cold-chain observation")
observation = observations[0]

# These independent DECIMAL reads check money, not graph relationships.
effects = spark.read.format("delta").load(
    table_root + "semantic_event_financial_effects").where(F.col("event_id") == EVENT_ID).collect()
effect_by_id = {x["effect_id"]: x.asDict() for x in effects}
assert len(effects) == len(effect_by_id) == 84
assert set(effect_by_id) == set(unique_paths), "Graph/Spark effect membership differs"
for effect_id, row in unique_paths.items():
    exact = effect_by_id[effect_id]
    assert Decimal(str(row["graph_effect_jpy"])).quantize(Decimal(".01")) == exact["delta_ebitda_full_jpy"]
    assert Decimal(str(row["graph_management_jpy"])).quantize(Decimal(".01")) == exact["delta_management_jpy"]
full = sum((x["delta_ebitda_full_jpy"] for x in effect_by_id.values()), Decimal(0))
weighted = sum((x["delta_management_jpy"] for x in effect_by_id.values()), Decimal(0))
assert full == Decimal("-114461186.25") and weighted == Decimal("-87630294.31")
effect = effect_by_id[representative["effect_id"]]
metric_rows = spark.read.format("delta").load(
    table_root + "semantic_financial_metrics_daily").where(
        F.col("metric_id") == representative["metric_id"]).collect()
kpi_rows = spark.read.format("delta").load(table_root + "kpi_snapshot").where(
    F.col("kpi_id") == representative["kpi_id"]).collect()
assert len(metric_rows) == len(kpi_rows) == 1
metric, kpi = metric_rows[0].asDict(), kpi_rows[0].asDict()
assert metric["metric_code"] == "EBITDA" and metric["scenario_tag"] == "actual"
assert kpi["kpi_code"] == "EBITDA_FULL_CONSOLIDATED" and kpi["scenario_tag"] == "actual"
assert metric["entity_id"] == effect["entity_id"]
assert str(metric["metric_date"]) == str(kpi["kpi_date"]) == str(effect["effect_date"])


def yen(amount):
    return f"{Decimal(str(amount)):,.2f} 円"


def oku(amount):
    return f"{Decimal(str(amount)) / Decimal(100000000):+.4f} 億円"


def esc(value):
    return escape(str(value), quote=True)


day = str(effect["effect_date"])
nodes = {
    "evidence": ("根拠記録", "架空の業務ログ", "SIM:// 原記録を下表で確認",
                 representative["evidence_id"], 20, 85, "#64748b"),
    "event": ("食品の損失イベント", EVENT_ID, "コールドチェーン損耗（架空）",
              EVENT_ID, 325, 85, "#8b5cf6"),
    "effect": ("代表1効果の配賦", yen(effect["delta_ebitda_full_jpy"]),
               "EBITDA差分 / 84効果のうち1件", effect["effect_id"], 630, 85, "#dc4960"),
    "metric": ("子会社の日次EBITDA", yen(metric["amount_group"]),
               day + " / actual総額", metric["metric_id"], 935, 85, "#0d9488"),
    "cold": ("食品の観測記録", f"{observation['temperature_c']:g} °C",
             f"廃棄率 {observation['spoilage_percent']:g}%（記録値）",
             observation["extension_id"], 20, 370, "#64748b"),
    "activity": ("対象となる販売活動", "食品の外部販売 / 1活動",
                 day, activity_id, 325, 370, "#64748b"),
    "contract": ("活動が属する契約", "製粉用小麦",
                 representative["commodity"], representative["contract_id"], 630, 370, "#64748b"),
    "kpi": ("全社の日次EBITDA", yen(kpi["amount_group"]),
            day + " / 全8社actual総額", kpi["kpi_id"], 935, 370, "#0d9488"),
}
edges = [
    ("evidence", "event", "EvidenceSupportsEvent", "根拠として関連", "association"),
    ("event", "effect", "EventHasEffect", "設計上の損失配賦", "attribution"),
    ("effect", "metric", "EffectRealizedInMetric", "日次指標に対応", "aggregation"),
    ("metric", "kpi", "MetricRollsUpToGroupKPI", "全社の集約先", "aggregation"),
    ("effect", "activity", "EffectOnActivity", "影響対象の活動", "association"),
    ("cold", "activity", extension_relation, "活動の観測", "association"),
    ("activity", "contract", "ActivityUnderContract", "契約に属する", "association"),
]
assert len(nodes) == 8 and len(edges) == 7
seen, remaining = set(), set(nodes)
while remaining:
    ready = {n for n in remaining if all(s in seen for s, t, *_ in edges if t == n)}
    assert ready, "The displayed relationship subset must be a DAG"
    seen.update(ready)
    remaining -= ready
colors = {"association": "#7c8b9f", "attribution": "#8b5cf6", "aggregation": "#0d9488"}
svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1190 530" '
       'role="img" aria-label="食品損失の実Ontology由来グラフ経路、8ノードのDAG">', "<defs>"]
for kind, color in colors.items():
    svg.append(f'<marker id="arr-{kind}" viewBox="0 0 10 10" refX="9" refY="5" '
               f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
               f'<path d="M0 0L10 5L0 10Z" fill="{color}"/></marker>')
svg.append('</defs><rect width="1190" height="530" rx="18" fill="#f6f8fc"/>')
svg.append('<text x="26" y="35" font-size="17" font-weight="700" fill="#334155">'
           '実体の関係をたどる：金額の大きさ → 根拠・活動・契約 → 指標・KPI</text>')
routes = {
    ("effect", "activity"): ("M742 200 C742 290 437 280 437 368", 570, 278),
    ("metric", "kpi"): ("M1047 200 L1047 368", 1047, 280),
}
for source, target, relation, label, kind in edges:
    if (source, target) in routes:
        path, tx, ty = routes[source, target]
    else:
        sx, sy, tx_node, ty_node = nodes[source][4], nodes[source][5], nodes[target][4], nodes[target][5]
        path = f"M{sx+225} {sy+57} L{tx_node-3} {ty_node+57}"
        tx, ty = (sx + 225 + tx_node) / 2, sy + 35
    dash = 'stroke-dasharray="5 4"' if kind == "association" else ""
    svg.append(f'<path d="{path}" fill="none" stroke="{colors[kind]}" stroke-width="2.6" '
               f'{dash} marker-end="url(#arr-{kind})"><title>{esc(relation)}</title></path>')
    svg.append(f'<text x="{tx}" y="{ty}" text-anchor="middle" fill="{colors[kind]}" '
               f'font-size="13" font-weight="600">{esc(label)}</text>')
for label, value, subtitle, full_id, x, y, color in nodes.values():
    svg.append(f'<g><title>{esc(full_id)}</title>'
               f'<rect x="{x+2}" y="{y+4}" width="225" height="115" rx="14" fill="#e5eaf3"/>'
               f'<rect x="{x}" y="{y}" width="225" height="115" rx="14" fill="white" stroke="#dbe2ef"/>'
               f'<rect x="{x}" y="{y+16}" width="4" height="82" rx="2" fill="{color}"/>'
               f'<text x="{x+16}" y="{y+29}" fill="{color}" font-size="16" font-weight="700">{esc(label)}</text>'
               f'<text x="{x+16}" y="{y+60}" fill="#172b4d" font-size="17" font-weight="700">{esc(value)}</text>'
               f'<text x="{x+16}" y="{y+90}" fill="#64748b" font-size="12.5">{esc(subtitle)}</text></g>')
svg.append("</svg>")
DEMO_SVG = "".join(svg)
read_at = dt.datetime.now(dt.timezone.utc).isoformat()
cards = [
    ("イベント全体 / 84効果を一度だけ合計", oku(full), yen(full),
     "持分管理寄与 " + yen(weighted), "#c43e57"),
    ("代表する1活動・1効果の差分", oku(effect["delta_ebitda_full_jpy"]),
     yen(effect["delta_ebitda_full_jpy"]),
     f"所有比率 {effect['ownership_ratio'] * 100:.0f}% / " + day, "#6d55c6"),
    ("同日の全社EBITDA / actual総額", oku(kpi["amount_group"]),
     yen(kpi["amount_group"]), "損失差分ではなく、全8社の日次総額", "#087f8c"),
]
card_html = "".join(
    f'<div class="kcard" style="border-top:4px solid {color}"><div class="eyebrow">{esc(label)}</div>'
    f'<div class="kvalue" style="color:{color}">{esc(big)}</div><strong>{esc(amount)}</strong>'
    f'<div class="muted">{esc(note)}</div></div>' for label, big, amount, note, color in cards)
lineage = "".join(
    f"<tr><td>{esc(n[0])}</td><td><code>{esc(n[3])}</code></td></tr>" for n in nodes.values())
relations = "".join(
    f"<tr><td>{esc(nodes[s][0])} → {esc(nodes[t][0])}</td><td><code>{esc(r)}</code></td>"
    f"<td>{esc(label)}</td></tr>" for s, t, r, label, _ in edges)
extra = [
    ("代表1効果 → 根拠記録", "EffectExplainedByEvidence"),
    ("代表1効果 → 契約", "EffectOnContract"),
    ("食品イベント → 対象活動", "EventImpactsActivity"),
]
relations += "".join(
    f"<tr><td>{esc(label)}</td><td><code>{esc(relation)}</code></td>"
    "<td>取得済み・図では省略</td></tr>" for label, relation in extra)
DEMO_HTML = f"""
<div class="trading-step3">
<style>
.trading-step3{{font-family:"Yu Gothic","Meiryo","Noto Sans JP",sans-serif;color:#26364d;max-width:1320px;line-height:1.65}}
.trading-step3 .hero{{background:linear-gradient(110deg,#14233f,#274777);color:white;padding:26px 30px;border-radius:18px;margin-bottom:18px}}
.trading-step3 h2{{font-size:25px;margin:4px 0 8px;color:inherit}}
.trading-step3 .eyebrow{{font-size:13px;font-weight:600;letter-spacing:.04em}}
.trading-step3 .cards{{display:flex;flex-wrap:wrap;gap:14px;margin:16px 0}}
.trading-step3 .kcard{{flex:1;min-width:240px;background:#f8fafc;border:1px solid #dfe6ef;border-radius:12px;padding:17px}}
.trading-step3 .kvalue{{font-size:27px;font-weight:800;margin:7px 0}}
.trading-step3 .muted{{font-size:12px;color:#67788e;margin-top:7px}}
.trading-step3 .note{{padding:12px 16px;background:#edf5fb;border-left:4px solid #5397ba;border-radius:6px;margin:14px 0}}
.trading-step3 svg{{width:100%;height:auto;font-family:"Yu Gothic","Meiryo","Noto Sans JP",sans-serif}}
.trading-step3 table{{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0 20px}}
.trading-step3 td,.trading-step3 th{{padding:9px 12px;border-bottom:1px solid #e1e8f1;text-align:left;overflow-wrap:anywhere}}
.trading-step3 th{{background:#edf2f8}}
.trading-step3 code{{font-size:12px;white-space:normal;overflow-wrap:anywhere}}
.trading-step3 .legend{{display:flex;gap:24px;flex-wrap:wrap;font-size:13px;margin:8px 0 15px}}
.trading-step3 summary{{cursor:pointer;font-weight:700;padding:10px 0}}
</style>
<div class="hero"><div class="eyebrow">TRADING DEMO · STEP 03 · LIVE GQL → INSTANCE PATH → DAG</div>
<h2>食品の損失は、どの根拠・活動から来たのか</h2>
DAで「損失の大きさ」を確認した後、ここで同じOntology由来の実体グラフをたどります。<br>
<span style="font-size:13px;color:#c5d8f1">FOD_NEG / 2025-10-01〜2026-09-30 / JPY / 読取専用</span></div>
<div class="cards">{card_html}</div>
<div class="note"><b>実際に照会したもの：</b>OntologyからマテリアライズされたGraphModelへ
GQLを実行し、84個の効果と実在の経路を取得。図の関係線はSQL JOINから作っていません。
<br><b>金額は別に照合：</b>元のDelta DECIMAL値をSparkで読み取り、effect_idごとに一度だけ合計。
Graphの浮動小数値とも全84効果で小数点以下2桁まで一致しました。</div>
{DEMO_SVG}
<div class="legend"><span style="color:#8b5cf6">━ 設計上の影響配賦</span>
<span style="color:#7c8b9f">┄ 記録・対象・契約の関連</span>
<span style="color:#0d9488">━ 指標への対応・集約先</span></div>
<div class="note"><b>読み方：</b>これは1活動を代表例にした、取得関係の非循環な部分図です。
1効果の差分、子会社の日次総額、全社の日次総額は別粒度です。図の金額同士を足し算しません。
イベント全体の損失は84効果の重複なし合計です。</div>
<h3>根拠記録（原文）</h3>
<p>{esc(representative['excerpt'])}<br><code>{esc(representative['source_record'])}</code></p>
<p class="muted">温度 {esc(observation['temperature_c'])}°C・廃棄率 {esc(observation['spoilage_percent'])}% は架空の観測値です。
記録のない許容温度・閾値超過・実世界の腐敗原因は推定しません。商品コードも原記録のままです。</p>
<details open><summary>実体のIDとデータリネージ（長いIDは図から分離）</summary>
<table><thead><tr><th>実体</th><th>GQLで得たID</th></tr></thead><tbody>{lineage}</tbody></table></details>
<details><summary>照会した本物の関係名・GQL・接続先</summary>
<table><thead><tr><th>向き</th><th>Graph関係型</th><th>意味</th></tr></thead><tbody>{relations}</tbody></table>
<p>Ontology <code>{ontology['id']}</code><br>GraphModel <code>{graph['id']}</code></p>
<pre style="white-space:pre-wrap;font-size:12px">{esc(PATH_QUERY)}</pre>
<pre style="white-space:pre-wrap;font-size:12px">{esc(EXTENSION_QUERY)}</pre></details>
<p class="muted">架空デモの設計上の配賦・根拠リンクであり、実世界の因果証明ではありません。
持分管理寄与は法定連結EBITDAではありません。Graph APIはbetaです。</p>
<p class="muted">保存済み実行結果 / GQL読取UTC: {esc(read_at)} /
再実行すると現在のGraphを読み直します。認証・空結果・照合不一致時はエラーで停止します。</p></div>
"""
AUDIT = {
    "version": 1, "status": "passed", "event_id": EVENT_ID,
    "workspace_id": workspace_id, "ontology_id": ontology["id"], "graph_id": graph["id"],
    "notebook_id": notebook_id, "live_graph_read_at_utc": read_at,
    "graph_api": API + f"workspaces/{workspace_id}/graphModels/{graph['id']}/executeQuery?beta=true",
    "graph_queries": graph_audit, "returned_path_rows": len(path_rows),
    "unique_event_effects": len(unique_paths), "graph_effect_ids": sorted(unique_paths),
    "exact_full_event_jpy": str(full), "exact_management_event_jpy": str(weighted),
    "representative_path": representative, "cold_chain_observation": observation,
    "exact_representative_effect_jpy": str(effect["delta_ebitda_full_jpy"]),
    "exact_subsidiary_daily_actual_ebitda_jpy": str(metric["amount_group"]),
    "exact_group_daily_actual_ebitda_jpy": str(kpi["amount_group"]),
    "delta_financial_crosscheck_tables": [
        table_root + x for x in ("semantic_event_financial_effects",
                                 "semantic_financial_metrics_daily", "kpi_snapshot")],
    "diagram_nodes": len(nodes), "diagram_edges": len(edges), "dag_checked": True,
    "diagram_relations": [{"source": s, "target": t, "relation": r, "semantic_kind": kind}
                         for s, t, r, _, kind in edges],
    "graph_read_only": True, "source_data_read_only": True,
    "browser_credentials_embedded": False, "static_fallback": False,
}
display(HTML(DEMO_HTML))


def lro(path, body):
    data, headers = api(path, "POST", body)
    operation = headers.get("x-ms-operation-id")
    if not operation:
        return data
    for _ in range(60):
        time.sleep(2)
        state, _ = api("operations/" + operation)
        if state["status"] == "Succeeded":
            return api("operations/" + operation + "/result")[0] if path.endswith("getDefinition?format=ipynb") else state
        if state["status"] in ("Failed", "Cancelled"):
            raise RuntimeError("Notebook snapshot persistence failed: " + state["status"])
    raise TimeoutError("Notebook snapshot persistence exceeded 120 seconds")


if PERSIST_OUTPUTS:
    if context["currentNotebookName"] != APPROVED_NOTEBOOK_NAME:
        raise RuntimeError("Refusing to save outputs into any notebook other than the new step-3 notebook")
    current = lro(f"workspaces/{workspace_id}/notebooks/{notebook_id}/getDefinition?format=ipynb", {})
    part = next(p for p in current["definition"]["parts"] if p["path"].endswith(".ipynb"))
    saved = json.loads(base64.b64decode(part["payload"]))
    dashboard = next(c for c in saved["cells"] if c["metadata"].get("tags") == ["step3-dashboard"])
    dashboard["execution_count"] = None
    dashboard["outputs"] = [{
        "output_type": "display_data", "metadata": {},
        "data": {"text/html": [DEMO_HTML],
                 "text/plain": ["実行済みOntology由来の食品損失DAG / " + read_at]},
    }]
    audit_cell = next(c for c in saved["cells"] if c["metadata"].get("tags") == ["step3-audit"])
    audit_cell["execution_count"] = None
    audit_cell["outputs"] = [{
        "output_type": "display_data", "metadata": {},
        "data": {"application/json": AUDIT, "text/plain": [json.dumps(AUDIT, ensure_ascii=False)]},
    }]
    saved["metadata"]["trading_step3"] = {"latest_live_audit": AUDIT}
    content = base64.b64encode(json.dumps(saved, ensure_ascii=False).encode()).decode()
    lro(f"workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition", {
        "definition": {"format": "ipynb", "parts": [{
            "path": "notebook-content.ipynb", "payloadType": "InlineBase64", "payload": content}]}})
    print("Live GQL paths + exact DECIMAL checks passed; visible HTML/SVG snapshot saved into this new notebook.")
print(json.dumps(AUDIT, ensure_ascii=False))
