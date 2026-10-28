import type { Api } from '@/lib/api';
import type { EventPathsOutput, LoadModelOutput, SimulateOutput } from '@/lib/types';

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
    ...over,
  };
}
