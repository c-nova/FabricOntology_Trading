"""Compare persisted live SQL/graph evidence with the deterministic local dataset."""
import base64
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re

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

relationships_live = next(base64.b64decode(x["payload"]).decode() for x in ontology_parts
                          if x["path"] == "relationships.tmdl")
assert len(re.findall(r"^relationship ", relationships_live, re.M)) == 42
assert "isActive" not in relationships_live
relationships_local = (ROOT / "ontology_tmdl/relationships.tmdl").read_text()
assert relationships_local.replace("\r\n", "\n").strip() == relationships_live.replace("\r\n", "\n").strip()

wide = load("reports/da_group_wide_2026-10-27.json")
wide_runs = {x["id"]: x for x in wide["runs"]}
assert len(wide_runs) == 8 and all(x["status"] == "completed" for x in wide_runs.values())
sector_of = {x["entity_id"]: x["sector_code"] for x in group["company_master"]}
entity_of_name = {x["entity_name"]: x["entity_id"] for x in group["company_master"]}


def wide_rows(run_id, column):
    execution = next(x for x in reversed(wide_runs[run_id]["sql_executions"])
                     if x["is_success"] and column in x["columns"] and x["rows_total"] == len(x["rows"]))
    return [dict(zip(execution["columns"], row)) for row in execution["rows"]]


def effect_sums(event, key, field):
    sums = defaultdict(Decimal)
    for effect in effects:
        if effect["event_id"] == event:
            sums[key(effect)] += Decimal(effect[field])
    return sums


def by_sector(effect):
    return sector_of[effect["entity_id"]]


def by_entity(effect):
    return effect["entity_id"]


def oku(value, places="0.01"):
    return (Decimal(value) / Decimal(10) ** 8).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def exactly(value, expected):
    return Decimal(str(value)) == expected


sector_rows = wide_rows("B_sector", "sector_code")
assert len(sector_rows) == 8
for row in sector_rows:
    event, sector = row["event_id"], row["sector_code"]
    assert exactly(row["delta_ebitda_full_oku_jpy"],
                   oku(effect_sums(event, by_sector, "delta_ebitda_full_jpy")[sector]))
    assert exactly(row["delta_management_oku_jpy"],
                   oku(effect_sums(event, by_sector, "delta_management_jpy")[sector]))
    assert row["distinct_effect_count"] == 84

annual_by_entity = defaultdict(Decimal)
for metric in group["semantic_financial_metrics_daily"]:
    if metric["scenario_tag"] == "actual" and metric["metric_code"] == "EBITDA":
        annual_by_entity[metric["entity_id"]] += Decimal(metric["amount_group"])
cross_full = effect_sums("CROSS_NEG", by_entity, "delta_ebitda_full_jpy")
cross_mgmt = effect_sums("CROSS_NEG", by_entity, "delta_management_jpy")
cross_cf = effect_sums("CROSS_NEG", by_entity, "delta_cf_full_jpy")
cross_contracts = defaultdict(set)
for effect in effects:
    if effect["event_id"] == "CROSS_NEG":
        cross_contracts[effect["entity_id"]].add(effect["contract_id"])

company_rows = wide_rows("company", "subsidiary_name")
assert len(company_rows) == 8 and sum(x["impacted_contract_count"] for x in company_rows) == 26
for row in company_rows:
    entity = entity_of_name[row["subsidiary_name"]]
    assert exactly(row["full_consolidated_impact_oku_jpy"], oku(cross_full[entity]))
    assert exactly(row["management_weighted_impact_oku_jpy"], oku(cross_mgmt[entity]))
    assert row["impacted_contract_count"] == len(cross_contracts[entity])
    assert exactly(row["impact_pct_of_annual_actual_full_ebitda"],
                   (cross_full[entity] / annual_by_entity[entity] * 100).quantize(
                       Decimal("0.01"), rounding=ROUND_HALF_UP))

casual_rows = wide_rows("casual_all_companies", "entity_id")
assert len(casual_rows) == 8
for row in casual_rows:
    entity = row["entity_id"]
    assert exactly(row["delta_ebitda_full_jpy_oku"], oku(cross_full[entity]))
    assert exactly(row["delta_management_jpy_oku"], oku(cross_mgmt[entity]))
    assert exactly(row["delta_cf_full_jpy_oku"], oku(cross_cf[entity]))
    assert row["effect_id_count"] == 42

