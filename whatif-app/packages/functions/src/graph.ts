import { FabricError, fabricFetch, type Coordinates } from './fabric.js';

// Step 3 のノートブック（scripts/step3_food_loss_runtime.py）と同じ呼び方。
// executeQuery は beta で、本番利用は非推奨とされている。互換が崩れたときに検知できるよう、
// ステータスコードと列を検査し、空や警告つきの結果は失敗にする。

interface GqlResponse {
  status?: { code?: string };
  additionalStatuses?: unknown[];
  result?: { data?: Record<string, unknown>[]; nextPage?: string };
}

const OK = new Set(['00000', '02000']);
const MAX_PAGES = 20;

export async function gql(
  token: string,
  where: Pick<Coordinates, 'workspaceId' | 'graphId'>,
  query: string,
  { allowEmpty = false }: { allowEmpty?: boolean } = {},
): Promise<Record<string, unknown>[]> {
  const base = `workspaces/${where.workspaceId}/graphModels/${where.graphId}/executeQuery?beta=true`;
  const rows: Record<string, unknown>[] = [];
  let next: string | undefined;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const res = await fabricFetch<GqlResponse>(token, {
      method: 'POST',
      path: next ? `${base}&continuationToken=${encodeURIComponent(next)}` : base,
      body: { query },
    });
    const code = res.status?.code ?? 'unknown';
    if (!OK.has(code) || (res.additionalStatuses?.length ?? 0) > 0) {
      throw new FabricError('UPSTREAM', `Graph query failed or warned (status ${code})`);
    }
    rows.push(...(res.result?.data ?? []));
    next = res.result?.nextPage;
    if (!next) {
      if (rows.length === 0 && !allowEmpty) throw new FabricError('UPSTREAM', 'Graph query returned no rows');
      return rows;
    }
  }
  throw new FabricError('UPSTREAM', 'Graph pagination exceeded its limit');
}

const str = (r: Record<string, unknown>, k: string): string => {
  const v = r[k];
  if (typeof v !== 'string') throw new FabricError('UPSTREAM', `Graph column ${k} is not a string`);
  return v;
};

export interface GraphEvent {
  eventId: string;
  sector: string;
  direction: string;
  severity: number;
  startDate: string;
  endDate: string;
  narrative: string;
}

export interface GraphCompany {
  entityId: string;
  name: string;
  sector: string;
  currency: string;
  ownership: string;
}

// 数値はグラフ上で浮動小数点になる。会計の正は SQL の DECIMAL なので、グラフからは構造と表示用の値だけを取り、
// 金額・持分は Lakehouse から取る。持分はここでは文字列にせず、SQL 側の値を使う。
export async function readEvents(token: string, where: Coordinates): Promise<GraphEvent[]> {
  const rows = await gql(
    token,
    where,
    `MATCH (e:RiskEvent)
     RETURN e.event_id AS event_id, e.primary_sector AS sector, e.direction AS direction,
            e.severity AS severity, e.start_date AS start_date, e.end_date AS end_date,
            e.narrative AS narrative
     ORDER BY e.event_id LIMIT 200`,
  );
  return rows.map((r) => ({
    eventId: str(r, 'event_id'),
    sector: str(r, 'sector'),
    direction: str(r, 'direction'),
    severity: Number(r['severity']),
    startDate: str(r, 'start_date'),
    endDate: str(r, 'end_date'),
    narrative: str(r, 'narrative'),
  }));
}

// イベントから日次メトリクス・全社KPIまでの経路（Step 3 の PATH_QUERY を、イベントを引数にした形）。
// イベントIDは英数字と _ のみ受け付け、クエリに埋め込む
const EVENT_ID = /^[A-Z0-9_]{1,40}$/;

export interface GraphPath {
  effectId: string;
  entityId: string;
  activityId: string;
  activityType: string;
  commodity: string;
  contractId: string;
  evidenceId: string;
  metricId: string;
  kpiId: string;
}

export async function readPaths(token: string, where: Coordinates, eventId: string): Promise<GraphPath[]> {
  if (!EVENT_ID.test(eventId)) throw new FabricError('UPSTREAM', 'Invalid event id');
  const rows = await gql(
    token,
    where,
    `MATCH (e:RiskEvent)-[:EventHasEffect]->(f:FinancialEffect)
           -[:EffectRealizedInMetric]->(m:FinancialMetric)
           -[:MetricRollsUpToGroupKPI]->(k:GroupKPI),
           (f)-[:EffectOnActivity]->(a:Activity)-[:ActivityUnderContract]->(c:Contract),
           (f)-[:EffectOnContract]->(c),
           (f)-[:EffectExplainedByEvidence]->(v:Evidence)-[:EvidenceSupportsEvent]->(e),
           (e)-[:EventImpactsActivity]->(a)
     WHERE e.event_id='${eventId}'
       AND m.metric_code='EBITDA' AND m.scenario_tag='actual'
       AND k.kpi_code='EBITDA_FULL_CONSOLIDATED' AND k.scenario_tag='actual'
     RETURN f.effect_id AS effect_id, a.entity_id AS entity_id, a.activity_id AS activity_id,
            a.activity_type AS activity_type, c.commodity AS commodity, c.contract_id AS contract_id,
            v.evidence_id AS evidence_id, m.metric_id AS metric_id, k.kpi_id AS kpi_id
     ORDER BY f.effect_id LIMIT 1000`,
  );
  if (rows.length >= 1000) throw new FabricError('UPSTREAM', 'Path limit reached; refusing a possibly incomplete result');
  return rows.map((r) => ({
    effectId: str(r, 'effect_id'),
    entityId: str(r, 'entity_id'),
    activityId: str(r, 'activity_id'),
    activityType: str(r, 'activity_type'),
    commodity: str(r, 'commodity'),
    contractId: str(r, 'contract_id'),
    evidenceId: str(r, 'evidence_id'),
    metricId: str(r, 'metric_id'),
    kpiId: str(r, 'kpi_id'),
  }));
}
