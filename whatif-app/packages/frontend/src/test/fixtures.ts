import type { Api } from '@/lib/api';
import type { EventPathsOutput, ForecastModelOutput, ForecastSimulationOutput, LoadModelOutput, SimulateOutput } from '@/lib/types';

// 実機の Functions が返した「形」に合わせたフィクスチャ。
// 実機で確認した値は、全体の基準・シナリオ・差・段階（steps）と FOD_NEG の影響額だけ。
// 会社別・セクター別・月別・他のイベントの金額は、画面の動作を確かめるための仮の値（実機の値ではない）。

const EVENT = (eventId: string, sector: string, direction: string, severity: number, startDate: string, endDate: string, narrative: string, effects: number) => ({
  eventId,
  sector,
  direction,
  severity,
  startDate: `${startDate}T00:00:00Z`,
  endDate: `${endDate}T00:00:00Z`,
  narrative,
  effects,
});

export const MODEL: Extract<LoadModelOutput, { ok: true }>['model'] = {
  events: [
    EVENT('MTL_NEG', 'metals', 'negative', 5, '2025-11-12', '2025-12-02', 'SYNTHETIC: smelter outage', 84),
    EVENT('FOD_NEG', 'foods', 'negative', 5, '2026-02-09', '2026-03-01', 'SYNTHETIC: cold chain spoilage incident', 84),
    EVENT('FOD_POS', 'foods', 'positive', 4, '2026-07-06', '2026-07-26', 'SYNTHETIC: grain yield and procurement improvement', 84),
  ],
  companies: [
    { entityId: 'SUB_FOD_JP_01', name: 'Caldriva Foods Japan KK', sector: 'foods', currency: 'JPY', ownership: '0.51000000' },
    { entityId: 'SUB_FOD_US_01', name: 'Caldriva Foods USA Inc.', sector: 'foods', currency: 'USD', ownership: '1.00000000' },
  ],
  period: { from: '2025-10-01', to: '2026-09-30' },
};

const totals = (full: string, management: string) => ({ full, management });
const row = (key: string, label: string, base: [string, string], scenario: [string, string]) => ({
  key,
  label,
  base: totals(...base),
  scenario: totals(...scenario),
  delta: totals(String(Number(scenario[0]) - Number(base[0])), String(Number(scenario[1]) - Number(base[1]))),
});

type Result = Extract<SimulateOutput, { ok: true }>['result'];

// 基準（何も変えない）
export const BASE_RESULT: Result = {
  period: { from: '2025-10-01', to: '2026-09-30' },
  applied: { fx: null, events: {}, ownership: {} },
  base: totals('44757399732.84', '33547898914.09'),
  scenario: totals('44757399732.84', '33547898914.09'),
  delta: totals('0.00', '0.00'),
  steps: { events: totals('0.00', '0.00'), fx: totals('0.00', '0.00'), ownership: totals('0.00', '0.00') },
  byEntity: [
    row('SUB_FOD_JP_01', 'Caldriva Foods Japan KK', ['3000000000.00', '1530000000.00'], ['3000000000.00', '1530000000.00']),
    row('SUB_FOD_US_01', 'Caldriva Foods USA Inc.', ['5000000000.00', '5000000000.00'], ['5000000000.00', '5000000000.00']),
  ],
  bySector: [row('foods', 'foods', ['8000000000.00', '6530000000.00'], ['8000000000.00', '6530000000.00'])],
  byMonth: [row('2026-02', '2026-02', ['3700000000.00', '2800000000.00'], ['3700000000.00', '2800000000.00'])],
  eventImpacts: [
    { eventId: 'MTL_NEG', scale: '1', effects: 84, baseFull: '-200000000.00', scenarioFull: '-200000000.00', baseManagement: '-150000000.00', scenarioManagement: '-150000000.00' },
    { eventId: 'FOD_NEG', scale: '1', effects: 84, baseFull: '-114461186.25', scenarioFull: '-114461186.25', baseManagement: '-87630294.31', scenarioManagement: '-87630294.31' },
    { eventId: 'FOD_POS', scale: '1', effects: 84, baseFull: '90000000.00', scenarioFull: '90000000.00', baseManagement: '70000000.00', scenarioManagement: '70000000.00' },
  ],
  stats: { rows: 2920, rowsTouched: 0, effects: 252 },
};

// 食品損失 50% 軽減 + 円高 10%（実機で確認した値）
export const SCENARIO_RESULT: Result = {
  ...BASE_RESULT,
  applied: { fx: { currency: 'USD', factor: '0.90' }, events: { FOD_NEG: '0.50' }, ownership: {} },
  scenario: totals('42482824156.07', '32178972713.38'),
  delta: totals('-2274575575.77', '-1368926200.71'),
  steps: { events: totals('57230593.13', '43815147.15'), fx: totals('-2331806168.90', '-1412741347.86'), ownership: totals('0.00', '0.00') },
  byEntity: [
    row('SUB_FOD_JP_01', 'Caldriva Foods Japan KK', ['3000000000.00', '1530000000.00'], ['3028615296.57', '1544493301.25']),
    row('SUB_FOD_US_01', 'Caldriva Foods USA Inc.', ['5000000000.00', '5000000000.00'], ['2700000000.00', '2700000000.00']),
  ],
  eventImpacts: BASE_RESULT.eventImpacts.map((i) =>
    i.eventId === 'FOD_NEG' ? { ...i, scale: '0.5', scenarioFull: '-51800000.00', scenarioManagement: '-39500000.00' } : i,
  ),
};

