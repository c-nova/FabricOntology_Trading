import assert from 'node:assert/strict';
import { before, describe, it } from 'node:test';
import { Decimal } from '../src/decimal.js';
import { DataError, prepare, ScenarioError, simulateFuture } from '../src/index.js';
import type { BaseData, FutureBaseline, FuturePath, FutureScenario, Prepared } from '../src/index.js';
import { loadLocalDataset } from '../src/local-loader.js';

const baseline: FutureBaseline = {
  asOf: '2024-03-01',
  period: { from: '2024-04-01', to: '2024-06-30' },
  amountFull: '100.00',
};
const scenario: FutureScenario = { eventId: 'EVENT', eventDate: '2024-04-01', scale: 1 };

function smallData(): BaseData {
  return {
    companies: [
      { entityId: 'B', entityName: 'Beta', sectorCode: 'S', countryCode: 'JP', currencyCode: 'JPY', ownershipRatio: '1' },
      { entityId: 'A', entityName: 'Alpha', sectorCode: 'S', countryCode: 'JP', currencyCode: 'JPY', ownershipRatio: '1' },
    ],
    ebitdaRows: [
      { metricId: 'a', date: '2024-02-29', entityId: 'A', amountLocal: '0', fxRateToGroup: '1', amountGroup: '0', managementJpy: '0' },
      { metricId: 'b', date: '2024-03-01', entityId: 'B', amountLocal: '0', fxRateToGroup: '1', amountGroup: '0', managementJpy: '0' },
      { metricId: 'c', date: '2024-02-29', entityId: 'B', amountLocal: '0', fxRateToGroup: '1', amountGroup: '0', managementJpy: '0' },
    ],
    effects: [
      { effectId: '1', eventId: 'EVENT', entityId: 'A', effectDate: '2024-02-29', metricId: 'a', deltaEbitdaLocal: '1', fxRateToGroup: '1', ownershipRatio: '1', deltaEbitdaFullJpy: '-0.01', deltaManagementJpy: '1' },
      { effectId: '2', eventId: 'EVENT', entityId: 'A', effectDate: '2024-02-29', metricId: 'a', deltaEbitdaLocal: '1', fxRateToGroup: '1', ownershipRatio: '1', deltaEbitdaFullJpy: '-0.01', deltaManagementJpy: '1' },
      { effectId: '3', eventId: 'EVENT', entityId: 'B', effectDate: '2024-03-01', metricId: 'b', deltaEbitdaLocal: '1', fxRateToGroup: '1', ownershipRatio: '1', deltaEbitdaFullJpy: '3.02', deltaManagementJpy: '1' },
      { effectId: '4', eventId: 'EVENT', entityId: 'B', effectDate: '2024-02-29', metricId: 'c', deltaEbitdaLocal: '1', fxRateToGroup: '1', ownershipRatio: '1', deltaEbitdaFullJpy: '1.00', deltaManagementJpy: '1' },
    ],
    events: [{ eventId: 'EVENT', primarySector: 'S', direction: 'negative', severity: 1, startDate: '2024-02-28', endDate: '2024-03-01', narrative: '' }],
  };
}

function pathsFor(p: Prepared, eventId = 'EVENT'): FuturePath[] {
  return p.effects.filter((e) => e.eventId === eventId).map((e) => ({
    effectId: e.effectId, entityId: e.entityId, metricId: e.row.metricId,
  }));
}

const errorCode = (code: string) => (error: unknown) => error instanceof ScenarioError && error.code === code;
let p: Prepared;
let paths: FuturePath[];

before(() => {
  p = prepare(smallData());
  paths = pathsFor(p);
});

