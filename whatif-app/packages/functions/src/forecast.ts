import { Decimal } from './engine/decimal.js';
import type { FutureBaseline } from './engine/index.js';
import { FabricError, fabricFetch, fabricFetchResponse, resolveNotebookId } from './fabric.js';

const NOTEBOOK_NAME = 'TradingDemo_04_Ontology_AutoML_予測';
const MODEL_NAME = 'AutoML + Graph';
const TTL_MS = 10 * 60 * 1000;

export interface EntityForecast {
  entityId: string;
  amountFull: string;
}

export interface ForecastSnapshot {
  baseline: FutureBaseline;
  generatedAt: string;
  model: string;
  /** 次の四半期の会社別予測（JPY）。保存された結果に無いときは null */
  byEntity: EntityForecast[] | null;
}

const object = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;

function date(value: unknown): Date | undefined {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? parsed : undefined;
}

const OKU = 100_000_000;
// 会社別の合計と、保存された合計のずれの許容（億円）。浮動小数点の誤差だけを許す
const SUM_TOLERANCE_OKU = 1e-6;

// 会社別の予測。無ければ null（古い保存結果）。あるのに壊れているときは、黙って捨てずに失敗にする
function parseByEntity(value: unknown, total: number): EntityForecast[] | null {
  if (value === undefined) return null;
  if (!Array.isArray(value) || value.length === 0) throw new FabricError('UPSTREAM', 'The saved company forecast is invalid.');
  const seen = new Set<string>();
  let sum = 0;
  const parsed = value.map((item): EntityForecast => {
    const row = object(item);
    const id = row?.entity_id;
    const amount = row?.amount_oku;
    if (typeof id !== 'string' || id.length === 0 || seen.has(id) || typeof amount !== 'number' || !Number.isFinite(amount)) {
      throw new FabricError('UPSTREAM', 'The saved company forecast is invalid.');
    }
    seen.add(id);
    sum += amount;
    return { entityId: id, amountFull: new Decimal(amount).times(OKU).toFixed(2) };
  });
  if (Math.abs(sum - total) > SUM_TOLERANCE_OKU) {
    throw new FabricError('UPSTREAM', 'The saved company forecast does not add up to the saved total.');
  }
  return parsed;
}

// The Notebook saves the latest actual run in metadata; never substitute a hardcoded estimate.
export function parseForecastDefinition(value: unknown): ForecastSnapshot {
  const parts = object(object(value)?.definition)?.parts;
  if (!Array.isArray(parts)) throw new FabricError('UPSTREAM', 'Forecast notebook definition is invalid.');
  const notebooks = parts.map(object).filter((part) =>
    typeof part?.path === 'string' && part.path.endsWith('.ipynb') &&
    part.payloadType === 'InlineBase64' && typeof part.payload === 'string',
  );
  if (notebooks.length !== 1) throw new FabricError('UPSTREAM', 'Forecast notebook content is missing or ambiguous.');
  const payload = notebooks[0]!.payload;
  if (typeof payload !== 'string') throw new FabricError('UPSTREAM', 'Forecast notebook content is invalid.');
  let notebook: unknown;
  try {
    notebook = JSON.parse(Buffer.from(payload, 'base64').toString('utf8'));
  } catch (error) {
    if (error instanceof SyntaxError) throw new FabricError('UPSTREAM', 'Forecast notebook content is not valid JSON.');
    throw error;
  }
  const report = object(object(object(notebook)?.metadata)?.trading_forecast)?.latest_live_report;
  const data = object(report);
  const results = data?.results;
  if (!Array.isArray(results)) throw new FabricError('UPSTREAM', 'The notebook has no saved forecast run.');
  const selected = results.map(object).filter((row) => row?.model === MODEL_NAME);
  if (selected.length !== 1) throw new FabricError('UPSTREAM', 'The selected forecast model is missing or ambiguous.');
  const amount = selected[0]!.next_q_forecast_oku;
  const origin = date(data?.future_origin);
  const horizon = data?.horizon_days;
  const generatedAt = data?.executed_at_utc;
  const source = object(data?.source);
  if (typeof amount !== 'number' || !Number.isFinite(amount) || !origin ||
      typeof horizon !== 'number' || !Number.isInteger(horizon) || horizon < 1 || horizon > 92 ||
      typeof generatedAt !== 'string' || !Number.isFinite(Date.parse(generatedAt)) ||
      source?.last_date !== data?.future_origin || typeof source?.graph_paths !== 'number' || source.graph_paths < 1) {
    throw new FabricError('UPSTREAM', 'The saved forecast or its provenance is invalid.');
  }
  const start = new Date(origin.valueOf() + 86_400_000);
  const end = new Date(start.valueOf() + (horizon - 1) * 86_400_000);
  const nextQuarter = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 3, 1));
  if (start.getUTCDate() !== 1 || start.getUTCMonth() % 3 !== 0 ||
      end.valueOf() + 86_400_000 !== nextQuarter.valueOf()) {
    throw new FabricError('UPSTREAM', 'The saved forecast is not a full calendar quarter.');
  }
  return {
    baseline: {
      asOf: origin.toISOString().slice(0, 10),
      period: { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) },
      amountFull: new Decimal(amount).times(OKU).toFixed(2),
    },
    generatedAt,
    model: MODEL_NAME,
    byEntity: parseByEntity(selected[0]!.next_q_by_entity_oku, amount),
  };
}