// 円安（USD +10%）の想定。増加の表示を確かめるための仮の値（実機の値ではない）。
export const INCREASE_RESULT: Result = {
  ...BASE_RESULT,
  applied: { fx: { currency: 'USD', factor: '1.10' }, events: {}, ownership: {} },
  scenario: totals('46000000000.00', '34800000000.00'),
  delta: totals('1242600267.16', '1252101085.91'),
  steps: { events: totals('0.00', '0.00'), fx: totals('1242600267.16', '1252101085.91'), ownership: totals('0.00', '0.00') },
};

export const PATHS: Extract<EventPathsOutput, { ok: true }>['paths'] = Array.from({ length: 84 }, (_, i) => ({
  effectId: `FE_FOD_${i}`,
  entityId: i % 2 === 0 ? 'SUB_FOD_JP_01' : 'SUB_FOD_US_01',
  activityId: `ACT_${i}`,
  activityType: 'external_sale',
  commodity: i % 3 === 0 ? 'milling_wheat' : 'wheat_flour',
  contractId: `CT_${i % 6}`,
  evidenceId: `EV_${i}`,
  metricId: `MET_${i % 40}`,
  kpiId: `KPI_${i % 40}`,
}));

export const FORECAST: Extract<ForecastModelOutput, { ok: true }>['forecast'] = {
  baseline: { asOf: '2026-09-30', period: { from: '2026-10-01', to: '2026-12-31' }, amountFull: '11489536832.22' },
  generatedAt: '2026-10-28T08:21:36.287799+00:00',
  model: 'AutoML + Graph',
};

// 四半期 × 業種の実績は、デモのデータから計算した実際の値。予測の業種別は、Notebookの会社別予測を業種ごとに足した代表値
const HISTORY = (key: string, from: string, to: string, days: number, e: string, fi: string, fo: string, m: string, total: string) => ({
  key, from, to, days, bySector: { energy: e, finance: fi, foods: fo, metals: m }, total,
});

export const FORECAST_LOADED: Extract<ForecastModelOutput, { ok: true }> = {
  ok: true,
  forecast: FORECAST,
  history: [
    HISTORY('2025-10', '2025-10-01', '2025-12-31', 92, '3659896223.83', '2215293991.93', '2268041186.13', '3450070964.81', '11593302366.70'),
    HISTORY('2026-01', '2026-01-01', '2026-03-31', 90, '3051868478.21', '2006240974.71', '1899787513.32', '3407015356.32', '10364912322.56'),
    HISTORY('2026-04', '2026-04-01', '2026-06-30', 91, '3641639908.28', '2025999134.02', '2182944718.51', '3387211701.26', '11237795462.07'),
    HISTORY('2026-07', '2026-07-01', '2026-09-30', 92, '3436018594.32', '2338305881.58', '2301118582.61', '3485946523.00', '11561389581.51'),
  ],
  forecastBySector: { energy: '3468366385.09', finance: '2283752778.81', foods: '2282177748.07', metals: '3455239920.26' },
};

export const FORECAST_RESULT: Extract<ForecastSimulationOutput, { ok: true }>['result'] = {
  period: FORECAST.baseline.period, asOf: FORECAST.baseline.asOf,
  baselineFull: FORECAST.baseline.amountFull, scenarioFull: '11375075645.97',
  deltaFull: '-114461186.25', eventId: 'FOD_NEG', eventDate: '2026-11-15', scale: '1',
  includedEffects: 84, excludedEffects: 0, historicalEffects: 84,
  byEntity: [{ entityId: 'SUB_FOD_JP_01', name: 'Caldriva Foods Japan KK', deltaFull: '-50000000.00' }],
};
export const FORECAST_GRAPH: Extract<ForecastSimulationOutput, { ok: true }>['graph'] = {
  effects: 84, activities: 84, contracts: 6, evidence: 2, metrics: 28, kpis: 15,
};

// 条件に応じて結果を返す API のスタブ。呼び出しは記録する。
export function stubApi(over: Partial<Api> = {}): Api & { calls: { simulate: unknown[]; eventPaths: string[]; loadModel: number } } {
  const calls = { simulate: [] as unknown[], eventPaths: [] as string[], loadModel: 0 };
  return {
    calls,
    loadModel: async () => {
      calls.loadModel += 1;
      return { ok: true, source: 'loaded', model: MODEL };
    },
    simulate: async (scenario) => {
      calls.simulate.push(scenario);
      const weaker = scenario.fx !== undefined && Number(scenario.fx.factor) > 1;
      const touched = scenario.fx !== undefined || (scenario.events !== undefined && Object.keys(scenario.events).length > 0);
      return { ok: true, source: 'cache', result: weaker ? INCREASE_RESULT : touched ? SCENARIO_RESULT : BASE_RESULT };
    },
    eventPaths: async (eventId) => {
      calls.eventPaths.push(eventId);
      return { ok: true, eventId, paths: PATHS };
    },
    loadForecast: async () => FORECAST_LOADED,
    simulateForecast: async (scenario) => ({
      ok: true,
      result: { ...FORECAST_RESULT, eventId: scenario.eventId, eventDate: scenario.eventDate, scale: String(scenario.scale) },
      graph: FORECAST_GRAPH,
    }),
    ...over,
  };
}
