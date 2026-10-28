import { describe, expect, it } from 'vitest';

import { explainCode, explainThrown } from './errors';
import { buildChain, checkConsistency, defaultPathEvent, groupByEntity } from './paths';
import type { EventImpact, GraphPath, SimulationResult } from './types';
import { buildWaterfall, scalePosition } from './waterfall';

// 実機の eventPaths(FOD_NEG) の最初の行と同じ形
const path = (n: number, overrides: Partial<GraphPath> = {}): GraphPath => ({
  effectId: `E${n}`,
  entityId: n % 2 === 0 ? 'SUB_FOD_JP_01' : 'SUB_FOD_US_01',
  activityId: `A${n}`,
  activityType: 'external_sale',
  commodity: 'milling_wheat',
  contractId: `C${n % 3}`,
  evidenceId: `V${n}`,
  metricId: `M${n % 7}`,
  kpiId: `K${n % 7}`,
  ...overrides,
});

describe('buildChain', () => {
  it('ノードごとの件数は、重複を除いた件数になる', () => {
    const paths = Array.from({ length: 10 }, (_, i) => path(i));
    const chain = buildChain(paths);
    expect(chain.map((c) => c.type)).toEqual(['RiskEvent', 'FinancialEffect', 'Activity', 'Contract', 'FinancialMetric', 'GroupKPI']);
    expect(chain.map((c) => c.count)).toEqual([1, 10, 10, 3, 7, 7]);
  });

  it('関係の名前は、グラフの関係名のまま', () => {
    const chain = buildChain([path(1)]);
    expect(chain.map((c) => c.via)).toEqual([undefined, 'EventHasEffect', 'EffectOnActivity', 'ActivityUnderContract', 'EffectRealizedInMetric', 'MetricRollsUpToGroupKPI']);
  });

  it('名前は資料と同じ用語で、日次指標は影響額から分かれる', () => {
    const chain = buildChain([path(1)]);
    expect(chain.map((c) => c.label)).toEqual(['イベント', '影響額', '取引活動', '契約', '日次指標', '全社KPI']);
    expect(chain.filter((c) => c.from).map((c) => [c.type, c.from])).toEqual([['FinancialMetric', '影響額']]);
  });

  it('経路が空なら、イベントも 0 件', () => {
    expect(buildChain([]).map((c) => c.count)).toEqual([0, 0, 0, 0, 0, 0]);
  });
});

describe('checkConsistency', () => {
  const paths = Array.from({ length: 84 }, (_, i) => path(i));
  it('グラフの効果数と Lakehouse の効果数が同じなら一致', () => {
    expect(checkConsistency(paths, { effects: 84 })).toEqual({ graphEffects: 84, lakehouseEffects: 84, match: true });
  });
  it('違えば、不一致として数を返す（隠さない）', () => {
    expect(checkConsistency(paths, { effects: 90 })).toEqual({ graphEffects: 84, lakehouseEffects: 90, match: false });
  });
  it('同じ効果の重複行は、1 件と数える', () => {
    expect(checkConsistency([path(1), path(1)], { effects: 1 }).match).toBe(true);
  });
});

describe('groupByEntity / defaultPathEvent', () => {
  it('会社ごとに、効果数・活動種別・商品をまとめる', () => {
    const g = groupByEntity([path(0), path(1), path(2, { commodity: 'wheat_flour' })]);
    expect(g).toEqual([
      { entityId: 'SUB_FOD_JP_01', effects: 2, activityTypes: ['external_sale'], commodities: ['milling_wheat', 'wheat_flour'] },
      { entityId: 'SUB_FOD_US_01', effects: 1, activityTypes: ['external_sale'], commodities: ['milling_wheat'] },
    ]);
  });

  it('既定のイベントは、基準の影響額（絶対値）が最大のもの', () => {
    const impact = (eventId: string, baseFull: string): EventImpact => ({ eventId, scale: '1', effects: 1, baseFull, scenarioFull: baseFull, baseManagement: '0', scenarioManagement: '0' });
    expect(defaultPathEvent([impact('A', '-100'), impact('B', '250.5'), impact('C', '-300')])).toBe('C');
    expect(defaultPathEvent([])).toBeUndefined();
  });
});

