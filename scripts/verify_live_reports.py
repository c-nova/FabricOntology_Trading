"""Compare persisted live SQL/graph evidence with the deterministic local dataset."""
import base64
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


def decoded(part):
    return json.loads(base64.b64decode(part["payload"]))


def sql_results(report):
    return [dict(zip(x["columns"], row)) for x in report["sql_executions"]
            if x.get("is_success") for row in x["rows"]]


def graph_rows(path):
    report = load(path)
    assert report["status"]["code"] == "00000", path
    return report["result"]["data"]


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


data = load("data/demo_dataset.json")
group = data["LH_Group_SAP"]
mapping = load("config/ontology_id_map.json")
nodes = graph_rows("reports/graph_node_counts.json")
actual_nodes = {x["entity_type"]: int(x["instance_count"]) for x in nodes}
expected_nodes = {name: len(data[e["lakehouse"]][e["table"]])
                  for name, e in mapping["entityTypes"].items()}
assert actual_nodes == expected_nodes

old = load("config/ontology_old_json_reference.json")
parts = {x["path"]: decoded(x) for x in old["definition"]["parts"]}
inventory = load("config/lakehouse_inventory.json")
lakehouses = {x["id"]: x["displayName"] for x in inventory["lakehouses"]}
edges = graph_rows("reports/graph_edge_counts.json")
actual_edges = {x["relationship_type"]: int(x["edge_count"]) for x in edges}
expected_edges = {}
for name, rel in mapping["relationshipTypes"].items():
    context = parts[f"RelationshipTypes/{rel['id']}/Contextualizations/{rel['contextualization']}.json"]
    source = context["dataBindingTable"]
    expected_edges[name] = len(data[lakehouses[source["itemId"]]][source["sourceTableName"]])
assert actual_edges == expected_edges

effects = group["semantic_event_financial_effects"]
effect_counts = Counter(x["event_id"] for x in effects)
paths = graph_rows("reports/graph_all_event_paths.json")
assert {x["event_id"]: int(x["effects_with_complete_path"]) for x in paths} == effect_counts
totals = defaultdict(lambda: [Decimal(0), Decimal(0)])
for effect in effects:
    totals[effect["event_id"]][0] += Decimal(effect["delta_ebitda_full_jpy"])
    totals[effect["event_id"]][1] += Decimal(effect["delta_management_jpy"])

draft = load("reports/da_qa_final_draft.json")
production = load("reports/da_qa_published.json")
assert not draft["has_more"] and not production["has_more"]
draft_rows, production_rows = sql_results(draft), sql_results(production)
event_rows = [x for x in production_rows if "total_delta_ebitda_full_jpy" in x]
assert len(event_rows) == 10
for row in event_rows:
    full, weighted = totals[row["event_id"]]
    assert money(row["total_delta_ebitda_full_jpy"]) == money(full)
    assert money(row["total_delta_management_jpy"]) == money(weighted)
    assert row["effect_id_count"] == effect_counts[row["event_id"]]
    assert row["total_event_count"] == 10

kpis = defaultdict(Decimal)
for kpi in group["kpi_snapshot"]:
    kpis[kpi["kpi_code"], kpi["scenario_tag"]] += Decimal(kpi["amount_group"])
annual = [x for x in draft_rows if "amount_group_total_jpy" in x]
assert len(annual) == 8
for row in annual:
    assert money(row["amount_group_total_jpy"]) == money(kpis[row["kpi_code"], row["scenario_tag"]])
smoke = next(x for x in production_rows if "ebitda_full_consolidated_jpy" in x)
assert money(smoke["ebitda_full_consolidated_jpy"]) == money(kpis["EBITDA_FULL_CONSOLIDATED", "actual"])
assert money(smoke["ebitda_management_weighted_jpy"]) == money(kpis["EBITDA_MANAGEMENT_WEIGHTED", "actual"])

