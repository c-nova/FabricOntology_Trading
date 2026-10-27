# Trading Multi-Sector Ontology Demo

## Scope and reproducibility

This is **fictional synthetic data**, not any real company's private data.
Names are invented demo names, not representations of real subsidiaries.
Period: **2025-10-01 through 2026-09-30**, 365 days. Latest data date: 2026-09-30.
Priority: EBITDA, then simplified CF. Local currencies: JPY/USD; group currency: JPY.
Deterministic seed: `20261023`. Four 100% and four 51% ownership assignments are
randomly shuffled across the eight entities, not determined by country.
`config/subsidiaries.json` is the generated canonical company register;
`config/subsidiaries.yaml` mirrors it.

## Workspace and physical separation

Workspace: `Trading` (`fb31bf6e-8199-4559-b1ce-541d04d20f04`).
Nine separate Lakehouses are preserved:

- Parent/SAP-like: `LH_Group_SAP`
- Metals: `LH_Metals_JP_01`, `LH_Metals_US_01`
- Energy: `LH_Energy_JP_01`, `LH_Energy_US_01`
- Foods: `LH_Foods_JP_01`, `LH_Foods_US_01`
- Finance: `LH_Finance_JP_01`, `LH_Finance_US_01`

Live discovery found the parent and Metals JP schema-enabled (`Tables/dbo/...`);
the other seven are legacy (`Tables/...`). Deployment branches on live properties.
No existing Lakehouse is replaced. Typed Delta tables are written with PySpark;
the Lakehouse SQL analytics endpoint is not used for DDL/DML.

Each subsidiary owns its profile, contracts, variable daily activities, events,
evidence, causal bridges, monetary effects, daily metrics, and sector extension.
Physical trading sectors also have weekly shipments; finance has exposures rather
than invented physical shipments. Common grains: 12 contracts/company, three
activities/company/day, company/day/metric/scenario financials.

## Events and accounting

Each sector has one material negative and one positive designed event.
Two cross-sector events affect all eight subsidiaries. Source-like evidence uses
`SIM://` records and is explicitly synthetic. Event effects start after a
company-specific 2–5-day lag and decay over 14 days.

`event_financial_effects` has one unique event/activity effect, with separate
revenue, cost, EBITDA and CF deltas. Actual activity EBITDA minus baseline
equals the sum of these effects exactly. Do not add effects to actual a second
time, or multiply effects through evidence/shipments one-to-many joins.
Event evidence plus designed mechanism is **not empirical proof of causation**.

All subsidiaries are controlled and fully consolidated:

- Full consolidated effect: `delta_local × daily_fx`
- Ownership-weighted **management contribution**: `delta_local × daily_fx × ownership`

Weighted management contribution is **not statutory consolidated EBITDA**,
equity-method income or non-controlling-interest accounting. CF is a simplified
80%-of-EBITDA baseline plus separately attributed event CF effects, not formal
operating/free cash flow. Parent corporate costs, tax, capital consolidation,
and inventory unrealized-profit elimination are outside this demo.

Internal services have 24 seller/buyer pairs, identical currency/date/amount,
and immediately recognized buyer expense. SAP-like GL includes their balanced
debit/credit journals. Internal sales and expenses are eliminated as opposite
entries per pair. Group semantic daily operating metrics represent external
transactions; internal services are held separately in `intercompany_transactions`.
Do not subtract internal sales again from external-only daily metrics.

## Historical FX provenance

Actual daily ECB observations are retained in `data/ecb_fx_raw.csv`:

`https://data-api.ecb.europa.eu/service/data/EXR/D.USD+JPY.EUR.SP00.A?startPeriod=2025-09-25&endPeriod=2026-09-30&format=csvdata`

JPY/USD = ECB JPY/EUR divided by USD/EUR. Weekends/ECB holidays use the immediately
preceding observation for at most five days; `observation_date` and `fill_days`
remain visible. There is no interpolation or invented future FX. JPY identity
rate is 1. Local prices and event narratives remain synthetic. Source hash,
coverage, ownership and reconciliation are in `reports/local_validation.json`.
Money uses Decimal and typed Delta `DECIMAL(28,8)`; rounding is to currency cents.
Daily and effect-level JPY sums can differ slightly because rounding grains differ.

## Ontology and Data Agent