describe('buildWaterfall', () => {
  // 実機の simulate（食品損失 50% 軽減 + 円高 10%）の steps と同じ値
  const result = {
    steps: {
      events: { full: '57230593.13', management: '43815147.15' },
      fx: { full: '-2331806168.90', management: '-1412741347.86' },
      ownership: { full: '0.00', management: '0.00' },
    },
    delta: { full: '-2274575575.77', management: '-1368926200.71' },
  } as unknown as SimulationResult;

  it('0 から積み上げ、最後に合計の差で終わる', () => {
    const w = buildWaterfall(result, 'full');
    expect(w.bars.map((b) => b.key)).toEqual(['events', 'fx', 'total']);
    expect(w.bars[0]).toMatchObject({ from: 0, to: 57230593.13, isTotal: false });
    expect(w.bars[1]!.from).toBeCloseTo(57230593.13);
    expect(w.bars[1]!.to).toBeCloseTo(57230593.13 - 2331806168.9);
    expect(w.bars[2]).toMatchObject({ from: 0, to: -2274575575.77, amount: '-2274575575.77', isTotal: true });
  });

  it('段階の差の合計が、合計の差に一致する（端数の丸めを除く）', () => {
    const w = buildWaterfall(result, 'full');
    const sum = w.bars.filter((b) => !b.isTotal).reduce((a, b) => a + Number(b.amount), 0);
    expect(Math.abs(sum - Number(w.bars[2]!.amount))).toBeLessThan(0.5);
  });

  it('軸は 0 を必ず含み、全ての棒が収まる', () => {
    const w = buildWaterfall(result, 'management');
    expect(w.min).toBeLessThanOrEqual(0);
    expect(w.max).toBeGreaterThanOrEqual(0);
    for (const b of w.bars) {
      expect(b.from).toBeGreaterThanOrEqual(w.min);
      expect(b.to).toBeLessThanOrEqual(w.max);
    }
  });

  it('持分が動いたときだけ、持分の段階を出す', () => {
    const moved = { ...result, steps: { ...result.steps, ownership: { full: '0.00', management: '2018852607.70' } } } as unknown as SimulationResult;
    expect(buildWaterfall(moved, 'management').bars.map((b) => b.key)).toEqual(['events', 'fx', 'ownership', 'total']);
  });

  it('何も変えない（全部 0）ときも、壊れない', () => {
    const zero = { steps: { events: { full: '0', management: '0' }, fx: { full: '0', management: '0' }, ownership: { full: '0', management: '0' } }, delta: { full: '0', management: '0' } } as unknown as SimulationResult;
    const w = buildWaterfall(zero, 'full');
    expect([w.min, w.max]).toEqual([0, 0]);
    expect(scalePosition(0, w.min, w.max)).toBe(0.5);
  });
});

describe('scalePosition', () => {
  it('範囲内の値を 0〜1 にする', () => {
    expect(scalePosition(0, -10, 30)).toBeCloseTo(0.25);
    expect(scalePosition(30, -10, 30)).toBe(1);
  });
});

describe('エラーの文言', () => {
  it('サーバーが返すコードは、すべて固有の文言を持つ', () => {
    for (const code of ['CAPACITY', 'AUTH', 'NOT_FOUND', 'AMBIGUOUS', 'RATE_LIMIT', 'UPSTREAM', 'UNKNOWN_EVENT', 'UNEXPECTED']) {
      const e = explainCode(code);
      expect(e.title.length, code).toBeGreaterThan(3);
      expect(e.action.length, code).toBeGreaterThan(3);
      expect(e.title, code).not.toBe(explainCode('___').title);
    }
  });

  it('容量の停止と権限の問題は、人が直す必要があると示す。一時的な失敗は、再試行でよい', () => {
    expect(explainCode('CAPACITY').needsOperator).toBe(true);
    expect(explainCode('AUTH').needsOperator).toBe(true);
    expect(explainCode('UPSTREAM').needsOperator).toBe(false);
    expect(explainCode('RATE_LIMIT').needsOperator).toBe(false);
  });

  it('未知のコードでも、内部のコードを見せずに案内する', () => {
    const e = explainCode('SOMETHING_NEW');
    expect(JSON.stringify(e)).not.toContain('SOMETHING_NEW');
  });

  it('例外は、メッセージの本文ではなく名前だけで判断する（URL や識別子を出さない）', () => {
    const net = new Error('POST https://secret-host.example/capacities/abc failed');
    net.name = 'NetworkError';
    const e = explainThrown(net);
    expect(JSON.stringify(e)).not.toContain('secret-host');
    expect(e.title).toContain('接続');
    const to = new Error('x');
    to.name = 'TimeoutError';
    expect(explainThrown(to).title).toContain('時間');
    expect(explainThrown('文字列')).toEqual(explainThrown(new Error('?')));
  });
});