describe('future overlay calculation', () => {
  it('uses each full JPY effect at 0%, 100%, and 300%, with deterministic company totals', () => {
    for (const [scale, delta, expectedScenario, a, b] of [
      [0, '0.00', '100.00', '0.00', '0.00'],
      [1, '4.00', '104.00', '-0.02', '4.02'],
      [3, '12.00', '112.00', '-0.06', '12.06'],
    ] as const) {
      assert.deepEqual(simulateFuture(p, baseline, { ...scenario, scale }, paths), {
        period: baseline.period, asOf: baseline.asOf, baselineFull: '100.00', scenarioFull: expectedScenario,
        deltaFull: delta, eventId: 'EVENT', eventDate: scenario.eventDate, scale: String(scale),
        includedEffects: 4, excludedEffects: 0, historicalEffects: 4,
        byEntity: [{ entityId: 'A', name: 'Alpha', deltaFull: a }, { entityId: 'B', name: 'Beta', deltaFull: b }],
      });
    }
  });

  it('rounds each scaled row before summing and rounds the full-quarter baseline once', () => {
    const r = simulateFuture(p, { ...baseline, amountFull: '100.005' }, { ...scenario, scale: 0.5 }, paths);
    assert.equal(r.baselineFull, '100.01');
    assert.equal(r.deltaFull, '1.99');
    assert.equal(r.scenarioFull, '102.00');
    assert.deepEqual(r.byEntity.map((e) => e.deltaFull), ['-0.02', '2.01']);
    const negative = simulateFuture(p, { ...baseline, amountFull: '-0.005' }, { ...scenario, scale: 0 }, paths);
    assert.equal(negative.baselineFull, '-0.01');
    assert.equal(negative.scenarioFull, '-0.01');
  });

  it('clips after the quarter end, including when no projected effect fits', () => {
    const late = simulateFuture(p, baseline, { ...scenario, eventDate: '2024-06-29' }, paths);
    assert.equal(late.includedEffects, 3);
    assert.equal(late.excludedEffects, 1);
    assert.equal(late.deltaFull, '0.98');
    assert.deepEqual(late.byEntity.map((e) => e.deltaFull), ['-0.02', '1.00']);
    const last = simulateFuture(p, baseline, { ...scenario, eventDate: '2024-06-30' }, paths);
    assert.equal(last.historicalEffects, 4);
    assert.equal(last.includedEffects, 0);
    assert.equal(last.excludedEffects, 4);
    assert.equal(last.deltaFull, '0.00');
    assert.equal(last.scenarioFull, '100.00');
    assert.deepEqual(last.byEntity.map((e) => e.deltaFull), ['0.00', '0.00']);
  });

  it('handles leap days in both historical lag and the projected period in UTC', () => {
    const result = simulateFuture(p, {
      asOf: '2024-03-01', period: { from: '2028-02-28', to: '2028-02-29' }, amountFull: '7',
    }, { ...scenario, eventDate: '2028-02-28' }, paths);
    assert.equal(result.includedEffects, 3);
    assert.equal(result.excludedEffects, 1);
    assert.equal(result.deltaFull, '0.98');
    assert.equal(result.scenarioFull, '7.98');
  });

  it('normalizes ISO event start timestamps to a UTC date', () => {
    const data = smallData();
    data.events[0]!.startDate = '2024-02-28T15:00:00-09:00';
    const q = prepare(data);
    const r = simulateFuture(q, baseline, { ...scenario, eventDate: '2024-06-30' }, pathsFor(q));
    assert.equal(r.includedEffects, 3);
    assert.equal(r.excludedEffects, 1);
    assert.equal(r.deltaFull, '0.98');
  });

  it('is pure and independent of input and path ordering', () => {
    const first = simulateFuture(p, baseline, scenario, paths);
    const reversed: Prepared = { ...p, effects: [...p.effects].reverse() };
    assert.deepEqual(simulateFuture(reversed, baseline, scenario, [...paths].reverse()), first);
    assert.deepEqual(simulateFuture(p, baseline, scenario, paths), first);
    assert.deepEqual(paths, pathsFor(p));
  });
});