Core: Company, RiskEvent, Activity, Contract, Shipment, Evidence,
FinancialEffect, FinancialMetric, GroupKPI. Eight company-specific sector
extensions access their own Lakehouses through zero-copy OneLake shortcuts in
the parent (`raw_<sector>_<jp/us>_extension`). The core uses parent
`semantic_*` projections carrying `source_lakehouse` provenance, needed because
an ontology entity supports only one static table binding.

`RiskEvent → Activity → Contract → FinancialEffect → FinancialMetric → GroupKPI`
is wired with evidence and ownership paths. Explicit effect/metric and
metric/KPI link tables avoid ambiguous date-only joins.
The deployed current-format definition is `ontology_tmdl/` and
`config/ontology_create.json`. The `ontology/` JSON tree is a legacy reference
intermediate, not a deployment artifact. No credentials are embedded.

All 20 table partitions use OneLake `AzureStorage.DataLake` expressions and
native `ONT_*` connection metadata. Public definition import currently removes
reserved connection annotations. After any replacement, reapply
`config/ontology_connection_bindings.json` through the native ontology authoring
flow before graph refresh. Merely accepting a definition does not prove graph
eligibility. The live readback confirms all 20 partition bindings. Direct
cross-Lakehouse extension edges were not queryable in the first runtime test;
the verified final layout uses eight shortcuts without moving/copying originals.
All 17 entity types were eligible; the final graph refresh completed at
**2026-10-23 09:44:24Z**. Real GQL queries verified **33,960 nodes / 65,684
edges**, all **17 entity types / 39 relationship types**, and complete
evidence/activity/contract/effect/metric/KPI paths for **all 1,344 effects across
10 events**. Graph numeric properties are floating-point; SQL DECIMAL remains
the accounting authority.

All 42 relationships (tabular relationships behind the 39 entity relationships)
are active, which the Data Agent needs: it builds join specifications only from
active relationships, and inactive ones leave its traversal planner without a
path. The first deployment wrote `isActive: false` on all of them; the generator
no longer does. Changing a relationship through the public API has a side effect:
`updateDefinition` (like create) removes the reserved `ONT_*` connection
annotations, 160 becoming 20. Afterwards the 20 scripts of
`config/ontology_connection_bindings.json` are sent one by one to the ontology
authoring endpoint that the Fabric UI itself calls (`POST …/DigitalOperationsService/direct/v4/workspaces/{workspaceId}/ontologies/{ontologyId}/definition/scripts`,
authenticated with a workload token that the web app requests for the signed-in
user). This restores 8 annotations on each of the 20 tables, the entities show
as eligible again, and the graph data is refreshed from the ontology page. The
endpoint is not documented and may change. On 2026-10-27 the sequence was
update, re-apply (20 of 20), refresh; node and edge counts per type were equal
to before (`reports/da_traversal_fix_2026-10-27.json`).

DA has two configured sources, within the documented five-source limit:
the ontology and the complete parent logical query surface. Its **25 selected
tables** comprise 17 parent/projection tables and eight zero-copy sector shortcuts.
The original nine Lakehouses and **95 physical tables / 90,424 rows** remain
separate; shortcuts add no copied rows. This layout avoids the source-expansion
cap encountered with direct nine-source bindings. Live DA SQL verified all eight
shortcut-to-activity joins: **365/365 each, zero unmatched rows**.
Japanese instructions, fixed-period questions, SQL examples and distinct
full/weighted metrics explicitly address stale dates and duplicate attribution;
generated answers still require review.
Equivalent numerical joins are possible in Snowflake/SQL; the ontology benefit
is shared meaning, relationships and traceable paths, not exclusive join ability.

SQL endpoint metadata must finish synchronizing before selecting source tables.
The first DA test encountered stale seven-table metadata and failed. Source
Refresh alone did not invalidate the server cache; removing/re-adding only the
DA source registration after SQL synchronization did. The final selected source
uses the canonical `Schemas/dbo/Tables` hierarchy. Live Japanese tests verified
annual full/weighted EBITDA, actual/baseline EBITDA/CF, the four/four ownership
mix, weekend ECB FX provenance, 24 reconciled internal pairs, all ten signed event
totals, evidence-to-KPI IDs, and the fixed latest-30-day period. An initial event
query wrongly excluded `primary_sector='all'`; instructions were corrected and
the **published production-stage query** returned all ten exact totals.
Non-English Data Agent use is not officially supported
by current Microsoft documentation; Japanese responses are verified best-effort.
The UI exposes Standard (GA) and Preview runtimes (Microsoft Learn, Fabric data agent
runtime, updated 2026-10-22); the published agent runs on Preview. Learn (Fabric data
agent concepts, updated 2026-10-21) still lists non-English languages as not currently
supported; Japanese is verified best-effort only.