// 会社別の予測を業種ごとに合計する（10進）。全業種のキーを持ち、会社マスタに無い会社があれば失敗にする
export function forecastBySector(
  byEntity: readonly EntityForecast[] | null,
  companies: readonly { entityId: string; sectorCode: string }[],
): Record<string, string> | null {
  if (byEntity === null) return null;
  const sectorOf = new Map(companies.map((c) => [c.entityId, c.sectorCode]));
  const sums = new Map<string, Decimal>();
  for (const code of [...new Set(companies.map((c) => c.sectorCode))].sort()) sums.set(code, new Decimal(0));
  for (const e of byEntity) {
    const sector = sectorOf.get(e.entityId);
    if (sector === undefined) throw new FabricError('UPSTREAM', 'The saved forecast refers to an unknown company.');
    sums.set(sector, sums.get(sector)!.plus(e.amountFull));
  }
  return Object.fromEntries([...sums].map(([code, sum]) => [code, sum.toFixed(2)]));
}

async function getDefinition(token: string, workspaceId: string, notebookId: string): Promise<unknown> {
  const response = await fabricFetchResponse<unknown>(token, {
    path: `workspaces/${workspaceId}/notebooks/${notebookId}/getDefinition?format=ipynb`,
    method: 'POST', body: {}, signal: AbortSignal.timeout(45_000),
  });
  if (response.status !== 202) return response.data;
  const operation = response.headers.get('x-ms-operation-id');
  if (!operation || !/^[0-9a-f-]{36}$/i.test(operation)) {
    throw new FabricError('UPSTREAM', 'Forecast notebook operation ID is missing.');
  }
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    const state = await fabricFetch<{ status?: string }>(token, {
      path: `operations/${operation}`, signal: AbortSignal.timeout(20_000),
    });
    if (state.status === 'Succeeded') {
      return fabricFetch<unknown>(token, {
        path: `operations/${operation}/result`, signal: AbortSignal.timeout(30_000),
      });
    }
    if (state.status === 'Failed' || state.status === 'Cancelled') {
      throw new FabricError('UPSTREAM', 'The forecast notebook could not be read.');
    }
  }
  throw new FabricError('UPSTREAM', 'Reading the forecast notebook timed out.');
}

let cache: { workspaceId: string; snapshot: ForecastSnapshot; loadedAt: number } | undefined;
const inflight = new Map<string, Promise<ForecastSnapshot>>();

export async function readForecast(token: string, workspaceId: string): Promise<ForecastSnapshot> {
  if (cache && cache.workspaceId === workspaceId && Date.now() - cache.loadedAt < TTL_MS) return cache.snapshot;
  let pending = inflight.get(workspaceId);
  if (!pending) {
    pending = (async () => {
      const notebookId = await resolveNotebookId(token, workspaceId, NOTEBOOK_NAME);
      const snapshot = parseForecastDefinition(await getDefinition(token, workspaceId, notebookId));
      cache = { workspaceId, snapshot, loadedAt: Date.now() };
      return snapshot;
    })().finally(() => { inflight.delete(workspaceId); });
    inflight.set(workspaceId, pending);
  }
  return pending;
}
