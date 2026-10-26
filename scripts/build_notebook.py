"""Package validated local data into a reproducible Fabric notebook definition."""
import base64
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
inventory = json.loads((ROOT/"config/lakehouse_inventory.json").read_text())
dataset = json.loads((ROOT/"data/demo_dataset.json").read_text())
links_only = "--links-only" in sys.argv
if links_only:
    dataset = {"LH_Group_SAP":{k:v for k,v in dataset["LH_Group_SAP"].items()
                             if k in ("semantic_effect_metric_links","semantic_metric_kpi_links")}}
packed = base64.b64encode(zlib.compress(json.dumps(dataset,ensure_ascii=False).encode(),9)).decode()
code = """import base64, datetime, decimal, json, re, zlib
import notebookutils
from pyspark.sql import functions as F, types as T
context = notebookutils.runtime.context
workspace_id = context["currentWorkspaceId"]
assert workspace_id == EXPECTED_WORKSPACE
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "").rstrip("/")
lakehouses = {x["displayName"]: x for x in notebookutils.lakehouse.list(workspace_id)}
data = json.loads(zlib.decompress(base64.b64decode(PACKED_DATA)))
counts = {}
if LINKS_ONLY:
    prior = json.loads(notebookutils.fs.head("Files/trading_demo_validation.json", 1000000))
    assert prior["status"] == "passed"
    counts.update(prior["counts"])
spark.conf.set("spark.sql.shuffle.partitions", "4")

def make_frame(rows):
    fields, converters = [], {}
    for col, sample in rows[0].items():
        values = [r[col] for r in rows if r[col] is not None]
        if isinstance(sample, bool):
            dtype = T.BooleanType()
        elif isinstance(sample, int):
            dtype = T.LongType()
        elif all(isinstance(v,str) and re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}",v) for v in values):
            dtype = T.DateType()
            converters[col] = datetime.date.fromisoformat
        elif all(isinstance(v,str) and re.fullmatch(r"-?\\d+(\\.\\d+)?",v) for v in values):
            dtype = T.DecimalType(28,8)
            converters[col] = decimal.Decimal
        else:
            dtype = T.StringType()
        fields.append(T.StructField(col,dtype,False))
    converted = [{k:converters[k](v) if k in converters else v for k,v in row.items()} for row in rows]
    return spark.createDataFrame(converted,T.StructType(fields))

for name, tables in data.items():
    lh = lakehouses[name]
    assert lh["id"] == EXPECTED_LAKEHOUSES[name], "Lakehouse identity changed"
    properties = notebookutils.lakehouse.getWithProperties(name, workspace_id)
    # The live workspace contains both schema-enabled and legacy lakehouses.
    schema_enabled = bool(properties.get("properties",{}).get("defaultSchema"))
    for table, rows in tables.items():
        path = f"abfss://{workspace_id}@{endpoint}/{lh['id']}/Tables/{'dbo/' if schema_enabled else ''}{table}"
        frame = make_frame(rows)
        frame.coalesce(1).write.format("delta").mode("overwrite").option("overwriteSchema","true").save(path)
        actual = spark.read.format("delta").load(path).count()
        assert actual == len(rows), (name,table,actual,len(rows))
        counts[name+"."+table] = actual
        print("PERSISTED", name, table, actual)

group_id = lakehouses["LH_Group_SAP"]["id"]
group_path = f"abfss://{workspace_id}@{endpoint}/{group_id}/Tables/dbo/"
effects = spark.read.format("delta").load(group_path+"semantic_event_financial_effects")
activities = spark.read.format("delta").load(group_path+"semantic_business_activities")
contracts = spark.read.format("delta").load(group_path+"semantic_contracts")
evidence = spark.read.format("delta").load(group_path+"semantic_event_evidence")
assert effects.join(activities,"activity_id","left_anti").count()==0
assert activities.join(contracts,"contract_id","left_anti").count()==0
assert effects.join(evidence,"evidence_id","left_anti").count()==0
if LINKS_ONLY:
    metrics = spark.read.format("delta").load(group_path+"semantic_financial_metrics_daily")
    kpis = spark.read.format("delta").load(group_path+"kpi_snapshot")
    effect_links = spark.read.format("delta").load(group_path+"semantic_effect_metric_links")
    metric_links = spark.read.format("delta").load(group_path+"semantic_metric_kpi_links")
    assert effect_links.join(effects,"effect_id","left_anti").count()==0
    assert effect_links.join(metrics,"metric_id","left_anti").count()==0
    assert metric_links.join(metrics,"metric_id","left_anti").count()==0
    assert metric_links.join(kpis,"kpi_id","left_anti").count()==0
    for row in kpis.groupBy("kpi_code","scenario_tag").agg(F.sum("amount_group").alias("amount")).collect():
        key = row.kpi_code+"_"+row.scenario_tag
        assert abs(row.amount-decimal.Decimal(EXPECTED_KPIS[key])) < decimal.Decimal(".001"), key
    for name in ["semantic_business_activities","semantic_event_financial_effects","kpi_snapshot"]:
        assert spark.table(f"`Trading`.`LH_Group_SAP`.`dbo`.`{name}`").count() > 0
delta = effects.groupBy("activity_id").agg(F.sum("delta_ebitda_local").alias("attributed"))
assert activities.join(delta,"activity_id","left").filter(
    F.abs(F.col("ebitda_local")-F.col("baseline_ebitda_local")-F.coalesce(F.col("attributed"),F.lit(0)))>F.lit(0.000001)
).count()==0
ic = spark.read.format("delta").load(group_path+"intercompany_transactions")
assert ic.groupBy("pair_id").agg(F.sum("ebitda_effect_group").alias("net")).filter("net != 0").count()==0
gl = spark.read.format("delta").load(group_path+"gl_postings")
assert gl.groupBy("journal_id").agg(F.sum("amount_local").alias("net")).filter("net != 0").count()==0
# Verify a real cross-lakehouse join, not only the group projection.
metals_id = lakehouses["LH_Metals_US_01"]["id"]
metals = spark.read.format("delta").load(f"abfss://{workspace_id}@{endpoint}/{metals_id}/Tables/business_activities")
master = spark.read.format("delta").load(group_path+"company_master")
assert metals.join(master,"entity_id").count()==1095
result = {"status":"passed","tables":len(counts),"rows":sum(counts.values()),
          "counts":counts,"checks":["Delta persisted row counts","cross-LH join",
          "activity-contract-evidence foreign keys","additive event attribution",
          "intercompany pair reconciliation","balanced journals"]}
notebookutils.fs.put(f"abfss://{workspace_id}@{endpoint}/{group_id}/Files/trading_demo_validation.json",json.dumps(result),True)
print(json.dumps(result))
notebookutils.notebook.exit(json.dumps({"status":"passed","tables":len(counts),"rows":sum(counts.values())}))
"""
setup = ("EXPECTED_WORKSPACE = "+repr(inventory["workspaceId"])+"\n"
         +"EXPECTED_LAKEHOUSES = "+repr({l["displayName"]:l["id"] for l in inventory["lakehouses"]})+"\n"
         +"LINKS_ONLY = "+repr(links_only)+"\n"
         +"EXPECTED_KPIS = "+repr(json.loads((ROOT/"reports/local_validation.json").read_text())["annual_kpis"])+"\n"
         +"PACKED_DATA = "+repr(packed)+"\n")