The Data Agent was **actually published through Fabric**, not merely imported
with a `published/` definition folder. Publication returned HTTP 200 and the UI
confirmed success. The separate published-view (`stage=production`) Japanese
query passed. Microsoft Copilot publication remained **OFF**; no sharing grants or
outbound messages were made during deployment.

On 2026-10-26 only the agent instructions were extended (`prompts/da_instructions_ja.txt`,
about 5,600 of 15,000 characters) with a "question reading" section so that short casual
questions work: default period words, metric words, event nicknames, sector and country
words, aggregation unit, unit format and no carry-over from the previous question. Failures
found after each publish (a one-day value for a period question, 10x unit slips, daily detail
only, topic carry-over) led to five publishes in total. Ten casual questions went from
6 OK / 2 partial / 2 NG to 10 OK, and Q1-Q4 numbers did not change. Results are
non-deterministic; see `reports/da_casual_baseline_2026-10-26.json` and
`reports/da_casual_after_2026-10-26.json` for the record and the known limits. Data, ontology,
Lakehouses, data-source instructions and example queries were not changed.

On 2026-10-27 eight read-only runs on the published agent (`reports/da_group_wide_2026-10-27.json`)
checked the group-wide pages of the presenter guide: sector, per-company and largest-event amounts
equal the saved data exactly at two decimals; the prose around the tables can be wrong; the chain
and FX what-if questions were answered with caveats or inconsistently between two runs; and in the six
runs that tried an ontology traversal the tool returned `no_path_found`, so every answer came from SQL on
the lakehouse tables with the ontology injected as context. Nothing was changed in that run.

The cause was found the same day: the generator had written `isActive: false` on all 42 relationships, and
the agent lists a join specification only for active relationships (scratch copies of the ontology showed
the same agent and question resolving 39 of 39 joins when the relationships are active, and failing
when they are not, on both the Standard and the Preview runtime). The relationships were set active in the
production ontology, the connection annotations were re-applied and the graph data was refreshed (see the
ontology section). The agent itself was not changed or republished. Eight repeat runs on the published
agent (`reports/da_traversal_fix_2026-10-27.json`) found a path in all 6 runs that tried a traversal,
including multi-hop paths with link-table joins, and the amounts did not change. The demo questions Q1 to Q4 and the
action question were run once each afterwards and equal the saved data. The agent still answers
with SQL on the lakehouse tables; it has no tool that queries the graph.

Annual actual JPY: full EBITDA **44,757,399,732.84**, ownership-weighted
management EBITDA **33,547,898,914.09**. Accounting and live-query evidence:
`reports/cloud_validation.json`, `reports/end_to_end_validation.json`,
`reports/da_qa_final_draft.json`, `reports/da_qa_published.json`,
`reports/da_group_wide_2026-10-27.json`, `reports/da_traversal_fix_2026-10-27.json`, and the graph count/path reports. Model-internal traces are removed from QA reports.

## Live entry points

- Workspace: https://app.fabric.microsoft.com/groups/fb31bf6e-8199-4559-b1ce-541d04d20f04/list?experience=fabric-developer
- Ontology: https://app.fabric.microsoft.com/groups/fb31bf6e-8199-4559-b1ce-541d04d20f04/ontologies/71b8b726-4f82-491b-afcb-ab5c75510e5e
- Data Agent: https://app.fabric.microsoft.com/groups/fb31bf6e-8199-4559-b1ce-541d04d20f04/aiskills/f8bd4ae0-96fa-4752-b911-6ebcc8c531e7?experience=fabric-developer

In the Data Agent, choose **公開済み** to use the published version. In the
Ontology, **グラフの探索** opens the materialized graph. Resource IDs, publication
state, and verification references are persisted in `config/deployment_manifest.json`.

## Rebuild and verification

