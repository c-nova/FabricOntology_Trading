-- Apply only the matching sector extension in each subsidiary.

CREATE TABLE IF NOT EXISTS metals_quality (
  extension_id STRING,
  activity_id STRING,
  entity_id STRING,
  contract_id STRING,
  observation_date DATE,
  purity_percent DECIMAL(28,8),
  smelter_utilization DECIMAL(28,8)
) USING DELTA;

CREATE TABLE IF NOT EXISTS energy_dispatch (
  extension_id STRING,
  activity_id STRING,
  entity_id STRING,
  contract_id STRING,
  observation_date DATE,
  storage_fill_percent DECIMAL(28,8),
  dispatch_mmbtu DECIMAL(28,8)
) USING DELTA;

CREATE TABLE IF NOT EXISTS foods_cold_chain (
  extension_id STRING,
  activity_id STRING,
  entity_id STRING,
  contract_id STRING,
  observation_date DATE,
  temperature_c DECIMAL(28,8),
  spoilage_percent DECIMAL(28,8)
) USING DELTA;

CREATE TABLE IF NOT EXISTS finance_exposure (
  extension_id STRING,
  activity_id STRING,
  entity_id STRING,
  contract_id STRING,
  observation_date DATE,
  notional_local DECIMAL(28,8),
  credit_spread_bps DECIMAL(28,8),
  hedge_coverage DECIMAL(28,8)
) USING DELTA;