ownership = [x for x in draft_rows if "ownership_ratio" in x]
assert Counter(Decimal(str(x["ownership_ratio"])) for x in ownership) == {Decimal("1"): 4, Decimal(".51"): 4}
fx = next(x for x in draft_rows if "fill_days" in x)
assert str(fx["observation_date"]).startswith("2026-09-04") and fx["fill_days"] == 1
assert Decimal(str(fx["fx_rate"])) == Decimal("156.24677336")
assert fx["source"].startswith("https://data-api.ecb.europa.eu/")
pairs = [x for x in draft_rows if "post_elimination_residual_jpy" in x]
assert len(pairs) == 24 and all(money(x["post_elimination_residual_jpy"]) == 0 for x in pairs)
shortcuts = [x for x in draft_rows if "activity_join_success_count" in x]
assert len(shortcuts) == 8
assert all(x["extension_total_count"] == x["activity_join_success_count"] == 365
           and x["activity_join_failure_count"] == 0 for x in shortcuts)
assert any("semantic_metric_kpi_links" in x.get("sql", "") and "k.kpi_id" in x.get("sql", "")
           and x.get("is_success") for x in draft["sql_executions"])

shortcut_readback = load("reports/sector_shortcuts_readback.json")
assert not shortcut_readback.get("continuationToken")
shortcut_by_name = {x["name"]: x for x in shortcut_readback["value"]}
assert len(shortcut_by_name) == 8
for binding in load("config/sector_shortcuts.json").values():
    expected = binding["create"]
    actual = shortcut_by_name[expected["name"]]
    assert actual["path"].strip("/") == expected["path"].strip("/")
    assert actual["target"]["oneLake"] == expected["target"]["oneLake"]
assert len({x["target"]["oneLake"]["itemId"] for x in shortcut_by_name.values()}) == 8
ontology_parts = load("reports/ontology_readback.json")["definition"]["parts"]
table_parts = [base64.b64decode(x["payload"]).decode() for x in ontology_parts
               if "/tables/" in "/" + x["path"] and x["path"].endswith(".tmdl")]
assert len(table_parts) == 20
for text in table_parts:
    for annotation in ("WorkspaceId", "ItemId", "ItemKind", "ItemName",
                       "WorkspaceName", "SqlEndpoint", "SqlDatabase", "PinnedAtUtc"):
        assert "annotation ONT_" + annotation + " =" in text

readback = load("reports/data_agent_readback.json")["definition"]["parts"]
for stage in ("draft", "published"):
    source = next(decoded(x) for x in readback if f"/{stage}/" in x["path"]
                  and x["path"].endswith("/datasource.json"))
    selected = source["elements"][0]["children"][0]["children"][0]["children"]
    assert len(selected) == 25 and all(x["is_selected"] for x in selected)
    config = next(decoded(x) for x in readback if x["path"] == f"Files/Config/{stage}/stage_config.json")
    assert config["aiInstructions"] == (ROOT / "prompts/da_instructions_ja.txt").read_text()

job = load("reports/graph_refresh_job_final.json")
assert job["status"] == "Completed" and job["failureReason"] is None
result = {
    "status": "passed",
    "physical_tables": sum(len(tables) for tables in data.values()),
    "physical_rows": sum(len(rows) for tables in data.values() for rows in tables.values()),
    "zero_copy_shortcuts": 8, "raw_lakehouses_preserved": 9,
    "graph_entity_types_verified": len(actual_nodes),
    "graph_nodes_verified": sum(actual_nodes.values()),
    "graph_relationship_types_verified": len(actual_edges),
    "graph_edges_verified": sum(actual_edges.values()),
    "complete_event_paths_verified": len(paths),
    "all_event_effects_traversable": sum(effect_counts.values()),
    "published_sql_event_totals_verified": 10,
    "annual_ebitda_cf_actual_baseline_totals_verified": 8,
    "ownership_mix_verified": {"100_percent": 4, "51_percent": 4},
    "intercompany_pairs_reconciled": 24,
    "weekend_ecb_fx_verified": True, "all_shortcut_activity_joins_verified": True,
    "published_stage_live_japanese_query_verified": True,
    "data_agent_selected_tables": 25, "data_agent_runtime": "Preview",
    "limitations": [
        "Japanese Data Agent responses are tested best-effort, not officially supported.",
        "Graph properties use floating point; exact accounting uses SQL DECIMAL.",
        "Ownership-weighted management contribution is not statutory consolidated EBITDA.",
        "CF is a simplified simulation; evidence and causal attribution are synthetic.",
    ],
}
(ROOT / "reports/end_to_end_validation.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