largest = wide_rows("casual_largest_event", "event_id")[0]
annual_total = sum(annual_by_entity.values())
assert largest["event_id"] == "CROSS_NEG"
assert exactly(largest["delta_ebitda_full_jpy_oku"], oku(sum(cross_full.values()), "0.0001"))
assert exactly(largest["annual_ebitda_full_consolidated_oku"], oku(annual_total, "0.001"))
assert exactly(largest["event_impact_to_annual_ebitda_percent"],
               (sum(cross_full.values()) / annual_total * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

usd_local = sum((Decimal(x["amount_local"]) for x in group["semantic_financial_metrics_daily"]
                 if x["scenario_tag"] == "actual" and x["metric_code"] == "EBITDA"
                 and x["currency_code"] == "USD"), Decimal(0))
sensitivity = wide_rows("fx_what_if_1", "yen_appreciation_10_jpy_sensitivity_oku_jpy")[0]
assert exactly(sensitivity["yen_appreciation_10_jpy_sensitivity_oku_jpy"], oku(-usd_local * 10, "0.0001"))
exposure = wide_rows("fx_what_if_2", "usd_actual_ebitda_exposure_usd")[0]
assert exactly(exposure["usd_actual_ebitda_exposure_usd"], usd_local)
assert "算定できません" in wide_runs["fx_what_if_2"]["answer"]

traversals = [x["ontology_traversal"] for x in wide_runs.values() if isinstance(x["ontology_traversal"], list)]
assert len(traversals) == 6 and all(t and t[0]["chosenPath"] == "no_path_found" for t in traversals)
for run_id in ("chain_1", "chain_2"):
    assert "intercompany" in wide_runs[run_id]["answer"] or "内部取引" in wide_runs[run_id]["answer"]

# Repeat of the eight runs after the relationships were set active (2026-10-27, about 15 minutes after the change).
fixed = load("reports/da_traversal_fix_2026-10-27.json")
fixed_runs = {x["id"]: x for x in fixed["runs"]}
assert set(fixed_runs) == set(wide_runs) and all(x["status"] == "completed" for x in fixed_runs.values())
fixed_attempts = {k: x["ontology_traversal"] for k, x in fixed_runs.items() if isinstance(x["ontology_traversal"], list)}
assert set(fixed_attempts) == {k for k, x in wide_runs.items() if isinstance(x["ontology_traversal"], list)}
assert all(t["found"] and t["chosenPath"] == "single_engine_join" for v in fixed_attempts.values() for t in v)
assert all(x["ontology_context"]["selected_entities"] == 17
           and x["ontology_context"]["context_chars"] > fixed["cause"]["before_fix"]["context_chars"]
           for x in fixed_runs.values())
assert fixed["verification"]["graph"]["node_counts"] == actual_nodes
assert fixed["verification"]["graph"]["edge_counts"] == actual_edges


def fixed_rows(run_id, column):
    table = next(t for t in reversed(fixed_runs[run_id]["result_tables"]) if column in t["columns"])
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def close(value, expected, tolerance):
    return abs(Decimal(str(value)) - expected) <= Decimal(tolerance)


for row in fixed_rows("B_sector", "sector_code"):
    if row["event_id"] in ("CROSS_NEG", "CROSS_POS") and row["sector_code"] != "ALL_4_SECTORS":
        event, sector = row["event_id"], row["sector_code"]
        assert exactly(row["full_consolidated_ebitda_impact_jpy_oku"],
                       oku(effect_sums(event, by_sector, "delta_ebitda_full_jpy")[sector]))
        assert exactly(row["management_ebitda_impact_jpy_oku"],
                       oku(effect_sums(event, by_sector, "delta_management_jpy")[sector]))
        assert row["unique_effect_id_count"] == 84
for row in fixed_rows("company", "subsidiary_name"):
    entity = entity_of_name[row["subsidiary_name"]]
    assert close(row["cross_neg_ebitda_full_oku_jpy"], oku(cross_full[entity], "0.0000001"), "0.0000001")
    assert close(row["cross_neg_ebitda_management_oku_jpy"], oku(cross_mgmt[entity], "0.0000001"), "0.0000001")
    assert row["affected_contract_count"] == len(cross_contracts[entity])
    assert close(row["cross_neg_impact_pct_of_annual_ebitda"],
                 cross_full[entity] / annual_by_entity[entity] * 100, "0.0001")
fixed_company_rows = fixed_rows("casual_all_companies", "company_id")
assert len(fixed_company_rows) == 8
for row in fixed_company_rows:
    entity = row["company_id"]
    assert exactly(row["delta_ebitda_full_oku_jpy"], oku(cross_full[entity]))
    assert exactly(row["delta_management_oku_jpy"], oku(cross_mgmt[entity]))
    assert exactly(row["delta_cf_full_oku_jpy"], oku(cross_cf[entity]))
fixed_largest = fixed_rows("casual_largest_event", "event_id")[0]
assert fixed_largest["event_id"] == "CROSS_NEG"
assert exactly(fixed_largest["full_consolidated_ebitda_impact_oku_jpy"], oku(sum(cross_full.values()), "0.0001"))
assert exactly(fixed_largest["annual_actual_ebitda_oku_jpy"], oku(annual_total, "0.001"))
assert exactly(fixed_largest["impact_as_percent_of_annual_actual_ebitda"],
               (sum(cross_full.values()) / annual_total * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
assert exactly(fixed_rows("fx_what_if_1", "change_jpy_oku")[0]["change_jpy_oku"], oku(-usd_local * 10))
assert not any(sector_of[x["entity_id"]] == "foods" or sector_of[x["counterparty_entity_id"]] == "foods"
               for x in group["intercompany_transactions"])
assert fixed_runs["chain_2"]["result_tables"][1]["rows_total"] == 0

demo = {x["id"]: x for x in fixed["demo_questions"]}
assert set(demo) == {"Q1", "Q2", "Q3", "Q4", "Q_ACT"} and all(x["status"] == "completed" for x in demo.values())
assert demo["Q1"]["ontology_traversal"] == demo["Q2"]["ontology_traversal"] == "not attempted"
assert all(t["found"] and t["chosenPath"] == "single_engine_join"
           for q in ("Q3", "Q4", "Q_ACT") for t in demo[q]["ontology_traversal"])
monthly, weighted_actual = defaultdict(Decimal), Decimal(0)
for row in group["kpi_snapshot"]:
    if row["kpi_code"] == "EBITDA_FULL_CONSOLIDATED":
        monthly[row["scenario_tag"], str(row["kpi_date"])[:7]] += Decimal(row["amount_group"])
    if row["kpi_code"] == "EBITDA_MANAGEMENT_WEIGHTED" and row["scenario_tag"] == "actual":
        weighted_actual += Decimal(row["amount_group"])
q1_tables = {tuple(t["columns"]): t for t in demo["Q1"]["result_tables"]}
series = q1_tables[("year_month", "scenario_tag", "ebitda_full_consolidated_oku_jpy")]["rows"]
assert len(series) == 24
for month, scenario, value in series:
    assert close(value, monthly[scenario, month] / Decimal(10) ** 8, "0.0001")
annual_row = q1_tables[("full_consolidated_ebitda_oku_jpy", "management_contribution_ebitda_oku_jpy")]["rows"][0]
assert close(annual_row[0], oku(annual_total), "0.005") and close(annual_row[1], oku(weighted_actual), "0.005")
q2_rows = demo["Q2"]["result_tables"][0]["rows"]
assert len(q2_rows) == 10
for event, value in q2_rows:
    assert close(value, totals[event][0] / Decimal(10) ** 8, "0.000001")

representative = min((x for x in effects if x["event_id"] == "FOD_NEG"), key=lambda x: x["effect_id"])
q3 = demo["Q3"]["extracted"]
assert exactly(q3["full_oku"], oku(totals["FOD_NEG"][0])) and exactly(q3["management_oku"], oku(totals["FOD_NEG"][1]))
assert q3["unique_effect_count"] == effect_counts["FOD_NEG"] == 84
for key, field in (("effect_id", "effect_id"), ("activity_id", "activity_id"),
                   ("contract_id", "contract_id"), ("evidence_id", "evidence_id")):
    assert q3[key] == representative[field]
day = representative["effect_date"][:10]
assert q3["daily_metric_id"] in {x["metric_id"] for x in group["semantic_financial_metrics_daily"]
                                 if x["entity_id"] == representative["entity_id"] and x["scenario_tag"] == "actual"
                                 and x["metric_code"] == "EBITDA" and str(x["metric_date"])[:10] == day}
assert q3["kpi_id"] in {x["kpi_id"] for x in group["kpi_snapshot"] if x["kpi_code"] == "EBITDA_FULL_CONSOLIDATED"
                        and x["scenario_tag"] == "actual" and str(x["kpi_date"])[:10] == day}

q4 = demo["Q4"]["extracted"]
energy_positive = [x for x in effects if x["event_id"] == "ENE_POS"]
assert exactly(q4["full_oku"], oku(totals["ENE_POS"][0])) and exactly(q4["management_oku"], oku(totals["ENE_POS"][1]))
assert set(q4["evidence_ids"]) == {x["evidence_id"] for x in energy_positive}
assert set(q4["contract_ids"]) == {x["contract_id"] for x in energy_positive}

negative_events = ("MTL_NEG", "ENE_NEG", "FOD_NEG", "FIN_NEG", "CROSS_NEG")
contract_sum, contract_events = defaultdict(Decimal), defaultdict(set)
for x in effects:
    if x["event_id"] in negative_events:
        contract_sum[x["contract_id"]] += Decimal(x["delta_ebitda_full_jpy"])
        contract_events[x["contract_id"]].add(x["event_id"])
expected_contracts = {c for c, _ in sorted(contract_sum.items(), key=lambda kv: kv[1])[:5]} | {
    c for c, events in contract_events.items() if len(events) >= 2}
action_rows = demo["Q_ACT"]["extracted"]["table"]
assert {x["contract_id"] for x in action_rows} == expected_contracts
for x in action_rows:
    assert exactly(x["full_oku"], oku(contract_sum[x["contract_id"]]))
    assert set(x["events"]) == contract_events[x["contract_id"]] and x["event_count"] == len(x["events"])

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
    "group_wide_da_runs_verified": {"runs": 8, "amount_tables_matching_saved_data": 4,
                                    "ontology_traversal_no_path_runs": len(traversals)},
    "traversal_fix_verified": {"relationships_active": 42, "runs": 8,
                               "ontology_traversal_found_runs": len(fixed_attempts),
                               "demo_questions_rechecked": len(demo)},
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
