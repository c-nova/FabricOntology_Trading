"""Deterministic fictional trading data; run with Python 3 standard library only."""
import base64
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import random
import re
import zlib
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[1]
START, END = dt.date(2025, 10, 1), dt.date(2026, 9, 30)
SEED = 20261023
SOURCE = ("https://data-api.ecb.europa.eu/service/data/EXR/"
          "D.USD+JPY.EUR.SP00.A?startPeriod=2025-09-25&endPeriod=2026-09-30&format=csvdata")
D = Decimal


def money(x):
    return D(str(x)).quantize(D(".01"), rounding=ROUND_HALF_UP)


def dumps(x):
    return json.dumps(x, ensure_ascii=False, default=str, separators=(",", ":"))


def ddl(table, rows):
    columns=[]
    for name,value in rows[0].items():
        kind = ("BOOLEAN" if isinstance(value,bool) else "BIGINT" if isinstance(value,int)
                else "DECIMAL(28,8)" if isinstance(value,D)
                else "DATE" if isinstance(value,dt.date) else "STRING")
        columns.append(f"  {name} {kind}")
    return f"CREATE TABLE IF NOT EXISTS {table} (\n"+",\n".join(columns)+"\n) USING DELTA;\n"


def generate():
    rng = random.Random(SEED)
    ownership = [D("1.00")] * 4 + [D(".51")] * 4
    random.Random(SEED).shuffle(ownership)
    companies = []
    for s, code, name in [("metals", "MTL", "Veltrona"), ("energy", "ENE", "Orivexa"),
                          ("foods", "FOD", "Caldriva"), ("finance", "FIN", "Nuvellora")]:
        for country, currency in [("JP", "JPY"), ("US", "USD")]:
            companies.append(dict(entity_id=f"SUB_{code}_{country}_01",
                                  entity_name=f"{name} {s.title()} {'Japan KK' if country == 'JP' else 'USA Inc.'}",
                                  sector_code=s, country_code=country, currency_code=currency,
                                  ownership_ratio=ownership[len(companies)],
                                  valid_from=START, valid_to=END))
    raw = list(csv.DictReader((ROOT / "data/ecb_fx_raw.csv").open()))
    eur = defaultdict(dict)
    for row in raw:
        eur[dt.date.fromisoformat(row["TIME_PERIOD"])][row["CURRENCY"]] = D(row["OBS_VALUE"])
    observations = {day: (v["JPY"] / v["USD"]).quantize(D(".00000001"))
                    for day, v in eur.items() if {"JPY", "USD"} <= v.keys()}
    assert max(observations) >= END, "Authoritative FX does not cover demo end; never extrapolate."
    dates = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    fx = {}
    group = defaultdict(list)
    for day in dates:
        observed = max(x for x in observations if x <= day)
        gap = (day - observed).days
        assert gap <= 5, f"FX fill exceeds five-day bound: {day}"
        fx[day] = observations[observed]
        for currency, rate in [("JPY", D(1)), ("USD", fx[day])]:
            group["fx_rates"].append(dict(fx_id=f"{day}_{currency}", rate_date=day,
                from_currency=currency, to_currency="JPY", fx_rate=rate,
                observation_date=observed if currency == "USD" else day,
                fill_days=gap if currency == "USD" else 0,
                rate_method="ECB EUR cross JPY/USD; previous observation <=5 days" if currency == "USD" else "identity",
                source=SOURCE if currency == "USD" else "JPY identity"))
    event_specs = [
        ("MTL_NEG", "metals", "2025-11-12", -1, "smelter outage", "cost"),
        ("MTL_POS", "metals", "2026-03-03", 1, "recycled alloy premium contract", "price"),
        ("ENE_NEG", "energy", "2026-01-14", -1, "LNG terminal maintenance delay", "cost"),
        ("ENE_POS", "energy", "2026-06-02", 1, "storage dispatch optimization", "volume"),
        ("FOD_NEG", "foods", "2026-02-09", -1, "cold chain spoilage incident", "cost"),
        ("FOD_POS", "foods", "2026-07-06", 1, "grain yield and procurement improvement", "price"),
        ("FIN_NEG", "finance", "2026-04-13", -1, "counterparty servicing cost shock", "cost"),
        ("FIN_POS", "finance", "2026-08-04", 1, "hedge execution fee uplift", "hedge"),
        ("CROSS_NEG", "all", "2026-05-11", -1, "cross-sector port and liquidity disruption", "cost"),
        ("CROSS_POS", "all", "2026-09-01", 1, "cross-sector logistics and treasury recovery", "volume"),
    ]
    events = []
    for eid, sector, day, sign, narrative, channel in event_specs:
        start = dt.date.fromisoformat(day)
        event = dict(event_id=eid, primary_sector=sector, start_date=start,
            end_date=start+dt.timedelta(days=20), severity=5 if sign < 0 else 4,
            direction="positive" if sign > 0 else "negative", confidence=D(".95"),
            event_type=channel, region_code="JP_US", narrative="SYNTHETIC: "+narrative,
            is_synthetic=True, causal_status="designed_attribution_not_observational_proof")
        events.append(event)
    datasets = {}
    extension_names = {"metals": "metals_quality", "energy": "energy_dispatch",
                       "foods": "foods_cold_chain", "finance": "finance_exposure"}
    for ci, c in enumerate(companies):
        entity, sector, currency = c["entity_id"], c["sector_code"], c["currency_code"]
        lh = f"LH_{sector.title()}_{c['country_code']}_01"
        tables = defaultdict(list)
        tables["company_profile"] = [c]
        applicable = [e for e in events if e["primary_sector"] in (sector, "all")]
        tables["risk_events"] = applicable
        for e in applicable:
            for n, kind in enumerate(("operations_log", "contract_amendment")):
                tables["event_evidence"].append(dict(evidence_id=f"{entity}_{e['event_id']}_{n}",
                    event_id=e["event_id"], entity_id=entity, recorded_date=e["start_date"],
                    evidence_type=kind, source_record=f"SIM://{entity}/{e['event_id']}/{kind}",
                    excerpt=f"SYNTHETIC {kind}: {e['narrative']}; designed causal mechanism={e['event_type']}.",
                    is_synthetic=True))
        commodity, unit, price = {
            "metals": ("copper_alloy", "tonne", 8200),
            "energy": ("LNG", "MMBtu", 12),
            "foods": ("milling_wheat", "tonne", 280),
            "finance": ("trade_finance", "USD_notional", .015),
        }[sector]
        scale = D(145) if currency == "JPY" else D(1)
        for n in range(12):
            tables["contracts"].append(dict(contract_id=f"{entity}_C{n:02}", entity_id=entity,
                commodity=commodity, contract_type="service_fee" if sector=="finance" else "physical_supply",
                strike_price=money(D(str(price))*scale), price_index="SYNTHETIC_DEMO_INDEX",
                start_date=START, end_date=END, currency_code=currency))
        daily = defaultdict(lambda: defaultdict(lambda: D(0)))
        for di, day in enumerate(dates):
            for n in range(3):
                aid, contract = f"{entity}_A{di:03}_{n}", f"{entity}_C{(di//30+n)%12:02}"
                vol = money({"metals": 35, "energy": 24000, "foods": 650,
                             "finance": 12000000}[sector] * rng.uniform(.7,1.3))
                revenue = money(vol*D(str(price))*scale*D(str(1+.08*math.sin(di/30))))
                cost = money(revenue * D(str(rng.uniform(.80,.91))))
                base = revenue-cost
                delta_rev, delta_cost, delta_cf = D(0), D(0), D(0)
                for e in applicable:
                    lag = 2 + ci % 4
                    elapsed = (day-e["start_date"]).days-lag
                    if not 0 <= elapsed < 14:
                        continue
                    weight = D(str(math.exp(-elapsed/10))).quantize(D(".000001"))
                    sign = 1 if e["direction"] == "positive" else -1
                    change = money(base * D(".65") * weight * sign)
                    dr, dc = (change, D(0)) if sign > 0 else (D(0), -change)
                    cfchange = money(change * D(".8"))
                    delta_rev += dr
                    delta_cost += dc
                    delta_cf += cfchange
                    bid, fid = f"{aid}_{e['event_id']}_B", f"{aid}_{e['event_id']}_F"
                    evidence_id = f"{entity}_{e['event_id']}_0"
                    tables["event_impact_bridge"].append(dict(bridge_id=bid, event_id=e["event_id"],
                        entity_id=entity, activity_id=aid, contract_id=contract,
                        impact_channel=e["event_type"], lag_days=lag, impact_weight=weight,
                        decay_half_life_days=7, evidence_id=evidence_id,
                        causal_mechanism="designed synthetic "+e["event_type"]))
                    rate = D(1) if currency=="JPY" else fx[day]
                    tables["event_financial_effects"].append(dict(effect_id=fid, bridge_id=bid,
                        event_id=e["event_id"], evidence_id=evidence_id, activity_id=aid,
                        contract_id=contract, entity_id=entity, effect_date=day,
                        delta_revenue_local=dr, delta_cost_local=dc, delta_ebitda_local=change,
                        delta_cf_local=cfchange, currency_code=currency, fx_rate_to_group=rate,
                        ownership_ratio=c["ownership_ratio"], delta_ebitda_full_jpy=money(change*rate),
                        delta_management_jpy=money(change*rate*c["ownership_ratio"]),
                        delta_cf_full_jpy=money(cfchange*rate),
                        attribution_method="unique_event_activity_additive"))
                tables["business_activities"].append(dict(activity_id=aid, entity_id=entity,
                    sector_code=sector, activity_date=day, contract_id=contract,
                    activity_type="financing_fee_accrual" if sector=="finance" else "external_sale",
                    volume=vol, unit=unit, baseline_revenue_local=revenue, baseline_cost_local=cost,
                    revenue_local=revenue+delta_rev, cost_local=cost+delta_cost,
                    baseline_ebitda_local=base, ebitda_local=base+delta_rev-delta_cost,
                    baseline_cf_local=money(base*D(".8")), cf_local=money(base*D(".8"))+delta_cf,
                    currency_code=currency, interco_flag=False))
                if n == 0 and di % 7 == 0 and sector != "finance":
                    tables["shipments"].append(dict(shipment_id=f"{aid}_S", activity_id=aid,
                        entity_id=entity, contract_id=contract, origin_country="AU",
                        destination_country=c["country_code"], etd=day,
                        eta=min(END, day+dt.timedelta(days=7)), delay_days=3 if delta_cost else 0,
                        volume=vol, unit=unit))
                if n == 0:
                    extension = dict(extension_id=aid+"_X", activity_id=aid, entity_id=entity,
                                     contract_id=contract, observation_date=day)
                    extension.update({
                        "metals": dict(purity_percent=D("99.90"), smelter_utilization=D(str(rng.randint(75,98)))),
                        "energy": dict(storage_fill_percent=D(str(rng.randint(40,95))), dispatch_mmbtu=vol),
                        "foods": dict(temperature_c=D("-18"), spoilage_percent=D("3.5") if delta_cost else D(".3")),
                        "finance": dict(notional_local=money(vol*scale), credit_spread_bps=D(str(rng.randint(90,240))),
                                        hedge_coverage=D(".85")),
                    }[sector])
                    tables[extension_names[sector]].append(extension)
            for a in tables["business_activities"][-3:]:
                for k in ["revenue_local","cost_local","ebitda_local","cf_local",
                          "baseline_ebitda_local","baseline_cf_local"]:
                    daily[day][k] += a[k]
        for day in dates:
            rate = D(1) if currency=="JPY" else fx[day]
            for code in ["revenue","cost","ebitda","cf"]:
                for scenario in (["actual","baseline"] if code in ("ebitda","cf") else ["actual"]):
                    amount = daily[day][f"{'baseline_' if scenario=='baseline' else ''}{code}_local"]
                    tables["financial_metrics_daily"].append(dict(
                        metric_id=f"{entity}_{day}_{code}_{scenario}", metric_date=day,
                        entity_id=entity, metric_code=code.upper(), amount_local=amount,
                        currency_code=currency, fx_rate_to_group=rate,
                        amount_group=money(amount*rate),
                        management_contribution_jpy=money(amount*rate*c["ownership_ratio"]),
                        scenario_tag=scenario, interco_flag=False))
            revenue, cost = daily[day]["revenue_local"], daily[day]["cost_local"]
            for ac, amount in [("AR",revenue),("SALES",-revenue),("COGS",cost),("AP",-cost)]:
                group["gl_postings"].append(dict(posting_id=f"{entity}_{day}_{ac}",
                    company_code=entity, entity_id=entity, fiscal_year=2026,
                    fiscal_period=(day.month-10)%12+1, posting_date=day, account_code=ac,
                    profit_center=sector, amount_local=amount, currency_code=currency,
                    interco_flag=False, journal_id=f"{entity}_{day}"))
        datasets[lh] = dict(tables)
        group["company_master"].append(dict(c, company_code=entity, consolidation_type="FULL_CONTROL"))
    # Paired internal services: seller and buyer book the same currency/date/rate.
    # Expense is recognized immediately; no unrealized inventory profit.
    for month in range(12):
        date = dt.date(2025+(month+9)//12, (month+9)%12+1, 15)
        for country in ("JP","US"):
            seller = next(c for c in companies if c["sector_code"]=="finance" and c["country_code"]==country)
            buyer = next(c for c in companies if c["sector_code"]=="energy" and c["country_code"]==country)
            amount = D("14500000") if country=="JP" else D("100000")
            rate = D(1) if country=="JP" else fx[date]
            pair = f"IC_{country}_{date}"
            for c, side, sign, account in [(seller,"sale",1,"SALES"),(buyer,"purchase",-1,"COGS")]:
                entity = c["entity_id"]
                entry = dict(interco_id=pair+"_"+side, pair_id=pair, entity_id=entity,
                    counterparty_entity_id=buyer["entity_id"] if side=="sale" else seller["entity_id"],
                    posting_date=date, side=side, amount_local=amount, currency_code=c["currency_code"],
                    amount_group=money(amount*rate), ebitda_effect_group=money(sign*amount*rate),
                    management_effect_jpy=money(sign*amount*rate*c["ownership_ratio"]))
                group["intercompany_transactions"].append(entry)
                group["group_consolidation_entries"].append(dict(
                    cons_entry_id=pair+"_"+side, pair_id=pair, company_code=entity,
                    posting_date=date, fiscal_year=2026, fiscal_period=month+1,
                    elimination_type=side, amount_group=money(-sign*amount*rate), currency_code="JPY",
                    rule_name="paired_revenue_and_expense_no_unrealized_profit"))
                for ac, debit in [(account,-amount if side=="sale" else amount),
                                  ("IC_AR" if side=="sale" else "IC_AP",amount if side=="sale" else -amount)]:
                    group["gl_postings"].append(dict(posting_id=pair+"_"+side+"_"+ac,
                        company_code=entity, entity_id=entity, fiscal_year=2026, fiscal_period=month+1,
                        posting_date=date, account_code=ac, profit_center=c["sector_code"],
                        amount_local=debit, currency_code=c["currency_code"], interco_flag=True,
                        journal_id=pair+"_"+side))
    # Materialized semantic projection retains source provenance and all nine raw sources.
    common = ["company_profile","contracts","business_activities","shipments","risk_events",
              "event_evidence","event_impact_bridge","event_financial_effects","financial_metrics_daily"]
    for table in common:
        seen = set()
        for lh, tables in datasets.items():
            for row in tables.get(table, []):
                if table=="risk_events":
                    if row["event_id"] in seen:
                        continue
                    seen.add(row["event_id"])
                group["semantic_"+table].append(dict(row, source_lakehouse=lh))
    metrics = group["semantic_financial_metrics_daily"]
    for effect in group["semantic_event_financial_effects"]:
        group["semantic_effect_metric_links"].append(dict(
            effect_id=effect["effect_id"],
            metric_id=f"{effect['entity_id']}_{effect['effect_date']}_ebitda_actual"))
    for metric in metrics:
        if metric["metric_code"] in ("EBITDA", "CF"):
            group["semantic_metric_kpi_links"].append(dict(
                metric_id=metric["metric_id"],
                kpi_id=f"{metric['metric_date']}_{metric['metric_code']}_FULL_CONSOLIDATED_{metric['scenario_tag']}"))
    for day in dates:
        selected = [r for r in metrics if r["metric_date"]==day]
        ic = [r for r in group["intercompany_transactions"] if r["posting_date"]==day]
        elim = sum((r["amount_group"] for r in group["group_consolidation_entries"] if r["posting_date"]==day), D(0))
        for code in ["EBITDA","CF"]:
            for scenario in ["actual","baseline"]:
                rows = [r for r in selected if r["metric_code"]==code and r["scenario_tag"]==scenario]
                full = sum((r["amount_group"] for r in rows), D(0))
                management = sum((r["management_contribution_jpy"] for r in rows), D(0))
                if code=="EBITDA":
                    full += sum((r["ebitda_effect_group"] for r in ic),D(0))+elim
                    management += sum((r["management_effect_jpy"] for r in ic),D(0))
                    management += sum((-r["management_effect_jpy"] for r in ic),D(0))
                for measure, amount in [(code+"_FULL_CONSOLIDATED",full),(code+"_MANAGEMENT_WEIGHTED",management)]:
                    group["kpi_snapshot"].append(dict(kpi_id=f"{day}_{measure}_{scenario}",
                        kpi_date=day, fiscal_year=2026, fiscal_period=(day.month-10)%12+1,
                        kpi_code=measure, amount_group=amount, currency_code="JPY", scenario_tag=scenario,
                        definition="full controlled-entity consolidation" if "FULL" in measure else
                        "simplified ownership-weighted management contribution; NOT statutory EBITDA"))
    datasets["LH_Group_SAP"] = dict(group)
    report = validate(datasets, companies, observations)
    return datasets, report, companies


def validate(data, companies, observations):
    group = data["LH_Group_SAP"]
    assert len(companies)==8 and sum(c["ownership_ratio"]==1 for c in companies)==4
    assert len({c["country_code"] for c in companies if c["ownership_ratio"]==1})==2
    activities = {r["activity_id"]:r for r in group["semantic_business_activities"]}
    contracts = {r["contract_id"] for r in group["semantic_contracts"]}
    evidence = {r["evidence_id"] for r in group["semantic_event_evidence"]}
    bridges = {r["bridge_id"] for r in group["semantic_event_impact_bridge"]}
    effects = group["semantic_event_financial_effects"]
    assert len({r["effect_id"] for r in effects})==len(effects)
    by_activity = defaultdict(lambda:D(0))
    for e in effects:
        assert e["activity_id"] in activities and e["contract_id"] in contracts
        assert e["evidence_id"] in evidence and e["bridge_id"] in bridges
        assert e["delta_ebitda_local"]==e["delta_revenue_local"]-e["delta_cost_local"]
        by_activity[e["activity_id"]]+=e["delta_ebitda_local"]
    for aid, a in activities.items():
        assert a["contract_id"] in contracts
        assert a["ebitda_local"]-a["baseline_ebitda_local"]==by_activity[aid]
    for pair in {r["pair_id"] for r in group["intercompany_transactions"]}:
        rows=[r for r in group["intercompany_transactions"] if r["pair_id"]==pair]
        assert len(rows)==2 and sum(r["ebitda_effect_group"] for r in rows)==0
        assert sum(r["amount_group"] for r in group["group_consolidation_entries"] if r["pair_id"]==pair)==0
    journals=defaultdict(lambda:D(0))
    for row in group["gl_postings"]:
        journals[row["journal_id"]]+=row["amount_local"]
    assert all(x==0 for x in journals.values())
    totals = defaultdict(lambda:D(0))
    for row in group["kpi_snapshot"]:
        totals[row["kpi_code"]+"_"+row["scenario_tag"]]+=row["amount_group"]
    # FX conversion rounds per source row; attribution total uses its own grain.
    effect_total=sum((r["delta_ebitda_full_jpy"] for r in effects),D(0))
    difference=totals["EBITDA_FULL_CONSOLIDATED_actual"]-totals["EBITDA_FULL_CONSOLIDATED_baseline"]
    assert abs(effect_total-difference)<D("5"), (effect_total,difference)
    chains=[]
    for e in group["semantic_risk_events"]:
        rows=[r for r in effects if r["event_id"]==e["event_id"]]
        assert rows
        chains.append(dict(event_id=e["event_id"], sector=e["primary_sector"],
            direction=e["direction"], effect_rows=len(rows),
            delta_ebitda_full_jpy=sum((r["delta_ebitda_full_jpy"] for r in rows),D(0)),
            example=rows[0]))
    return dict(status="passed", seed=SEED, period=[str(START),str(END)],
        fictional_data=True, fx_source=SOURCE, fx_last_observation=str(max(observations)),
        fx_sha256=hashlib.sha256((ROOT/"data/ecb_fx_raw.csv").read_bytes()).hexdigest(),
        ownership=[dict(entity_id=c["entity_id"],ownership_ratio=c["ownership_ratio"]) for c in companies],
        row_counts={lh:{t:len(r) for t,r in tables.items()} for lh,tables in data.items()},
        annual_kpis=dict(totals), attribution_vs_daily_rounding_difference=effect_total-difference,
        qa_checks=["8 entities; random seeded 4x100/4x51; both countries",
                   "all activity/contract/evidence/bridge FKs; unique effect IDs",
                   "activity actual minus baseline exactly equals unique attributed effects",
                   "24 intercompany pairs net zero and paired elimination net zero",
                   "double-entry local-currency journals balance",
                   "10 positive/negative event chains; each sector plus cross-sector",
                   "FX <=5-day bounded preceding observation; no invented exchange rates"],
        event_chains=chains)


if __name__ == "__main__":
    data, report, companies = generate()
    (ROOT/"data/demo_dataset.json").write_text(dumps(data))
    (ROOT/"reports/local_validation.json").write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2))
    (ROOT/"config/subsidiaries.json").write_text(json.dumps(companies,default=str,indent=2))
    raw = data["LH_Metals_JP_01"]
    common = [t for t in raw if t!="metals_quality"]
    (ROOT/"ddl/10_common_subsidiary_tables.sql").write_text(
        "-- Spark-only reference DDL; notebook deploys typed Delta into each company's own lakehouse.\n"
        "-- Finance has no physical shipments. Schema-enabled targets use dbo; legacy targets omit dbo.\n\n"
        +"\n".join(ddl(t,raw[t]) for t in common))
    (ROOT/"ddl/20_group_sap_tables.sql").write_text(
        "-- Spark-only reference DDL. The Lakehouse SQL endpoint is read-only for table data/creation.\n"
        "-- semantic_* are provenance-preserving projections, not substitutes for raw company lakehouses.\n\n"
        +"\n".join(ddl(t,r) for t,r in data["LH_Group_SAP"].items()))
    (ROOT/"ddl/30_sector_extension_tables.sql").write_text(
        "-- Apply only the matching sector extension in each subsidiary.\n\n"
        +"\n".join(ddl(t,data[f"LH_{s}_JP_01"][t]) for s,t in [
            ("Metals","metals_quality"),("Energy","energy_dispatch"),
            ("Foods","foods_cold_chain"),("Finance","finance_exposure")]))
    print(dumps({"status":report["status"],"tables":sum(len(t) for t in data.values()),
                 "rows":sum(len(r) for t in data.values() for r in t.values()),
                 "annual_kpis":report["annual_kpis"]}))
