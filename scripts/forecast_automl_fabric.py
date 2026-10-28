"""Read live Ontology graph and Lakehouse data; save results only in this notebook."""
import base64
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import mlflow
import notebookutils
import pandas as pd
from IPython.display import HTML, display

mlflow.autolog(disable=True)
API = "https://api.fabric.microsoft.com/v1/"
context = notebookutils.runtime.context
workspace_id = context["currentWorkspaceId"]
notebook_id = context["currentNotebookId"]
if workspace_id != EXPECTED_WORKSPACE or context["currentNotebookName"] != NOTEBOOK_NAME:
    raise RuntimeError("Tradingの指定された予測Notebook以外では実行しません。")


def api(path, method="GET", body=None, skill="spark-cli"):
    url = path if path.startswith(API) else API + path
    if not url.startswith(API):
        raise ValueError("Unexpected Fabric API host")
    headers = {
        "Authorization": "Bearer " + notebookutils.credentials.getToken("pbi"),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-ms-fabric-skill": skill,
    }
    request = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(),
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            return (json.loads(data) if data else None,
                    {key.lower(): value for key, value in response.headers.items()})
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Fabric API HTTP {error.code}: 接続・権限・クエリを確認してください。") from error


def list_all(path):
    results = []
    for _ in range(20):
        page, _ = api(path)
        results.extend(page["value"])
        path = page.get("continuationUri")
        if not path:
            if page.get("continuationToken"):
                raise RuntimeError("Catalog pagination is incomplete")
            return results
    raise RuntimeError("Catalog pagination exceeded limit")


def one_named(values, name):
    matches = [item for item in values if item["displayName"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one item named {name}")
    return matches[0]


catalog = list_all(f"workspaces/{workspace_id}/items")
ontology = one_named([item for item in catalog if item["type"] == "Ontology"], ONTOLOGY_NAME)
graph = one_named(
    list_all(f"workspaces/{workspace_id}/graphModels"),
    ONTOLOGY_NAME + "_graph_" + ontology["id"].replace("-", ""),
)
lakehouse = one_named([item for item in catalog if item["type"] == "Lakehouse"], "LH_Group_SAP")
properties, _ = api(f"workspaces/{workspace_id}/lakehouses/{lakehouse['id']}")
schema = properties["properties"].get("defaultSchema")
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "").rstrip("/")
table_root = f"abfss://{workspace_id}@{endpoint}/{lakehouse['id']}/Tables/"
table_root += schema + "/" if schema else ""


def gql(query):
    rows = []
    continuation = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        path = f"workspaces/{workspace_id}/graphModels/{graph['id']}/executeQuery?beta=true"
        if continuation:
            path += "&continuationToken=" + urllib.parse.quote(continuation, safe="")
        response, _ = api(path, "POST", {"query": query}, "fabriciq-ontology-cli")
        code = response["status"]["code"]
        if code not in ("00000", "02000") or response.get("additionalStatuses"):
            raise RuntimeError(f"Graph query failed or warned: {code}")
        rows.extend(response.get("result", {}).get("data", []))
        continuation = response.get("result", {}).get("nextPage")
        if not continuation:
            if not rows:
                raise RuntimeError("Graph returned no rows; no static fallback is allowed")
            return rows
        time.sleep(2)
    raise TimeoutError("Graph pagination exceeded 180 seconds")


events = gql("""
MATCH (e:RiskEvent)
RETURN e.event_id AS event_id, e.start_date AS event_start_date
ORDER BY e.event_id LIMIT 200
""".strip())
if len(events) >= 200:
    raise RuntimeError("Graph event query reached its limit")
paths = []
for event in events:
    event_id = event["event_id"]
    if not re.fullmatch(r"[A-Z0-9_]{1,40}", event_id):
        raise ValueError("Unexpected event ID")
    rows = gql(f"""
MATCH (e:RiskEvent)-[:EventHasEffect]->(f:FinancialEffect)
      -[:EffectRealizedInMetric]->(m:FinancialMetric),
      (f)-[:EffectOnActivity]->(a:Activity)
WHERE e.event_id='{event_id}' AND m.metric_code='EBITDA' AND m.scenario_tag='actual'
RETURN e.event_id AS event_id, e.start_date AS event_start_date,
       f.effect_id AS effect_id, a.entity_id AS entity_id, m.metric_id AS metric_id
ORDER BY f.effect_id LIMIT 1000
""".strip())
    if len(rows) >= 1000:
        raise RuntimeError("Graph path query reached its limit")
    paths.extend(rows)


def source(table, columns):
    return spark.read.format("delta").load(table_root + table).select(*columns).toPandas()


metrics = source("semantic_financial_metrics_daily",
                 ["metric_id", "metric_date", "entity_id", "metric_code", "scenario_tag", "amount_group"])
effects = source("semantic_event_financial_effects",
                 ["effect_id", "event_id", "entity_id", "effect_date", "delta_ebitda_full_jpy"])
links = source("semantic_effect_metric_links", ["effect_id", "metric_id"])
event_source = source("semantic_risk_events", ["event_id", "start_date"])
graph_events = pd.DataFrame(events)
graph_events["event_start_date"] = pd.to_datetime(graph_events["event_start_date"], utc=True).dt.tz_localize(None).dt.normalize()
event_source["start_date"] = pd.to_datetime(event_source["start_date"]).dt.normalize()
checked = graph_events.merge(event_source, on="event_id", validate="one_to_one")
if len(checked) != len(graph_events) or len(checked) != len(event_source):
    raise ValueError("Graph/Lakehouse event membership differs")
if not (checked["event_start_date"] == checked["start_date"]).all():
    raise ValueError("Graph/Lakehouse event dates differ")
graph_paths = pd.DataFrame(paths)
graph_paths["event_start_date"] = pd.to_datetime(graph_paths["event_start_date"], utc=True).dt.tz_localize(None)
frame, base_columns, audit = prepare_features(metrics, effects, links, graph_paths)
report = run_comparison(frame, base_columns, time_budget=20)
report["source"] = audit
report["graph_event_count"] = len(events)
report["graph_api"] = "Ontology Graph GQL beta"
report["executed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
report["assumptions"] = [
    "合成データ。為替は過去のECB実績。",
    "Graphの現在のスナップショットを利用。イベント開始日と影響日を利用可能日時と仮定し、厳密な過去時点の公開履歴は未検証。",
    "各予測時点より後のイベント、影響額、為替実績を特徴量に使わない。",
    "四半期の観測は1回、Q4は既に閲覧済み。差は探索的で一般化・因果を示さない。",
    "教師データの92日間は週ごとに重複する。独立した観測数ではない。",
    "予測値の精度保証なし。将来の為替と未知イベントは予測していない。",
]


def render(report):
    lines = []
    for row in report["results"]:
        lines.append(
            "<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{:+.2f}</td>"
            "<td>{:+.2f}%</td><td>{:.2f}</td></tr>".format(
                row["model"], row["q4_forecast_oku"], row["q4_actual_oku"],
                row["q4_error_oku"], row["q4_error_percent"], row["next_q_forecast_oku"],
            )
        )
    model_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{:.3f}</td><td>{}</td><td>{}</td></tr>".format(
            item["model"], item["best_estimator"], item["validation"]["validation_mae_company_oku"],
            item["q4_training_rows"], item["future_training_rows"],
        ) for item in report["models"]
    )
    notes = "".join("<li>" + value + "</li>" for value in report["assumptions"])
    return f"""
<div style="font-family:Arial,'Yu Gothic',sans-serif;max-width:1100px;color:#1b2940;line-height:1.55">
<h2>Ontology × AutoML｜次の四半期のEBITDA予測</h2>
<p>実Graphでイベント → 影響額 → 日次指標、および影響額 → 取引活動の関係を取得。
Lakehouseから金額を読み、予測はFLAMLが実施。Graph {report['source']['graph_paths']:,}経路を照合。</p>
<p><b>単位：億円</b>。Q4は2026年7〜9月。次の四半期は2026年10〜12月。
8社の92日予測を合算した全額ベース。</p>
<table style="border-collapse:collapse;width:100%" border="1" cellpadding="8">
<tr><th>方法</th><th>Q4予測</th><th>Q4実績</th><th>差額</th><th>誤差</th><th>次の四半期予測</th></tr>
{''.join(lines)}</table>
<h3>モデル選定と学習行</h3>
<p>2026-03-30を予測起点とする92日先（3Qまで）で選定。評価用Q4と重ならないよう、
その選定時の学習ラベルは起点以前に終了。特徴量あり・なしは同じ検索条件。</p>
<table style="border-collapse:collapse;width:100%" border="1" cellpadding="8">
<tr><th>方法</th><th>選択されたモデル</th><th>選定時の会社別MAE（億円）</th><th>Q4予測学習行</th><th>次Q予測学習行</th></tr>
{model_rows}</table>
<h3>前提と限界</h3><ul>{notes}</ul>
<p>実行UTC: {report['executed_at_utc']}。OntologyとLakehouseは読取専用、結果はこのNotebookに保存。</p>
</div>
"""


