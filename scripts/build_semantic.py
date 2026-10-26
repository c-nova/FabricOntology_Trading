"""Build deterministic ontology and Data Agent definition parts from demo schemas."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT/"data/demo_dataset.json").read_text())
inventory = json.loads((ROOT/"config/lakehouse_inventory.json").read_text())
WS = inventory["workspaceId"]
LH = {x["displayName"]: x["id"] for x in inventory["lakehouses"]}
shortcut_file = ROOT / "config/sector_shortcuts.json"
SHORTCUTS = json.loads(shortcut_file.read_text()) if shortcut_file.exists() else {}
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"
ontology_parts, idmap = [], {"entityTypes":{}, "relationshipTypes":{}}
counter = 100000000000000


def new_id():
    global counter
    counter += 1
    return str(counter)


def guid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "trading-demo-v1/"+name))


def part(path, content):
    return dict(path=path, payload=base64.b64encode(
        json.dumps(content,ensure_ascii=False,separators=(",",":")).encode()).decode(),
        payloadType="InlineBase64")


def value_type(value):
    if isinstance(value,bool):
        return "Boolean"
    if isinstance(value,int):
        return "BigInt"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        return "DateTime"
    if re.fullmatch(r"-?\d+(\.\d+)?",value):
        return "Double"
    return "String"


def source(lh,table):
    return dict(sourceType="LakehouseTable",workspaceId=WS,itemId=LH[lh],
                sourceTableName=table,sourceSchema="dbo")


def entity(name,lh,table,key,display=None):
    eid = new_id()
    columns = data[lh][table][0]
    properties = {col:new_id() for col in columns}
    definition = dict(id=eid,namespace="usertypes",namespaceType="Custom",name=name,
        entityIdParts=[properties[key]],displayNamePropertyId=properties[display or key],
        visibility="Visible",properties=[dict(id=properties[col],name=col,valueType=value_type(v))
            for col,v in columns.items()],timeseriesProperties=[])
    bid=guid(name+"/binding")
    ontology_parts.extend([
        part(f"EntityTypes/{eid}/definition.json",definition),
        part(f"EntityTypes/{eid}/DataBindings/{bid}.json",dict(id=bid,
            dataBindingConfiguration=dict(dataBindingType="NonTimeSeries",
                propertyBindings=[dict(sourceColumnName=c,targetPropertyId=p) for c,p in properties.items()],
                sourceTableProperties=source(lh,table))))])
    idmap["entityTypes"][name]=dict(id=eid,properties=properties,key=key,lakehouse=lh,table=table)


def relationship(name,src,tgt,lh,table,src_col,tgt_col):
    rid, cid = new_id(), guid(name+"/context")
    a,b=idmap["entityTypes"][src],idmap["entityTypes"][tgt]
    ontology_parts.extend([
        part(f"RelationshipTypes/{rid}/definition.json",dict(id=rid,namespace="usertypes",
            namespaceType="Custom",name=name,source=dict(entityTypeId=a["id"]),target=dict(entityTypeId=b["id"]))),
        part(f"RelationshipTypes/{rid}/Contextualizations/{cid}.json",dict(id=cid,
            dataBindingTable=source(lh,table),
            sourceKeyRefBindings=[dict(sourceColumnName=src_col,targetPropertyId=a["properties"][a["key"]])],
            targetKeyRefBindings=[dict(sourceColumnName=tgt_col,targetPropertyId=b["properties"][b["key"]])]))])
    idmap["relationshipTypes"][name]=dict(id=rid,contextualization=cid)


ontology_parts.extend([part(".platform",dict(metadata=dict(type="Ontology",displayName="TradingOntology_Multisector"))),
                       part("definition.json",{})])
GROUP="LH_Group_SAP"
for name,table,key,display in [
    ("Company","company_master","entity_id","entity_name"),
    ("RiskEvent","semantic_risk_events","event_id","narrative"),
    ("Activity","semantic_business_activities","activity_id",None),
    ("Contract","semantic_contracts","contract_id","commodity"),
    ("Shipment","semantic_shipments","shipment_id",None),
    ("Evidence","semantic_event_evidence","evidence_id","excerpt"),
    ("FinancialEffect","semantic_event_financial_effects","effect_id",None),
    ("FinancialMetric","semantic_financial_metrics_daily","metric_id",None),
    ("GroupKPI","kpi_snapshot","kpi_id","kpi_code"),
]:
    entity(name,GROUP,table,key,display)
for name,src,tgt,table,a,b in [
    ("EventImpactsActivity","RiskEvent","Activity","semantic_event_impact_bridge","event_id","activity_id"),
    ("ActivityUnderContract","Activity","Contract","semantic_business_activities","activity_id","contract_id"),
    ("ShipmentForActivity","Shipment","Activity","semantic_shipments","shipment_id","activity_id"),
    ("ShipmentUnderContract","Shipment","Contract","semantic_shipments","shipment_id","contract_id"),
    ("EvidenceSupportsEvent","Evidence","RiskEvent","semantic_event_evidence","evidence_id","event_id"),
    ("EventHasEffect","RiskEvent","FinancialEffect","semantic_event_financial_effects","event_id","effect_id"),
    ("EffectExplainedByEvidence","FinancialEffect","Evidence","semantic_event_financial_effects","effect_id","evidence_id"),
    ("EffectOnActivity","FinancialEffect","Activity","semantic_event_financial_effects","effect_id","activity_id"),
    ("EffectOnContract","FinancialEffect","Contract","semantic_event_financial_effects","effect_id","contract_id"),
    ("ContractOwnedByCompany","Contract","Company","semantic_contracts","contract_id","entity_id"),
    ("ActivityOwnedByCompany","Activity","Company","semantic_business_activities","activity_id","entity_id"),
    ("EffectOwnedByCompany","FinancialEffect","Company","semantic_event_financial_effects","effect_id","entity_id"),
    ("MetricForCompany","FinancialMetric","Company","semantic_financial_metrics_daily","metric_id","entity_id"),
    ("EffectRealizedInMetric","FinancialEffect","FinancialMetric","semantic_effect_metric_links","effect_id","metric_id"),
    ("MetricRollsUpToGroupKPI","FinancialMetric","GroupKPI","semantic_metric_kpi_links","metric_id","kpi_id"),
]:
    relationship(name,src,tgt,GROUP,table,a,b)
for lh in LH:
    if lh==GROUP:
        continue
    sector,country=lh.split("_")[1:3]
    table={"Metals":"metals_quality","Energy":"energy_dispatch","Foods":"foods_cold_chain","Finance":"finance_exposure"}[sector]
    name=sector+country+"Extension"
    entity(name,lh,table,"extension_id")
    relationship(name+"ForActivity",name,"Activity",lh,table,"extension_id","activity_id")
    relationship(name+"ForCompany",name,"Company",lh,table,"extension_id","entity_id")
    relationship(name+"ForContract",name,"Contract",lh,table,"extension_id","contract_id")
ontology = dict(displayName="TradingOntology_Multisector",type="Ontology",
    description="Fictional multisector trading; shared causal/accounting core and 8 company sector extensions",
    definition=dict(parts=ontology_parts))
(ROOT/"config/ontology_old_json_reference.json").write_text(json.dumps(ontology,ensure_ascii=False))
(ROOT/"config/ontology_id_map.json").write_text(json.dumps(idmap,ensure_ascii=False,indent=2))
# A human-readable part tree is reviewable without decoding base64.
for p in ontology_parts:
    if p["path"]==".platform":
        continue
    target=ROOT/"ontology"/p["path"]
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(base64.b64decode(p["payload"]))


def tmdl_part(path,text):
    return dict(path=path,payload=base64.b64encode(text.encode()).decode(),payloadType="InlineBase64")


def current_tmdl_definition():
    """Current (2026-09) public API uses TMDL, not legacy entity-type JSON."""
    endpoints={
        "LH_Group_SAP":"2ef7f1dd-1f4b-4fa5-854b-acf8a30a738a",
        "LH_Metals_JP_01":"54f870a9-8480-4978-a3ba-eb3a6a96ec04",
        "LH_Metals_US_01":"c21c2f42-6e81-4801-965d-ce42d54077a3",
        "LH_Energy_JP_01":"34e6b1d7-4565-4a14-959a-f62c9533f36c",
        "LH_Energy_US_01":"e950363a-dc5c-498f-aed7-cd751d620fcb",
        "LH_Foods_JP_01":"d79a7e4c-ef48-483f-a408-83541ab885f7",
        "LH_Foods_US_01":"3b17bd9e-89c9-454e-ac6b-95ea5cb4d691",
        "LH_Finance_JP_01":"74bb56b5-ccea-4a04-8766-600f45e5b161",
        "LH_Finance_US_01":"4b033ed0-5cdb-451f-8625-34a6c70c5b05",
    }
    # These are live-discovered SQL endpoint identities, not invented resources.
    server="jh6zduwe5ahuzonwbmgkxkovau-n27td64zqfmulmookqoqjuqpaq.datawarehouse.fabric.microsoft.com"
    tables,entities,relationships,entityrels={},{},[],[]
    connection_scripts=[]
    pinned_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
    types={"String":"string","Boolean":"boolean","BigInt":"int64","DateTime":"dateTime","Double":"double"}
    def table(alias,lh,real):
        if alias in tables:
            return
        text=f"table {alias}\n\tlineageTag: {guid('table/'+alias)}\n"
        for col,v in data[lh][real][0].items():
            text+=f"\n\tcolumn {col}\n\t\tdataType: {types[value_type(v)]}\n\t\tsourceColumn: {col}\n\t\tlineageTag: {guid(alias+'/'+col)}\n"
        binding_lh = SHORTCUTS.get(alias, {}).get("lakehouse", lh)
        binding_table = SHORTCUTS.get(alias, {}).get("table", real)
        schema = "dbo"
        text+=f"\n\tpartition {alias} = entity\n\t\tmode: directLake\n\t\tsource\n\t\t\tentityName: {binding_table}\n\t\t\tschemaName: {schema}\n\t\t\texpressionSource: DB_{binding_lh}\n"
        connection_annotations={
            "WorkspaceId":WS,"ItemId":LH[binding_lh],"ItemKind":"Lakehouse",
            "ItemName":binding_lh,"WorkspaceName":"Trading","SqlEndpoint":server,"SqlDatabase":binding_lh,
            "PinnedAtUtc":pinned_at,
        }
        for key,value in connection_annotations.items():
            text+=f"\n\t\tannotation ONT_{key} = {value}\n"
        # Public ALM strips reserved ONT connection annotations; the ontology UI
        # uses native TMSL scripts to persist this source-selection metadata.
        connection_scripts.append({"alter":{"object":{"table":alias,"partition":alias},
            "partition":{"name":alias,"mode":"directLake",
                "source":{"type":"entity","entityName":binding_table,"schemaName":schema,
                          "expressionSource":"DB_"+binding_lh},
                "annotations":[{"name":"ONT_"+k,"value":v} for k,v in connection_annotations.items()]}}})
        tables[alias]=text
    for name,e in idmap["entityTypes"].items():
        table(name,e["lakehouse"],e["table"])
        text=f"entity {name}\n\tlineageTag: {guid('entity/'+name)}\n\tbackingTable: {name}\n\tkeyProperty: {e['key']}\n"
        for col,v in data[e["lakehouse"]][e["table"]][0].items():
            text+=f"\n\tproperty {col}\n\t\tdataType: {types[value_type(v)]}\n\t\tlineageTag: {guid('property/'+name+'/'+col)}\n\t\tbackingConfiguration\n\t\t\tvalueColumn: {name}.{col}\n"
        entities[name]=text
    id_to_name={e["id"]:n for n,e in idmap["entityTypes"].items()}
    definitions={p["path"]:json.loads(base64.b64decode(p["payload"])) for p in ontology_parts if p["path"]!=".platform"}
    def rel(name,many,col,one,key):
        relationships.append(f"relationship {name}\n\tisActive: false\n\tfromColumn: {many}.{col}\n\ttoColumn: {one}.{key}\n")
    for name,r in idmap["relationshipTypes"].items():
        definition=definitions[f"RelationshipTypes/{r['id']}/definition.json"]
        context=definitions[f"RelationshipTypes/{r['id']}/Contextualizations/{r['contextualization']}.json"]
        a,b=id_to_name[definition["source"]["entityTypeId"]],id_to_name[definition["target"]["entityTypeId"]]
        source_table=context["dataBindingTable"]
        lh=next(n for n,v in LH.items() if v==source_table["itemId"])
        real=source_table["sourceTableName"]
        acol=context["sourceKeyRefBindings"][0]["sourceColumnName"]
        bcol=context["targetKeyRefBindings"][0]["sourceColumnName"]
        ea,eb=idmap["entityTypes"][a],idmap["entityTypes"][b]
        header=f"entityRelationship {name}\n\tlineageTag: {guid('entityrel/'+name)}\n\tlabel: {name}\n\tfromEntity: {a}\n\ttoEntity: {b}\n\tbackingConfiguration\n"
        if (lh,real)==(ea["lakehouse"],ea["table"]):
            rel("R_"+name,a,bcol,b,eb["key"])
            header+=f"\t\trelationship: R_{name}\n"
        elif (lh,real)==(eb["lakehouse"],eb["table"]):
            rel("R_"+name,b,acol,a,ea["key"])
            header+=f"\t\trelationship: R_{name}\n"
        else:
            junction="Link_"+name
            table(junction,lh,real)
            rel("R_"+name+"_A",junction,acol,a,ea["key"])
            rel("R_"+name+"_B",junction,bcol,b,eb["key"])
            header+=f"\t\ttype: table\n\t\ttable: {junction}\n\t\tfromRelationship: R_{name}_A\n\t\ttoRelationship: R_{name}_B\n"
        entityrels.append(header)
    expression=""
    used_lakehouses = {
        SHORTCUTS.get(name, {}).get("lakehouse", e["lakehouse"])
        for name, e in idmap["entityTypes"].items()
    }
    for lh in endpoints:
        if lh not in used_lakehouses:
            continue
        expression+=f'expression DB_{lh} =\n\t\tlet\n\t\t    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{WS}/{LH[lh]}", [HierarchicalNavigation=true])\n\t\tin\n\t\t    Source\n\tlineageTag: {guid("expression/"+lh)}\n\n'
    model="model Model\n\n"+"".join(f"ref table {n}\n" for n in tables)
    model+="\n"+"".join(f"ref entity {n}\n" for n in entities)+"\nref namespace default\n"
    parts=[
        part(".platform",{"metadata":{"type":"Ontology","displayName":"TradingOntology_Multisector"},
                          "config":{"version":"2.0","logicalId":guid("ontology")}}),
        tmdl_part("database.tmdl","database\n\tcompatibilityLevel: 1000000\n"),
        tmdl_part("model.tmdl",model),
        tmdl_part("namespaces/default.tmdl","namespace default\n\tlineageTag: default\n"),
        tmdl_part("expressions.tmdl",expression),
        tmdl_part("relationships.tmdl","\n".join(relationships)),
        tmdl_part("entityRelationships.tmdl","\n".join(entityrels)),
    ]
    parts += [tmdl_part("tables/"+name+".tmdl",text) for name,text in tables.items()]
    parts += [tmdl_part("entities/"+name+".tmdl",text) for name,text in entities.items()]
    for p in parts:
        target=ROOT/"ontology_tmdl"/p["path"]
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(base64.b64decode(p["payload"]))
    (ROOT/"config/ontology_connection_bindings.json").write_text(
        json.dumps(connection_scripts,ensure_ascii=False,indent=2))
    return dict(displayName="TradingOntology_Multisector",type="Ontology",
        description="Fictional 4-sector trading: 9 Lakehouses, evidence and full/weighted EBITDA",
        definition={"parts":parts})


(ROOT/"config/ontology_create.json").write_text(json.dumps(current_tmdl_definition(),ensure_ascii=False))


def data_agent(ontology_id):
    parts = [part("Files/Config/data_agent.json",{"$schema":SCHEMA+"dataAgent/definition/dataAgent/2.1.0/schema.json"})]
    instructions=(ROOT/"prompts/da_instructions_ja.txt").read_text()
    fewshots=[
        dict(id=guid("qa/kpi"),question="対象年度の全額連結EBITDAと持分管理寄与を比較して",
             query="SELECT kpi_code, SUM(amount_group) AS amount_jpy FROM dbo.kpi_snapshot WHERE scenario_tag='actual' AND kpi_code IN ('EBITDA_FULL_CONSOLIDATED','EBITDA_MANAGEMENT_WEIGHTED') GROUP BY kpi_code"),
        dict(id=guid("qa/events"),question="各セクターの正負イベントのEBITDA影響を示して",
             query="SELECT e.event_id,e.primary_sector,e.direction,SUM(f.delta_ebitda_full_jpy) full_jpy,SUM(f.delta_management_jpy) management_jpy FROM dbo.semantic_event_financial_effects f JOIN dbo.semantic_risk_events e ON e.event_id=f.event_id GROUP BY e.event_id,e.primary_sector,e.direction ORDER BY full_jpy"),
        dict(id=guid("qa/chain"),question="食品の悪化イベントから根拠・活動・契約へのチェーンを示して",
             query="SELECT TOP 10 f.effect_id,f.event_id,a.activity_id,c.contract_id,v.evidence_id,v.excerpt,f.delta_ebitda_full_jpy FROM dbo.semantic_event_financial_effects f JOIN dbo.semantic_business_activities a ON a.activity_id=f.activity_id JOIN dbo.semantic_contracts c ON c.contract_id=f.contract_id JOIN dbo.semantic_event_evidence v ON v.evidence_id=f.evidence_id WHERE f.event_id='FOD_NEG' ORDER BY f.delta_ebitda_full_jpy"),
    ]
    def element(name,typ,children=None,datatype=None):
        r=dict(id=guid(typ+"/"+name),is_selected=True,display_name=name,type=typ,children=children or [])
        if datatype:r["data_type"]=datatype
        return r
    tables=[]
    source_tables = dict(data[GROUP])
    for binding in SHORTCUTS.values():
        source_tables[binding["table"]] = data[binding["source_lakehouse"]][binding["source_table"]]
    for table,rows in source_tables.items():
        columns=[element(col,"lakehouse_tables.column",datatype={
            "Boolean":"bit","BigInt":"bigint","Double":"decimal","DateTime":"date","String":"varchar"}[value_type(v)])
            for col,v in rows[0].items()]
        tables.append(element(table,"lakehouse_tables.table",columns))
    datasource=dict(**{"$schema":SCHEMA+"dataAgent/definition/dataSource/1.0.0/schema.json"},
        artifactId=LH[GROUP],workspaceId=WS,displayName=GROUP,type="lakehouse_tables",
        dataSourceInstructions=instructions,userDescription="SAP-like parent plus provenance-preserving projection of all 8 subsidiaries",
        elements=[element("Schemas","schema_grouping",[
            element("dbo","lakehouse_tables.schema",[
                element("Tables","table_grouping",tables)])])])
    for stage in ("draft","published"):
        parts.extend([
            part(f"Files/Config/{stage}/stage_config.json",dict(
                **{"$schema":SCHEMA+"dataAgent/definition/stageConfiguration/1.0.0/schema.json"},
                aiInstructions=instructions,experimental={"enableExperimentalFeatures":True})),
            part(f"Files/Config/{stage}/lakehouse-tables-{GROUP}/datasource.json",datasource),
            part(f"Files/Config/{stage}/lakehouse-tables-{GROUP}/fewshots.json",
                 {"$schema":SCHEMA+"dataAgent/definition/fewShots/1.0.0/schema.json","fewShots":fewshots}),
            part(f"Files/Config/{stage}/ontologies/TradingOntology_Multisector/ontology.json",dict(
                **{"$schema":SCHEMA+"dataAgent/definition/ontology/1.0.0/schema.json"},
                artifactId=ontology_id,workspaceId=WS,displayName="TradingOntology_Multisector",
                elements=[dict(id=name,is_selected=True,display_name=name,type="ontology.entity",children=[])
                          for name in idmap["entityTypes"]],entitiesWithUserAuthoredDescriptions=[])),
        ])
    parts.append(part("Files/Config/publish_info.json",dict(
        **{"$schema":SCHEMA+"dataAgent/definition/publishInfo/1.0.0/schema.json"},
        description="架空総合商社デモ。4セクター・日米8子会社、9分離Lakehouseとゼロコピー参照。2025-10～2026-09のEBITDA/簡易CF、全額連結と持分管理寄与、ECB為替、架空根拠とイベント配賦を日本語で分析。")))
    return dict(displayName="TradingDA_Multisector",
                description="架空総合商社: 4 sectors / 8 subsidiaries / ECB FX / EBITDA and CF",
                definition=dict(parts=parts))


if __name__=="__main__":
    import sys
    if len(sys.argv)>1:
        (ROOT/"config/data_agent_create.json").write_text(json.dumps(data_agent(sys.argv[1]),ensure_ascii=False))
    print(json.dumps({"entities":len(idmap["entityTypes"]),"relationships":len(idmap["relationshipTypes"]),
                      "source_lakehouses":len(LH)}))
