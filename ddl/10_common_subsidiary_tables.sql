-- Spark-only reference DDL; notebook deploys typed Delta into each company's own lakehouse.
-- Finance has no physical shipments. Schema-enabled targets use dbo; legacy targets omit dbo.

CREATE TABLE IF NOT EXISTS company_profile (
  entity_id STRING,
  entity_name STRING,
  sector_code STRING,
  country_code STRING,
  currency_code STRING,
  ownership_ratio DECIMAL(28,8),
  valid_from DATE,
  valid_to DATE
) USING DELTA;

CREATE TABLE IF NOT EXISTS risk_events (
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
  causal_status STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS event_evidence (
  evidence_id STRING,
  event_id STRING,
  entity_id STRING,
  recorded_date DATE,
  evidence_type STRING,
  source_record STRING,
  excerpt STRING,
  is_synthetic BOOLEAN
) USING DELTA;

CREATE TABLE IF NOT EXISTS contracts (
  contract_id STRING,
  entity_id STRING,
  commodity STRING,
  contract_type STRING,
  strike_price DECIMAL(28,8),
  price_index STRING,
  start_date DATE,
  end_date DATE,
  currency_code STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS business_activities (
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
  interco_flag BOOLEAN
) USING DELTA;

CREATE TABLE IF NOT EXISTS shipments (
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
  unit STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS event_impact_bridge (
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
  causal_mechanism STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS event_financial_effects (
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
  attribution_method STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS financial_metrics_daily (
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
  interco_flag BOOLEAN
) USING DELTA;
