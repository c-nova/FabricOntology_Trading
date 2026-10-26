-- Spark-only reference DDL. The Lakehouse SQL endpoint is read-only for table data/creation.
-- semantic_* are provenance-preserving projections, not substitutes for raw company lakehouses.

CREATE TABLE IF NOT EXISTS fx_rates (
  fx_id STRING,
  rate_date DATE,
  from_currency STRING,
  to_currency STRING,
  fx_rate DECIMAL(28,8),
  observation_date DATE,
  fill_days BIGINT,
  rate_method STRING,
  source STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS gl_postings (
  posting_id STRING,
  company_code STRING,
  entity_id STRING,
  fiscal_year BIGINT,
  fiscal_period BIGINT,
  posting_date DATE,
  account_code STRING,
  profit_center STRING,
  amount_local DECIMAL(28,8),
  currency_code STRING,
  interco_flag BOOLEAN,
  journal_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS company_master (
  entity_id STRING,
  entity_name STRING,
  sector_code STRING,
  country_code STRING,
  currency_code STRING,
  ownership_ratio DECIMAL(28,8),
  valid_from DATE,
  valid_to DATE,
  company_code STRING,
  consolidation_type STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS intercompany_transactions (
  interco_id STRING,
  pair_id STRING,
  entity_id STRING,
  counterparty_entity_id STRING,
  posting_date DATE,
  side STRING,
  amount_local DECIMAL(28,8),
  currency_code STRING,
  amount_group DECIMAL(28,8),
  ebitda_effect_group DECIMAL(28,8),
  management_effect_jpy DECIMAL(28,8)
) USING DELTA;

CREATE TABLE IF NOT EXISTS group_consolidation_entries (
  cons_entry_id STRING,
  pair_id STRING,
  company_code STRING,
  posting_date DATE,
  fiscal_year BIGINT,
  fiscal_period BIGINT,
  elimination_type STRING,
  amount_group DECIMAL(28,8),
  currency_code STRING,
  rule_name STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_company_profile (
  entity_id STRING,
  entity_name STRING,
  sector_code STRING,
  country_code STRING,
  currency_code STRING,
  ownership_ratio DECIMAL(28,8),
  valid_from DATE,
  valid_to DATE,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_contracts (
  contract_id STRING,
  entity_id STRING,
  commodity STRING,
  contract_type STRING,
  strike_price DECIMAL(28,8),
  price_index STRING,
  start_date DATE,
  end_date DATE,
  currency_code STRING,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_business_activities (
  activity_id STRING,
  entity_id STRING,
  sector_code STRING,
  activity_date DATE,
  contract_id STRING,
  activity_type STRING,
  volume DECIMAL(28,8),
  unit STRING,
  baseline_revenue_local DECIMAL(28,8),
  baseline_cost_local DECIMAL(28,8),
  revenue_local DECIMAL(28,8),
  cost_local DECIMAL(28,8),
  baseline_ebitda_local DECIMAL(28,8),
  ebitda_local DECIMAL(28,8),
  baseline_cf_local DECIMAL(28,8),
  cf_local DECIMAL(28,8),
  currency_code STRING,
  interco_flag BOOLEAN,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_shipments (
  shipment_id STRING,
  activity_id STRING,
  entity_id STRING,
  contract_id STRING,
  origin_country STRING,
  destination_country STRING,
  etd DATE,
  eta DATE,
  delay_days BIGINT,
  volume DECIMAL(28,8),
  unit STRING,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_risk_events (
  event_id STRING,
  primary_sector STRING,
  start_date DATE,
  end_date DATE,
  severity BIGINT,
  direction STRING,
  confidence DECIMAL(28,8),
  event_type STRING,
  region_code STRING,
  narrative STRING,
  is_synthetic BOOLEAN,
  causal_status STRING,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_event_evidence (
  evidence_id STRING,
  event_id STRING,
  entity_id STRING,
  recorded_date DATE,
  evidence_type STRING,
  source_record STRING,
  excerpt STRING,
  is_synthetic BOOLEAN,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_event_impact_bridge (
  bridge_id STRING,
  event_id STRING,
  entity_id STRING,
  activity_id STRING,
  contract_id STRING,
  impact_channel STRING,
  lag_days BIGINT,
  impact_weight DECIMAL(28,8),
  decay_half_life_days BIGINT,
  evidence_id STRING,
  causal_mechanism STRING,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_event_financial_effects (
  effect_id STRING,
  bridge_id STRING,
  event_id STRING,
  evidence_id STRING,
  activity_id STRING,
  contract_id STRING,
  entity_id STRING,
  effect_date DATE,
  delta_revenue_local DECIMAL(28,8),
  delta_cost_local DECIMAL(28,8),
  delta_ebitda_local DECIMAL(28,8),
  delta_cf_local DECIMAL(28,8),
  currency_code STRING,
  fx_rate_to_group DECIMAL(28,8),
  ownership_ratio DECIMAL(28,8),
  delta_ebitda_full_jpy DECIMAL(28,8),
  delta_management_jpy DECIMAL(28,8),
  delta_cf_full_jpy DECIMAL(28,8),
  attribution_method STRING,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_financial_metrics_daily (
  metric_id STRING,
  metric_date DATE,
  entity_id STRING,
  metric_code STRING,
  amount_local DECIMAL(28,8),
  currency_code STRING,
  fx_rate_to_group DECIMAL(28,8),
  amount_group DECIMAL(28,8),
  management_contribution_jpy DECIMAL(28,8),
  scenario_tag STRING,
  interco_flag BOOLEAN,
  source_lakehouse STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_effect_metric_links (
  effect_id STRING,
  metric_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS semantic_metric_kpi_links (
  metric_id STRING,
  kpi_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS kpi_snapshot (
  kpi_id STRING,
  kpi_date DATE,
  fiscal_year BIGINT,
  fiscal_period BIGINT,
  kpi_code STRING,
  amount_group DECIMAL(28,8),
  currency_code STRING,
  scenario_tag STRING,
  definition STRING
) USING DELTA;
