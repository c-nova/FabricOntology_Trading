"""Generate the portable, identifier-redacted Fabric forecast notebook."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "TradingDemo_04_Ontology_AutoML_予測"


def cell(kind, source, tag):
    item = {"cell_type": kind, "metadata": {"tags": [tag]},
            "source": source.splitlines(keepends=True)}
    if kind == "code":
        item.update(execution_count=None, outputs=[])
    return item


intro = """# STEP 04｜Ontology × AutoMLで次の四半期を予測

架空の8社について、過去92日程度の実績から次の92日のEBITDAを予測します。
現在のOntologyから実体化されたGraphへGQL（beta）を実行し、イベント → 影響額 →
日次指標と影響額 → 取引活動の関係を取得。Lakehouseの金額と照合し、
予測時点までの影響額・経路数をAutoMLの追加特徴量にします。

**3Qで学習、4Qを探索的に評価**し、4Qまでで再学習した次Qの予測も表示。
GraphなしAutoML・直近平均と比べます。将来のイベントや為替の実績は入力しません。
Graphは現在のスナップショットのため、発生日にデータが利用可能だったと仮定します。
1年の合成データ・重複する教師期間では、実世界への一般化や厳密な季節性は検証できません。

結果はこのNotebookの出力に保存します。GraphとLakehouseのデータは変更しません。
「すべて実行」はGraph読み取りとSpark計算を行い、Fabric容量を消費します。
"""
dashboard = """if "html" in globals():
    display(HTML(html))
else:
    print("保存済みの実行結果がない場合は「すべて実行」を選択してください。")
"""
params = f"""EXPECTED_WORKSPACE = "__WORKSPACE_ID__"
ONTOLOGY_NAME = "TradingOntology_Multisector"
NOTEBOOK_NAME = "{NAME}"
"""
notebook = {
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
        "language_info": {"name": "python"},
        "dependencies": {"lakehouse": {
            "default_lakehouse": "__LAKEHOUSE_ID_LH_Group_SAP__",
            "default_lakehouse_workspace_id": "__WORKSPACE_ID__",
            "default_lakehouse_name": "LH_Group_SAP",
            "known_lakehouses": [{"id": "__LAKEHOUSE_ID_LH_Group_SAP__"}],
        }},
    },
    "cells": [
        cell("markdown", intro, "forecast-intro"),
        cell("code", dashboard, "forecast-dashboard"),
        cell("markdown", "## 再実行用のパラメーターと処理\n", "forecast-heading"),
        cell("code", params, "parameters"),
        cell("code", (ROOT / "scripts/forecast_automl_core.py").read_text(), "forecast-core"),
        cell("code", (ROOT / "scripts/forecast_automl_fabric.py").read_text(), "forecast-runtime"),
    ],
}
for index, item in enumerate(notebook["cells"]):
    item["id"] = f"forecast-{index}"
    if item["cell_type"] == "code":
        compile("".join(item["source"]), f"forecast-cell-{index}", "exec")
output = ROOT / "notebooks/TradingDemo_04_Ontology_AutoML.ipynb"
output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")
print(json.dumps({"notebook": output.name, "cells": len(notebook["cells"])}))
