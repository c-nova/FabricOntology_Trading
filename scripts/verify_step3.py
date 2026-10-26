"""Validate actual step-3 job, persisted output, graph audit and reopened UI evidence."""
import base64
from decimal import Decimal
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


job = load("reports/step3_job.json")
assert job["status"] == "Completed" and job["failureReason"] is None
parts = load("reports/step3_notebook_readback.json")["definition"]["parts"]
part = next(p for p in parts if p["path"].endswith(".ipynb"))
nb = json.loads(base64.b64decode(part["payload"]))
audit = nb["metadata"]["trading_step3"]["latest_live_audit"]
assert audit == load("reports/step3_live_audit.json")
assert audit["notebook_id"] == job["itemId"]
assert audit["status"] == "passed" and audit["unique_event_effects"] == 84
assert [q["status"] for q in audit["graph_queries"]] == ["00000", "00000"]
assert [q["rows"] for q in audit["graph_queries"]] == [84, 1]
assert "?beta=true" in audit["graph_api"]
assert audit["source_data_read_only"] and audit["graph_read_only"]
assert not audit["browser_credentials_embedded"] and not audit["static_fallback"]
data = load("data/demo_dataset.json")["LH_Group_SAP"]
effects = [x for x in data["semantic_event_financial_effects"] if x["event_id"] == "FOD_NEG"]
assert set(audit["graph_effect_ids"]) == {x["effect_id"] for x in effects}
for column, total in (("delta_ebitda_full_jpy", "exact_full_event_jpy"),
                      ("delta_management_jpy", "exact_management_event_jpy")):
    assert sum((Decimal(x[column]) for x in effects), Decimal(0)) == Decimal(audit[total])
representative = audit["representative_path"]
effect = next(x for x in effects if x["effect_id"] == representative["effect_id"])
assert Decimal(effect["delta_ebitda_full_jpy"]) == Decimal(audit["exact_representative_effect_jpy"])
assert effect["activity_id"] == representative["activity_id"]
assert effect["evidence_id"] == representative["evidence_id"]
assert effect["contract_id"] == representative["contract_id"]
assert Decimal(audit["exact_full_event_jpy"]) != Decimal(audit["exact_representative_effect_jpy"])
assert Decimal(audit["exact_group_daily_actual_ebitda_jpy"]) > 0

dashboard = next(c for c in nb["cells"] if c["metadata"].get("tags") == ["step3-dashboard"])
html = "".join(dashboard["outputs"][0]["data"]["text/html"])
svg = ET.fromstring(re.search(r"<svg\b.*?</svg>", html, re.S).group(0))
ns = {"s": "http://www.w3.org/2000/svg"}
assert len(svg.findall("s:g", ns)) == 8
assert len([p for p in svg.findall("s:path", ns) if p.get("marker-end")]) == 7
assert len(audit["diagram_relations"]) == 7 and audit["dag_checked"]
assert "-114,461,186.25 円" in html and "113,069,201.90 円" in html
assert "閾値超過" in html and "保存済み実行結果" in html
assert "<script" not in html.lower() and "<iframe" not in html.lower()
for cell in nb["cells"]:
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), "persisted-step3-cell", "exec")
runtime = next(c for c in nb["cells"] if c["metadata"].get("tags") == ["step3-runtime"])
assert "".join(runtime["source"]) == (ROOT / "scripts/step3_food_loss_runtime.py").read_text()
ui = load("reports/step3_ui_verification.json")
assert ui["dashboard_visible"] and ui["dashboard_in_actual_notebook_output_iframe"]
assert ui["svg_nodes"] == 8 and ui["svg_arrow_paths"] == 7 and not ui["node_label_overflow"]
assert ui["exact_event_amount_visible"] and ui["snapshot_timestamp_visible"]
print(json.dumps({"status": "passed", "job_id": job["id"], "real_gql_queries": 2,
                  "unique_effects": 84, "nodes": 8, "edges": 7,
                  "persisted_outputs": True, "reopened_visible_svg": True}))
