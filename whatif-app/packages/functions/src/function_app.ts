import { UserDataFunctions, AudienceType, type RayfinContext } from '@microsoft/fabric-user-data-functions';
import { simulate, simulateFuture, quarterlySectors, type Scenario, type ScenarioResult, type FutureBaseline, type FutureScenario, type FutureResult, type QuarterSectors, ScenarioError, DataError } from './engine/index.js';
import { FabricError } from './fabric.js';
import { forecastBySector, readForecast } from './forecast.js';
import { readEvents, readPaths, type GraphEvent, type GraphPath } from './graph.js';
import { load, cacheAgeMs, type Source } from './model.js';

const udf = new UserDataFunctions();


// 期待される失敗は例外ではなく、型付きの結果で返す（画面が理由を表示できるように）
export type Failure = { ok: false; code: string; message: string };
const fail = (error: unknown): Failure => {
  if (error instanceof ScenarioError) return { ok: false, code: error.code, message: error.message };
  if (error instanceof FabricError) return { ok: false, code: error.code, message: error.message };
  if (error instanceof DataError) return { ok: false, code: 'UPSTREAM', message: 'Graph and source data could not be reconciled.' };
  console.error('unexpected failure', error instanceof Error ? error.name : typeof error);
  return { ok: false, code: 'UNEXPECTED', message: 'An unexpected error occurred.' };
};

const tokens = (ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>) => ({ fabric: ctx.Tokens.Fabric, sql: ctx.Tokens.Sql });

export type ProbeResult =
  | {
      ok: true;
      source: Source;
      loadMs: number;
      cacheAgeMs: number | null;
      counts: { companies: number; ebitdaRows: number; effects: number; events: number };
      reconciliation: { ok: boolean; groupMismatches: number; managementMismatches: number; effectMismatches: number };
      base: { full: string; management: string };
      graph: { events: number; eventIds: string[]; foodLossPathRows: number; foodLossUniqueEffects: number; pathMs: number };
    }
  | Failure;

