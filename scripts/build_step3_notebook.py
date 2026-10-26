"""Build the new demo-step-3 notebook locally before any Fabric deployment."""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "config/deployment_manifest.json").read_text())
inventory = json.loads((ROOT / "config/lakehouse_inventory.json").read_text())
group = next(x for x in inventory["lakehouses"] if x["displayName"] == "LH_Group_SAP")
NAME = "TradingDemo_03_食品損失のOntology経路とDAG"


def cell(kind, source, tags=None):
    result = {"cell_type": kind, "metadata": {"tags": tags or []},
              "source": source.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


intro = """# STEP 03｜食品損失を、Ontologyの実体経路から読み解く

**DAで損失額 → このNotebookで実体の関係 → 根拠・活動・契約・EBITDA・KPI。**

DA自身に図の描画を求めず、ここで一度だけNotebookに移ります。
下の図は実行日時つきの保存済み結果です。「すべて実行」で現在の
**Ontology由来のマテリアライズ済みGraphModelにGQLを実行**して更新します。
Ontologyモデルそのものへの未提供APIでも、SQL JOINをグラフ照会に見せたものでもありません。
金額だけは別にSparkでDelta DECIMAL値と照合します。データ/Graphは読取専用です。
"""
parameters = f"""EVENT_ID = "FOD_NEG"
PERSIST_OUTPUTS = True
EXPECTED_WORKSPACE = "{manifest['workspace']['id']}"
EXPECTED_ONTOLOGY = "{manifest['ontology']['id']}"
EXPECTED_GRAPH = "{manifest['ontology']['graph_id']}"
ONTOLOGY_NAME = "TradingOntology_Multisector"
APPROVED_NOTEBOOK_NAME = "{NAME}"
"""
dashboard = """from IPython.display import HTML, display
if "DEMO_HTML" in globals():
    display(HTML(DEMO_HTML))
else:
    print("「すべて実行」で実Graphを照会します。初回実行後、この位置に日時つきDAGが保存されます。")
"""
notebook = {
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
        "language_info": {"name": "python"},
        "dependencies": {"lakehouse": {
            "default_lakehouse": group["id"],
            "default_lakehouse_workspace_id": manifest["workspace"]["id"],
            "default_lakehouse_name": "LH_Group_SAP",
            "known_lakehouses": [{"id": group["id"]}],
        }},
    },
    "cells": [
        cell("markdown", intro),
        cell("code", dashboard, ["step3-dashboard"]),
        cell("markdown", "## 再実行用パラメーターと処理\n通常のデモは上の保存済み図で完結します。以下は監査・再実行用です。\n"),
        cell("code", parameters, ["parameters"]),
        cell("code", (ROOT / "scripts/step3_food_loss_runtime.py").read_text(), ["step3-runtime"]),
        cell("markdown", "## 実行監査\nGQLのクエリ・実体ID・金額照合値。認証情報は含めません。\n"),
        cell("code", 'if "AUDIT" in globals():\n    display(AUDIT)\n', ["step3-audit"]),
    ],
}
for index, item in enumerate(notebook["cells"]):
    item["id"] = f"trading-step3-{index}"
    if item["cell_type"] == "code":
        compile("".join(item["source"]), f"step3-cell-{index}", "exec")
encoded = base64.b64encode(json.dumps(notebook, ensure_ascii=False).encode()).decode()
payload = {
    "displayName": NAME, "type": "Notebook",
    "description": "デモ手順3：DAの食品損失額から、実Ontology由来GraphへのGQL照会で根拠・活動・契約・EBITDA・KPIをたどりSVG DAG化。金額は別途DECIMAL照合。",
    "definition": {"format": "ipynb", "parts": [{
        "path": "notebook-content.ipynb", "payload": encoded, "payloadType": "InlineBase64"}]},
}
(ROOT / "notebooks/TradingDemo_03_FoodLoss_Ontology_DAG.ipynb").write_text(
    json.dumps(notebook, ensure_ascii=False, indent=1))
(ROOT / "config/step3_notebook_create.json").write_text(json.dumps(payload, ensure_ascii=False))
print(json.dumps({"name": NAME, "cells": len(notebook["cells"]), "runtime_syntax": "passed"}))