html = render(report)
display(HTML(html))


def lro(path, body):
    data, headers = api(path, "POST", body)
    operation = headers.get("x-ms-operation-id")
    if not operation:
        return data
    for _ in range(60):
        time.sleep(2)
        state, _ = api("operations/" + operation)
        if state["status"] == "Succeeded":
            if path.endswith("getDefinition?format=ipynb"):
                return api("operations/" + operation + "/result")[0]
            return state
        if state["status"] in ("Failed", "Cancelled"):
            raise RuntimeError("Notebook persistence failed: " + state["status"])
    raise TimeoutError("Notebook persistence exceeded 120 seconds")


saved = lro(f"workspaces/{workspace_id}/notebooks/{notebook_id}/getDefinition?format=ipynb", {})
part = next(part for part in saved["definition"]["parts"] if part["path"].endswith(".ipynb"))
nb = json.loads(base64.b64decode(part["payload"]))
dashboard = next(cell for cell in nb["cells"] if "forecast-dashboard" in cell["metadata"].get("tags", []))
dashboard["outputs"] = [{
    "output_type": "display_data", "metadata": {},
    "data": {"text/html": [html], "text/plain": ["Ontology × AutoML: saved live result"]},
}]
nb["metadata"]["trading_forecast"] = {"latest_live_report": report}
content = base64.b64encode(json.dumps(nb, ensure_ascii=False).encode()).decode()
lro(f"workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition", {
    "definition": {"format": "ipynb", "parts": [{
        "path": "notebook-content.ipynb", "payloadType": "InlineBase64", "payload": content,
    }]}
})
print(json.dumps(report, ensure_ascii=False))
