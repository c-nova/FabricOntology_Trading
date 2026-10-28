import sql from 'mssql';
import type { BaseData, CompanyRow, EbitdaRow, EffectRow, EventRow } from './engine/index.js';
import { FabricError, type Coordinates } from './fabric.js';

// 金額・率・為替は CAST(... AS VARCHAR(40)) で文字列として受け取る（浮動小数点を通さない）。
// 読むのは親 Lakehouse（LH_Group_SAP）の semantic_* テーブルだけで、すべて読み取り専用の SELECT。

const SCHEMA = 'dbo';

// 取り込みの前提を、件数で確認する（不足は静かに欠落させず失敗にする）
export const EXPECTED = { companies: 8, ebitdaRows: 2920, effects: 1344, events: 10 } as const;

async function connect(token: string, where: Coordinates): Promise<sql.ConnectionPool> {
  const pool = new sql.ConnectionPool({
    server: where.sqlServer,
    database: where.lakehouseName,
    options: { encrypt: true, trustServerCertificate: false },
    connectionTimeout: 30_000,
    requestTimeout: 60_000,
    authentication: { type: 'azure-active-directory-access-token', options: { token } },
  });
  try {
    return await pool.connect();
  } catch (error) {
    throw mapSqlError(error);
  }
}

// ドライバーのエラー本文は、サーバー名やトークン断片を含み得るので返さない
function mapSqlError(error: unknown): FabricError {
  const e = error as { code?: string; number?: number } | undefined;
  const code = e?.code ?? (e?.number !== undefined ? String(e.number) : 'unknown');
  if (code === 'ELOGIN' || code === '18456' || code === '40615') {
    return new FabricError('AUTH', `SQL endpoint denied the login (${code}). The app identity needs access to the Lakehouse.`);
  }
  if (code === 'ETIMEOUT' || code === 'ESOCKET' || code === 'ECONNRESET') {
    return new FabricError('UPSTREAM', `SQL endpoint did not respond (${code}).`);
  }
  return new FabricError('UPSTREAM', `SQL query failed (${code}).`);
}

type Row = Record<string, unknown>;

async function run(pool: sql.ConnectionPool, query: string): Promise<Row[]> {
  try {
    const result = await pool.request().query(query);
    return result.recordset as unknown as Row[];
  } catch (error) {
    throw mapSqlError(error);
  }
}

const s = (r: Row, k: string): string => {
  const v = r[k];
  if (typeof v === 'string') return v;
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  throw new FabricError('UPSTREAM', `SQL column ${k} was not a string`);
};

const V = (c: string) => `CAST(${c} AS VARCHAR(40))`;

export async function readBaseData(token: string, where: Coordinates): Promise<BaseData> {
  const pool = await connect(token, where);
  try {
    const companies = (
      await run(
        pool,
        `SELECT entity_id, entity_name, sector_code, country_code, currency_code, ${V('ownership_ratio')} AS ownership_ratio
         FROM ${SCHEMA}.company_master ORDER BY entity_id`,
      )
    ).map<CompanyRow>((r) => ({
      entityId: s(r, 'entity_id'),
      entityName: s(r, 'entity_name'),
      sectorCode: s(r, 'sector_code'),
      countryCode: s(r, 'country_code'),
      currencyCode: s(r, 'currency_code'),
      ownershipRatio: s(r, 'ownership_ratio'),
    }));

    const ebitdaRows = (
      await run(
        pool,
        `SELECT metric_id, CONVERT(VARCHAR(10), metric_date, 23) AS metric_date, entity_id,
                ${V('amount_local')} AS amount_local, ${V('fx_rate_to_group')} AS fx_rate_to_group,
                ${V('amount_group')} AS amount_group, ${V('management_contribution_jpy')} AS management_contribution_jpy
         FROM ${SCHEMA}.semantic_financial_metrics_daily
         WHERE metric_code = 'EBITDA' AND scenario_tag = 'actual'
         ORDER BY metric_date, entity_id`,
      )
    ).map<EbitdaRow>((r) => ({
      metricId: s(r, 'metric_id'),
      date: s(r, 'metric_date'),
      entityId: s(r, 'entity_id'),
      amountLocal: s(r, 'amount_local'),
      fxRateToGroup: s(r, 'fx_rate_to_group'),
      amountGroup: s(r, 'amount_group'),
      managementJpy: s(r, 'management_contribution_jpy'),
    }));

    // 効果 → 日次メトリクスは、明示的なリンク表で結ぶ（日付だけの結合は曖昧になるため使わない）
    const effects = (
      await run(
        pool,
        `SELECT f.effect_id, f.event_id, f.entity_id, CONVERT(VARCHAR(10), f.effect_date, 23) AS effect_date, l.metric_id,
                ${V('f.delta_ebitda_local')} AS delta_ebitda_local, ${V('f.fx_rate_to_group')} AS fx_rate_to_group,
                ${V('f.ownership_ratio')} AS ownership_ratio, ${V('f.delta_ebitda_full_jpy')} AS delta_ebitda_full_jpy,
                ${V('f.delta_management_jpy')} AS delta_management_jpy
         FROM ${SCHEMA}.semantic_event_financial_effects f
         JOIN ${SCHEMA}.semantic_effect_metric_links l ON l.effect_id = f.effect_id
         ORDER BY f.effect_id`,
      )
    ).map<EffectRow>((r) => ({
      effectId: s(r, 'effect_id'),
      eventId: s(r, 'event_id'),
      entityId: s(r, 'entity_id'),
      effectDate: s(r, 'effect_date'),
      metricId: s(r, 'metric_id'),
      deltaEbitdaLocal: s(r, 'delta_ebitda_local'),
      fxRateToGroup: s(r, 'fx_rate_to_group'),
      ownershipRatio: s(r, 'ownership_ratio'),
      deltaEbitdaFullJpy: s(r, 'delta_ebitda_full_jpy'),
      deltaManagementJpy: s(r, 'delta_management_jpy'),
    }));

    const events = (
      await run(
        pool,
        `SELECT event_id, primary_sector, direction, severity, CONVERT(VARCHAR(10), start_date, 23) AS start_date,
                CONVERT(VARCHAR(10), end_date, 23) AS end_date, narrative
         FROM ${SCHEMA}.semantic_risk_events ORDER BY event_id`,
      )
    ).map<EventRow>((r) => ({
      eventId: s(r, 'event_id'),
      primarySector: s(r, 'primary_sector'),
      direction: s(r, 'direction'),
      severity: Number(r['severity']),
      startDate: s(r, 'start_date'),
      endDate: s(r, 'end_date'),
      narrative: s(r, 'narrative'),
    }));

    const counts = { companies: companies.length, ebitdaRows: ebitdaRows.length, effects: effects.length, events: events.length };
    for (const k of Object.keys(EXPECTED) as (keyof typeof EXPECTED)[]) {
      if (counts[k] !== EXPECTED[k]) {
        throw new FabricError('UPSTREAM', `Unexpected row count for ${k}: got ${counts[k]}, expected ${EXPECTED[k]}`);
      }
    }
    return { companies, ebitdaRows, effects, events };
  } finally {
    await pool.close().catch(() => undefined);
  }
}