describe('future input and chronology validation', () => {
  it('rejects invalid calendar dates, malformed dates, inverted or nonfuture periods, and event dates outside the period', () => {
    const bad: [FutureBaseline, FutureScenario][] = [
      [{ ...baseline, asOf: '2023-02-29' }, scenario],
      [{ ...baseline, asOf: '2024-02-30' }, scenario],
      [{ ...baseline, asOf: '2024-03-01T00:00:00Z' }, scenario],
      [{ ...baseline, period: { from: '2024-04-31', to: '2024-06-30' } }, scenario],
      [{ ...baseline, period: { from: '2024-04-01', to: '2024-06-31' } }, scenario],
      [{ ...baseline, period: { from: '2024-06-01', to: '2024-05-01' } }, scenario],
      [{ ...baseline, period: { from: '2024-03-01', to: '2024-06-30' } }, scenario],
      [{ ...baseline, period: { from: '2024-02-29', to: '2024-06-30' } }, scenario],
      [baseline, { ...scenario, eventDate: '2024-02-30' }],
      [baseline, { ...scenario, eventDate: '2024-03-31' }],
      [baseline, { ...scenario, eventDate: '2024-07-01' }],
      [baseline, { ...scenario, eventDate: '2024-04-01T00:00:00Z' }],
    ];
    for (const [b, s] of bad) assert.throws(() => simulateFuture(p, b, s, paths), errorCode('BAD_PERIOD'));
  });

  it('rejects non-finite, non-number and out-of-range scales and unknown event IDs', () => {
    for (const scale of [NaN, Infinity, -Infinity, '1' as unknown as number]) {
      assert.throws(() => simulateFuture(p, baseline, { ...scenario, scale }, paths), errorCode('BAD_NUMBER'));
    }
    for (const scale of [-0.01, 3.01]) {
      assert.throws(() => simulateFuture(p, baseline, { ...scenario, scale }, paths), errorCode('OUT_OF_RANGE'));
    }
    assert.throws(() => simulateFuture(p, baseline, { ...scenario, eventId: 'event' }, paths), errorCode('UNKNOWN_EVENT'));
  });

  it('rejects malformed or future source event dates and future, pre-event, or invalid source effects', () => {
    for (const startDate of [
      '2024-02-30', '2024-02-28garbage', '2024-02-28T25:00:00Z',
      '2024-02-28T00:00:00', '2024-03-02', '2024-03-01T23:00:00-02:00',
    ]) {
      const data = smallData();
      data.events[0]!.startDate = startDate;
      assert.throws(() => simulateFuture(prepare(data), baseline, scenario, paths), DataError, startDate);
    }
    for (const effectDate of ['2024-03-02', '2024-02-27', '2024-02-30', '2024-02-29T00:00:00Z']) {
      const data = smallData();
      data.effects[0]!.effectDate = effectDate;
      assert.throws(() => simulateFuture(prepare(data), baseline, scenario, paths), DataError, effectDate);
    }
    const data = smallData();
    data.effects[0]!.effectDate = '2024-03-02';
    assert.throws(() => simulateFuture(prepare(data), baseline, scenario, paths.slice(1)), DataError);
  });

  it('rejects inconsistent source entities, dates, duplicate event/effect IDs and empty source effects', () => {
    const data = smallData();
    data.effects[0]!.entityId = 'B';
    assert.throws(() => simulateFuture(prepare(data), baseline, scenario, paths), DataError);
    const unknown = smallData();
    unknown.effects[0]!.entityId = 'UNKNOWN';
    assert.throws(() => simulateFuture(prepare(unknown), baseline, scenario, paths), DataError);
    const mismatchedDate = smallData();
    mismatchedDate.effects[0]!.effectDate = '2024-03-01';
    assert.throws(() => simulateFuture(prepare(mismatchedDate), baseline, scenario, paths), DataError);
    assert.throws(() => simulateFuture({ ...p, events: [...p.events, p.events[0]!] }, baseline, scenario, paths), DataError);
    assert.throws(() => simulateFuture({ ...p, effects: [...p.effects, p.effects[0]!] }, baseline, scenario, paths), DataError);
    assert.throws(() => simulateFuture({ ...p, effects: [] }, baseline, scenario, paths), DataError);
  });
});

describe('Graph path verification', () => {
  it('requires all and only the exact paths, not just the same count', () => {
    const bad: FuturePath[][] = [
      [],
      paths.slice(1),
      [...paths, paths[0]!],
      [paths[0]!, paths[0]!, ...paths.slice(2)],
      [{ ...paths[0]!, effectId: 'missing' }, ...paths.slice(1)],
      [{ ...paths[0]!, effectId: '' }, ...paths.slice(1)],
      [{ ...paths[0]!, entityId: '' }, ...paths.slice(1)],
      [{ ...paths[0]!, metricId: '' }, ...paths.slice(1)],
      [{ ...paths[0]!, entityId: 'B' }, ...paths.slice(1)],
      [{ ...paths[0]!, metricId: 'b' }, ...paths.slice(1)],
      [...paths, { effectId: 'extra', entityId: 'A', metricId: 'a' }],
    ];
    for (const graph of bad) assert.throws(() => simulateFuture(p, baseline, scenario, graph), DataError);
    assert.throws(() => simulateFuture(p, baseline, scenario, undefined as unknown as FuturePath[]), DataError);
    assert.throws(() => simulateFuture(p, baseline, { ...scenario, scale: 0 }, paths.slice(1)), DataError);
    assert.throws(() => simulateFuture(p, baseline, { ...scenario, eventDate: '2024-06-30' }, paths.slice(1)), DataError);
  });
});

