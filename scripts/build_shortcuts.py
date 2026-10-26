"""Define zero-copy sector-extension shortcuts; subsidiary data stays separate."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
inventory = json.loads((ROOT / "config/lakehouse_inventory.json").read_text())
entities = json.loads((ROOT / "config/ontology_id_map.json").read_text())["entityTypes"]
ids = {x["displayName"]: x["id"] for x in inventory["lakehouses"]}
bindings = {}
for name, entity in entities.items():
    if not name.endswith("Extension"):
        continue
    lakehouse = entity["lakehouse"]
    sector, country = lakehouse.split("_")[1:3]
    source_schema = "dbo/" if lakehouse == "LH_Metals_JP_01" else ""
    shortcut = f"raw_{sector.lower()}_{country.lower()}_extension"
    bindings[name] = {
        "source_lakehouse": lakehouse,
        "source_table": entity["table"],
        "lakehouse": "LH_Group_SAP",
        "table": shortcut,
        "create": {
            "path": "Tables/dbo",
            "name": shortcut,
            "target": {"oneLake": {
                "workspaceId": inventory["workspaceId"],
                "itemId": ids[lakehouse],
                "path": "Tables/" + source_schema + entity["table"],
            }},
        },
    }
(ROOT / "config/sector_shortcuts.json").write_text(
    json.dumps(bindings, ensure_ascii=False, indent=2))
cleanup = {"sequence": {"maxParallelism": 1, "operations": [
    {"delete": {"object": {"expression": "DB_" + name}}}
    for name in ids if name != "LH_Group_SAP"
]}}
(ROOT / "config/ontology_cleanup_expressions.json").write_text(
    json.dumps(cleanup, indent=2))
print(json.dumps({"zero_copy_shortcuts": len(bindings), "raw_lakehouses": len(ids) - 1}))