### Demo step 3: real ontology-backed graph paths → notebook DAG

New notebook **TradingDemo_03_食品損失のOntology経路とDAG**:
https://app.fabric.microsoft.com/groups/fb31bf6e-8199-4559-b1ce-541d04d20f04/synapsenotebooks/a4f43713-21d0-481e-a843-50566614182d

The DA-to-notebook transition is intentional: the DA states the loss magnitude;
the notebook renders the graph. It reads the **materialized GraphModel derived
from the ontology**, not an invented ontology query API and not a SQL JOIN diagram.
The current documented GQL beta endpoint is
`POST /v1/workspaces/{workspaceId}/graphModels/{graphModelId}/executeQuery?beta=true`
([reference](https://learn.microsoft.com/en-us/fabric/graph/gql-query-api)).
Runtime authentication uses `notebookutils.credentials.getToken("pbi")`; browser
credentials are never embedded.

The completed notebook run returned all84 FOD_NEG evidence/event/effect/activity/
contract/metric/KPI paths and one real food-observation edge. An eight-node,
seven-edge SVG DAG shows a readable **acyclic subset** of these actual directed
relationships. Additional matched relationships remain in its lineage table.
Associations, designed effect attribution and metric aggregation are distinguished;
neither a graph edge nor a temperature reading proves real-world causation.
No temperature limit or threshold violation is inferred.

Separate read-only Spark Delta DECIMAL reads verify the unique effect membership
and money. The dashboard distinguishes **event-wide loss -114,461,186.25 JPY**,
**representative one-effect delta -3,003,488.94 JPY**, and **same-day all-company
actual EBITDA +113,069,201.90 JPY**. These different grains must not be summed.
The representative is selected deterministically from live results, not copied
from an earlier report.

The notebook saves its actual runtime HTML/SVG dashboard and audit into **its own
new definition only**. Reopening the notebook was verified to show the persisted
diagram without executing cells. It is explicitly a timestamped snapshot; Run all
reads the graph again and fails on auth, empty results or reconciliation mismatch,
without static simulated-edge fallback. Original tables, ontology, graph
materialization, DA and earlier notebooks are unchanged.

Artifacts: `config/step3_deployment.json`, `scripts/step3_food_loss_runtime.py`,
`notebooks/TradingDemo_03_FoodLoss_Ontology_DAG.ipynb`,
`notebooks/TradingDemo_03_FoodLoss_Ontology_DAG.executed.ipynb`,
`reports/step3_live_audit.json`, `reports/step3_ui_verification.json`, and standalone
`reports/step3_food_loss_dashboard.html` / `step3_food_loss_dag.svg`.
Validate with `python3 scripts/verify_step3.py`.

### Original dataset and semantic build

From this project directory:

```sh
python3 scripts/generate_demo.py
python3 scripts/build_notebook.py
python3 scripts/build_shortcuts.py
python3 scripts/build_semantic.py 71b8b726-4f82-491b-afcb-ab5c75510e5e
python3 scripts/verify_live_reports.py
```

The generator fails on incomplete actual FX coverage, dangling keys, duplicate
effects, unbalanced journals, internal mismatch or attribution mismatch.
The deployed notebook writes persistent Delta, checks row counts, cross-Lakehouse
joins, foreign keys, event attribution, intercompany pairs and GL balance.
The finalize notebook writes relationship link tables, checks cloud annual
KPI totals against the local reference and verifies managed table resolution.
Its report is `LH_Group_SAP/Files/trading_demo_validation.json`.

Rebuild sequencing matters: deploy/verify physical tables first, create the
eight shortcuts from `config/sector_shortcuts.json`, finish SQL metadata sync,
then deploy ontology/source bindings and refresh the graph. Remove unused
connector expressions after changing direct bindings to shortcuts; public ALM
readback rejects unreferenced connectors. Re-register the DA source if its
schema cache predates synchronization. Rebuilding local files does not by
itself deploy or publish cloud changes.

Fabric control-plane REST is used from the signed-in browser context; this
session does not have Fabric MCP tools. Token values never leave memory.
Shell inventory/provision scripts optionally accept `FABRIC_TOKEN` through the
environment only, handle pagination/HTTP failures and bounded LRO polling,
and never accept tokens as command-line arguments. Do not commit credentials, and do
not share or publish outside the requested Fabric workspace.
