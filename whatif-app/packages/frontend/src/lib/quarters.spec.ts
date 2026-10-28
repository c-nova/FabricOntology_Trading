import { describe, expect, it } from 'vitest';

import { FORECAST_LOADED, FORECAST_RESULT } from '@/test/fixtures';

import { buildChartQuarters, axisLabels, fiscalLabel, fiscalQuarter, monthsLabel, sectorsOf } from './quarters';

describe('会計四半期（10月始まり）', () => {
  it('このデモの年度の定義に合う', () => {
    expect(fiscalQuarter('2025-10-01')).toEqual({ fy: 2026, q: 1 });
    expect(fiscalQuarter('2025-12-31')).toEqual({ fy: 2026, q: 1 });
    expect(fiscalQuarter('2026-01-01')).toEqual({ fy: 2026, q: 2 });
    expect(fiscalQuarter('2026-04-01')).toEqual({ fy: 2026, q: 3 });
    expect(fiscalQuarter('2026-07-01')).toEqual({ fy: 2026, q: 4 });
    expect(fiscalQuarter('2026-09-30')).toEqual({ fy: 2026, q: 4 });
    expect(fiscalQuarter('2026-10-01')).toEqual({ fy: 2027, q: 1 });
    expect(fiscalLabel('2026-10-01')).toBe('FY27 Q1');
    expect(fiscalLabel('2099-12-31')).toBe('FY00 Q1');
  });

  it('不正な日付は、黙って通さない', () => {
    for (const bad of ['', '2026-13-01', '2026/10/01', 'x']) expect(() => fiscalQuarter(bad)).toThrow();
    expect(() => monthsLabel('2026-00')).toThrow();
    expect(monthsLabel('2026-10')).toBe('10〜12月');
    expect(monthsLabel('2026-01')).toBe('1〜3月');
  });
});

describe('axisLabels', () => {
  const q = { fiscal: 'FY27 Q1', months: '10〜12月' };

  it('広い幅では、そのまま2段に出す', () => {
    expect(axisLabels(q, false)).toEqual(['FY27 Q1', '10〜12月']);
  });

  it('狭い幅では、年度は残したまま短くする（26Q1 と 27Q1 を区別できる）', () => {
    expect(axisLabels(q, true)).toEqual(['27Q1', '10〜12']);
    expect(axisLabels({ fiscal: 'FY26 Q1', months: '10〜12月' }, true)[0]).not.toBe(axisLabels(q, true)[0]);
    expect(axisLabels({ fiscal: 'FY26 Q2', months: '1〜3月' }, true)).toEqual(['26Q2', '1〜3']);
  });
});

describe('buildChartQuarters', () => {
  it('過去4四半期の実績と、予測の1四半期を、古い順に並べる', () => {
    const q = buildChartQuarters(FORECAST_LOADED);
    expect(q.map((x) => [x.fiscal, x.months, x.kind])).toEqual([
      ['FY26 Q1', '10〜12月', 'actual'],
      ['FY26 Q2', '1〜3月', 'actual'],
      ['FY26 Q3', '4〜6月', 'actual'],
      ['FY26 Q4', '7〜9月', 'actual'],
      ['FY27 Q1', '10〜12月', 'forecast'],
    ]);
    expect(q.every((x) => !x.partial)).toBe(true);
    expect(q[3]!.total).toBeCloseTo(115.6138958151, 6);
    expect(q[4]!.total).toBeCloseTo(114.8953683222, 6);
  });

  it('業種別の積み上げは、金属・エネルギー・食品・金融の順で、合計に一致する', () => {
    const q = buildChartQuarters(FORECAST_LOADED);
    for (const x of q) {
      expect(x.sectors!.map((s) => s.code)).toEqual(['metals', 'energy', 'foods', 'finance']);
      expect(x.sectors!.reduce((a, s) => a + s.value, 0)).toBeCloseTo(x.total, 3);
    }
    expect(sectorsOf(q)).toEqual(['metals', 'energy', 'foods', 'finance']);
  });

  it('イベントを仮定した結果は、同じ予測期間のときだけ、予測の四半期に重ねる', () => {
    expect(buildChartQuarters(FORECAST_LOADED).at(-1)!.scenario).toBeUndefined();
    const withScenario = buildChartQuarters(FORECAST_LOADED, FORECAST_RESULT).at(-1)!;
    expect(withScenario.scenario).toBeCloseTo(113.7507564597, 6);
    const stale = { ...FORECAST_RESULT, period: { from: '2026-07-01', to: '2026-09-30' } };
    expect(buildChartQuarters(FORECAST_LOADED, stale).at(-1)!.scenario).toBeUndefined();
    expect(buildChartQuarters(FORECAST_LOADED, FORECAST_RESULT)[0]!.scenario).toBeUndefined();
  });

  it('予測の業種別が無いとき（古い保存結果）は、予測の四半期だけ内訳なしにする', () => {
    const q = buildChartQuarters({ ...FORECAST_LOADED, forecastBySector: null });
    expect(q.at(-1)!.sectors).toBeNull();
    expect(q[0]!.sectors).not.toBeNull();
    expect(sectorsOf(q)).toEqual(['metals', 'energy', 'foods', 'finance']);
  });

  it('一部の日しか入っていない四半期は、そう分かるようにする', () => {
    const history = FORECAST_LOADED.history.map((h, i) => (i === 0 ? { ...h, days: 40 } : h));
    expect(buildChartQuarters({ ...FORECAST_LOADED, history })[0]!.partial).toBe(true);
  });

  it('履歴の並びが逆でも、古い順になる', () => {
    const q = buildChartQuarters({ ...FORECAST_LOADED, history: [...FORECAST_LOADED.history].reverse() });
    expect(q.map((x) => x.key)).toEqual(['2025-10', '2026-01', '2026-04', '2026-07', '2026-10']);
  });
});