// 接続の診断。値は件数と合計だけで、ID・ホスト名・トークンは返さない
udf.func(
  'probe',
  async (ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<ProbeResult> => {
    try {
      const { data, source } = await load(tokens(ctx));
      const t0 = Date.now();
      const events = await readEvents(ctx.Tokens.Fabric, data.coordinates);
      const paths = await readPaths(ctx.Tokens.Fabric, data.coordinates, 'FOD_NEG');
      const pathMs = Date.now() - t0;
      const result = simulate(data.prepared, {});
      const r = data.reconciliation;
      return {
        ok: true,
        source,
        loadMs: data.loadMs,
        cacheAgeMs: cacheAgeMs() ?? null,
        counts: {
          companies: data.base.companies.length,
          ebitdaRows: data.base.ebitdaRows.length,
          effects: data.base.effects.length,
          events: data.base.events.length,
        },
        reconciliation: {
          ok: r.ok,
          groupMismatches: r.groupMismatches,
          managementMismatches: r.managementMismatches,
          effectMismatches: r.effectFullMismatches + r.effectManagementMismatches,
        },
        base: result.base,
        graph: {
          events: events.length,
          eventIds: events.map((e) => e.eventId),
          foodLossPathRows: paths.length,
          foodLossUniqueEffects: new Set(paths.map((p) => p.effectId)).size,
          pathMs,
        },
      };
    } catch (error) {
      return fail(error);
    }
  },
  []
);

export type SimulateResult = { ok: true; source: Source; result: ScenarioResult } | Failure;

// シナリオを適用する。入力の検証はエンジン側（範囲外・未知のIDは ScenarioError）
udf.func(
  'simulate',
  async (scenario: Scenario, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<SimulateResult> => {
    try {
      const { data, source } = await load(tokens(ctx));
      return { ok: true, source, result: simulate(data.prepared, scenario) };
    } catch (error) {
      return fail(error);
    }
  },
  []
);

export interface ModelView {
  events: (GraphEvent & { effects: number })[];
  companies: { entityId: string; name: string; sector: string; currency: string; ownership: string }[];
  period: { from: string; to: string };
}

export type ModelResult = { ok: true; source: Source; model: ModelView } | Failure;

// 画面の選択肢（イベント一覧・会社一覧）。イベントはオントロジーのグラフから、会社と持分は Lakehouse から取る
udf.func(
  'loadModel',
  async (ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<ModelResult> => {
    try {
      const { data, source } = await load(tokens(ctx));
      const events = await readEvents(ctx.Tokens.Fabric, data.coordinates);
      const perEvent = new Map<string, number>();
      for (const e of data.base.effects) perEvent.set(e.eventId, (perEvent.get(e.eventId) ?? 0) + 1);
      return {
        ok: true,
        source,
        model: {
          events: events.map((e) => ({ ...e, effects: perEvent.get(e.eventId) ?? 0 })),
          companies: data.base.companies.map((c) => ({
            entityId: c.entityId,
            name: c.entityName,
            sector: c.sectorCode,
            currency: c.currencyCode,
            ownership: c.ownershipRatio,
          })),
          period: { from: data.prepared.firstDate, to: data.prepared.lastDate },
        },
      };
    } catch (error) {
      return fail(error);
    }
  },
  []
);

export type PathsResult = { ok: true; eventId: string; paths: GraphPath[] } | Failure;

// 選んだイベントの影響経路（イベント → 効果 → 日次メトリクス → 全社KPI）をグラフから取る
udf.func(
  'eventPaths',
  async (eventId: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<PathsResult> => {
    try {
      const { data } = await load(tokens(ctx));
      if (!data.base.events.some((e) => e.eventId === eventId)) {
        return { ok: false, code: 'UNKNOWN_EVENT', message: 'Unknown event.' };
      }
      return { ok: true, eventId, paths: await readPaths(ctx.Tokens.Fabric, data.coordinates, eventId) };
    } catch (error) {
      return fail(error);
    }
  },
  []
);

export interface ForecastView {
  baseline: FutureBaseline;
  generatedAt: string;
  model: string;
}

// 四半期ごとの業種別の実績と、予測の業種別の内訳（保存された結果に会社別が無いときは null）
export type ForecastModelResult =
  | { ok: true; forecast: ForecastView; history: QuarterSectors[]; forecastBySector: Record<string, string> | null }
  | Failure;

udf.func(
  'loadForecast',
  async (ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<ForecastModelResult> => {
    try {
      const { data } = await load(tokens(ctx));
      const forecast = await readForecast(ctx.Tokens.Fabric, data.coordinates.workspaceId);
      if (forecast.baseline.asOf !== data.prepared.lastDate) {
        throw new FabricError('UPSTREAM', 'Forecast and historical data have different cutoffs.');
      }
      return {
        ok: true,
        forecast: { baseline: forecast.baseline, generatedAt: forecast.generatedAt, model: forecast.model },
        history: quarterlySectors(data.prepared),
        forecastBySector: forecastBySector(forecast.byEntity, data.base.companies),
      };
    } catch (error) {
      return fail(error);
    }
  },
  []
);

export interface ForecastGraphSummary {
  effects: number;
  activities: number;
  contracts: number;
  evidence: number;
  metrics: number;
  kpis: number;
}

export type ForecastSimulationResult = { ok: true; result: FutureResult; graph: ForecastGraphSummary } | Failure;

udf.func(
  'simulateForecast',
  async (scenario: FutureScenario, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric | AudienceType.Sql>): Promise<ForecastSimulationResult> => {
    try {
      const { data } = await load(tokens(ctx));
      if (!data.base.events.some((event) => event.eventId === scenario.eventId)) {
        return { ok: false, code: 'UNKNOWN_EVENT', message: 'Unknown event.' };
      }
      const [forecast, paths] = await Promise.all([
        readForecast(ctx.Tokens.Fabric, data.coordinates.workspaceId),
        readPaths(ctx.Tokens.Fabric, data.coordinates, scenario.eventId),
      ]);
      if (forecast.baseline.asOf !== data.prepared.lastDate) {
        throw new FabricError('UPSTREAM', 'Forecast and historical data have different cutoffs.');
      }
      const result = simulateFuture(data.prepared, forecast.baseline, scenario, paths);
      return {
        ok: true, result,
        graph: {
          effects: new Set(paths.map((path) => path.effectId)).size,
          activities: new Set(paths.map((path) => path.activityId)).size,
          contracts: new Set(paths.map((path) => path.contractId)).size,
          evidence: new Set(paths.map((path) => path.evidenceId)).size,
          metrics: new Set(paths.map((path) => path.metricId)).size,
          kpis: new Set(paths.map((path) => path.kpiId)).size,
        },
      };
    } catch (error) {
      return fail(error);
    }
  },
  []
);