nb = dict(nbformat=4, nbformat_minor=5, metadata={
    "kernelspec":{"display_name":"Synapse PySpark","language":"python","name":"synapse_pyspark"},
    "language_info":{"name":"python"},
    "dependencies":{"lakehouse":{"default_lakehouse":inventory["lakehouses"][0]["id"],
        "default_lakehouse_name":"LH_Group_SAP","default_lakehouse_workspace_id":inventory["workspaceId"]}}},
    cells=[dict(cell_type="code",execution_count=None,outputs=[],metadata={},
                source=(setup+code).splitlines(keepends=True))])
name = "TradingDemo_FinalizeSemantic" if links_only else "TradingDemo_SeedAndValidate"
(ROOT/f"notebooks/{name}.ipynb").write_text(json.dumps(nb,ensure_ascii=False))
payload = dict(displayName=name, type="Notebook",
    description="Fictional 8-subsidiary trading demo; ECB actual FX; persistent Delta and reconciliation",
    definition=dict(format="ipynb",parts=[dict(path="notebook-content.ipynb",
        payload=base64.b64encode(json.dumps(nb).encode()).decode(),payloadType="InlineBase64")]))
(ROOT/("config/notebook_finalize_create.json" if links_only else "config/notebook_create.json")).write_text(json.dumps(payload))
print("Notebook packaged",len(packed),"compressed bytes")