describe('amount safety', () => {
  it('rejects malformed and non-finite baselines and source effects', () => {
    for (const amountFull of ['', 'NaN', 'Infinity', ' 10', '0x10', '1e100', '1e38']) {
      assert.throws(() => simulateFuture(p, { ...baseline, amountFull }, scenario, paths), DataError, amountFull);
    }
    for (const amount of ['NaN', 'Infinity', '1e38']) {
      const q = { ...p, effects: p.effects.map((e, i) => i === 0 ? { ...e, full: new Decimal(amount) } : e) };
      assert.throws(() => simulateFuture(q, baseline, scenario, paths), DataError, amount);
    }
  });

  it('preserves cents in large decimal products and rejects unsafe results', () => {
    const q = { ...p, effects: [{ ...p.effects[0]!, full: new Decimal('1000000000000000000000000000000000.01') }] };
    const r = simulateFuture(q, { ...baseline, amountFull: '0' }, { ...scenario, scale: 1.0000000000000002 }, pathsFor(q));
    assert.equal(r.deltaFull, '1000000000000000200000000000000000.01');
    assert.throws(() => simulateFuture(p, { ...baseline, amountFull: '99999999999999999999999999999999999999.99' }, scenario, paths), DataError);
    const oversized = { ...p, effects: [{ ...p.effects[0]!, full: new Decimal('9e37') }] };
    assert.throws(() => simulateFuture(oversized, baseline, { ...scenario, scale: 3 }, pathsFor(oversized)), DataError);
  });

  it('sums exactly even if intermediate subtotals exceed the safe output range', () => {
    const amounts = ['9e37', '9e37', '-9e37', '-9e37'];
    const effects = amounts.map((amount, i) => ({ ...p.effects[0]!, effectId: `E${i}`, full: new Decimal(amount) }));
    const q = { ...p, effects };
    const graph = pathsFor(q);
    const result = simulateFuture(q, { ...baseline, amountFull: '0' }, scenario, graph);
    assert.equal(result.deltaFull, '0.00');
    assert.deepEqual(result.byEntity.map((e) => e.deltaFull), ['0.00']);
    assert.deepEqual(simulateFuture({ ...q, effects: [...effects].reverse() }, { ...baseline, amountFull: '0' }, scenario, graph), result);
  });
});

describe('FOD_NEG historical fixture', () => {
  it('projects all 84 effects at 100% to the documented full JPY amount', () => {
    const fixture = prepare(loadLocalDataset().base);
    const graph = pathsFor(fixture, 'FOD_NEG');
    const b = { asOf: '2026-09-30', period: { from: '2026-10-01', to: '2026-12-31' }, amountFull: '5000000000.00' };
    const s = { eventId: 'FOD_NEG', eventDate: '2026-10-01', scale: 1 };
    const r = simulateFuture(fixture, b, s, graph);
    assert.equal(r.historicalEffects, 84);
    assert.equal(r.includedEffects, 84);
    assert.equal(r.excludedEffects, 0);
    assert.equal(r.baselineFull, '5000000000.00');
    assert.equal(r.deltaFull, '-114461186.25');
    assert.equal(r.scenarioFull, '4885538813.75');
    assert.equal(r.byEntity.reduce((a, e) => a.plus(e.deltaFull), new Decimal(0)).toFixed(2), r.deltaFull);
    assert.ok(r.byEntity.every((e) => fixture.companies.get(e.entityId)?.name === e.name));
    const zero = simulateFuture(fixture, b, { ...s, scale: 0 }, graph);
    assert.equal(zero.deltaFull, '0.00');
    assert.equal(zero.scenarioFull, b.amountFull);
    const tripled = simulateFuture(fixture, b, { ...s, scale: 3 }, graph);
    assert.equal(tripled.deltaFull, '-343383558.75');
    assert.equal(tripled.scenarioFull, '4656616441.25');
    const lastDay = simulateFuture(fixture, b, { ...s, eventDate: '2026-12-31' }, graph);
    assert.equal(lastDay.includedEffects, 0);
    assert.equal(lastDay.excludedEffects, 84);
    assert.equal(lastDay.scenarioFull, b.amountFull);
  });
});
