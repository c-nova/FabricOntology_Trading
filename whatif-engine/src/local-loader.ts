import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { BaseData, CompanyRow, EbitdaRow, EffectRow, EventRow } from './types.js';

// テストと検証用。Functions には載せない（Lakehouse からは SQL で同じ形を作る）。

type Row = Record<string, unknown>;

export interface ReferenceData {
  baselineRows: EbitdaRow[];
  // kpi_snapshot の EBITDA の日次値
  kpiDaily: { date: string; scenario: string; code: string; amount: string }[];
}

export interface LocalDataset {
  base: BaseData;
  reference: ReferenceData;
}

export function defaultDatasetPath(): string {
  return process.env['DEMO_DATASET'] ?? resolve(process.cwd(), '..', 'data', 'demo_dataset.json');
}

// 数値トークンは元の文字列のまま受け取る（"1.00" や 8 桁の為替を浮動小数点にしない）
function readJson(path: string): Record<string, Record<string, Row[]>> {
  const text = readFileSync(path, 'utf8');
  return JSON.parse(text, (_key, value, context?: { source?: string }) =>
    typeof value === 'number' ? (context?.source ?? String(value)) : value,
  );
}

const str = (r: Row, k: string): string => {
  const v = r[k];
  if (typeof v !== 'string') throw new Error(`column ${k} is not a string: ${String(v)}`);
  return v;
};

export function loadLocalDataset(path: string = defaultDatasetPath()): LocalDataset {
  const parent = readJson(path)['LH_Group_SAP'];
  if (!parent) throw new Error('LH_Group_SAP not found in dataset');
  const table = (name: string): Row[] => {
    const rows = parent[name];
    if (!rows) throw new Error(`table ${name} not found`);
    return rows;
  };

  const companies: CompanyRow[] = table('company_master').map((r) => ({
    entityId: str(r, 'entity_id'),
    entityName: str(r, 'entity_name'),
    sectorCode: str(r, 'sector_code'),
    countryCode: str(r, 'country_code'),
    currencyCode: str(r, 'currency_code'),
    ownershipRatio: str(r, 'ownership_ratio'),
  }));

  const ebitda = table('semantic_financial_metrics_daily').filter((r) => r['metric_code'] === 'EBITDA');
  const toRow = (r: Row): EbitdaRow => ({
    metricId: str(r, 'metric_id'),
    date: str(r, 'metric_date'),
    entityId: str(r, 'entity_id'),
    amountLocal: str(r, 'amount_local'),
    fxRateToGroup: str(r, 'fx_rate_to_group'),
    amountGroup: str(r, 'amount_group'),
    managementJpy: str(r, 'management_contribution_jpy'),
  });
  const ebitdaRows = ebitda.filter((r) => r['scenario_tag'] === 'actual').map(toRow);
  const baselineRows = ebitda.filter((r) => r['scenario_tag'] === 'baseline').map(toRow);

  const metricOf = new Map(table('semantic_effect_metric_links').map((r) => [str(r, 'effect_id'), str(r, 'metric_id')]));
  const effects: EffectRow[] = table('semantic_event_financial_effects').map((r) => {
    const effectId = str(r, 'effect_id');
    const metricId = metricOf.get(effectId);
    if (!metricId) throw new Error(`effect ${effectId} has no metric link`);
    return {
      effectId,
      eventId: str(r, 'event_id'),
      entityId: str(r, 'entity_id'),
      effectDate: str(r, 'effect_date'),
      metricId,
      deltaEbitdaLocal: str(r, 'delta_ebitda_local'),
      fxRateToGroup: str(r, 'fx_rate_to_group'),
      ownershipRatio: str(r, 'ownership_ratio'),
      deltaEbitdaFullJpy: str(r, 'delta_ebitda_full_jpy'),
      deltaManagementJpy: str(r, 'delta_management_jpy'),
    };
  });

  const events: EventRow[] = table('semantic_risk_events').map((r) => ({
    eventId: str(r, 'event_id'),
    primarySector: str(r, 'primary_sector'),
    direction: str(r, 'direction'),
    severity: Number(str(r, 'severity')),
    startDate: str(r, 'start_date'),
    endDate: str(r, 'end_date'),
    narrative: str(r, 'narrative'),
  }));

  const kpiDaily = table('kpi_snapshot')
    .filter((r) => typeof r['kpi_code'] === 'string' && (r['kpi_code'] as string).startsWith('EBITDA_'))
    .map((r) => ({
      date: str(r, 'kpi_date'),
      scenario: str(r, 'scenario_tag'),
      code: str(r, 'kpi_code'),
      amount: str(r, 'amount_group'),
    }));

  return { base: { companies, ebitdaRows, effects, events }, reference: { baselineRows, kpiDaily } };
}
