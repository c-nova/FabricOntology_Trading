import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { Decimal } from '../src/decimal.js';
import { DataError, prepare, quarterlySectors, simulate } from '../src/index.js';
import type { BaseData } from '../src/index.js';
import { loadLocalDataset } from '../src/local-loader.js';

const company = (entityId: string, sectorCode: string) => ({
  entityId, entityName: entityId, sectorCode, countryCode: 'JP', currencyCode: 'JPY', ownershipRatio: '1',
});
const row = (metricId: string, date: string, entityId: string, amount: string) => ({
  metricId, date, entityId, amountLocal: amount, fxRateToGroup: '1', amountGroup: amount, managementJpy: amount,
});

function small(rows: ReturnType<typeof row>[]): BaseData {
  return { companies: [company('A', 'metals'), company('B', 'energy')], ebitdaRows: rows, effects: [], events: [] };
}

describe('quarterlySectors', () => {
  it('sums exactly by calendar quarter and sector, and fills missing sectors with zero', () => {
    const p = prepare(small([
      row('1', '2025-12-31', 'A', '0.10'),
      row('2', '2025-12-31', 'B', '0.20'),
      row('3', '2026-01-01', 'A', '0.01'),
      row('4', '2026-02-28', 'A', '-0.04'),
      row('5', '2026-03-31', 'B', '1000000000000000000000.07'),
    ]));
    assert.deepEqual(quarterlySectors(p), [
      { key: '2025-10', from: '2025-12-31', to: '2025-12-31', days: 1, bySector: { energy: '0.20', metals: '0.10' }, total: '0.30' },
      {
        key: '2026-01', from: '2026-01-01', to: '2026-03-31', days: 3,
        bySector: { energy: '1000000000000000000000.07', metals: '-0.03' }, total: '1000000000000000000000.04',
      },
    ]);
  });

  it('puts every month in the right quarter and ignores row order', () => {
    const months = ['01', '03', '04', '06', '07', '09', '10', '12'];
    const rows = months.map((m, i) => row(`m${i}`, `2026-${m}-15`, 'A', String(i + 1)));
    const keys = quarterlySectors(prepare(small(rows))).map((q) => [q.key, q.total]);
    assert.deepEqual(keys, [['2026-01', '3.00'], ['2026-04', '7.00'], ['2026-07', '11.00'], ['2026-10', '15.00']]);
    const shuffled = prepare(small([...rows].reverse()));
    assert.deepEqual(quarterlySectors(shuffled).map((q) => [q.key, q.total]), keys);
  });

  it('does not change its input', () => {
    const p = prepare(small([row('1', '2026-01-01', 'A', '5'), row('2', '2026-01-02', 'B', '6')]));
    const before = JSON.stringify(p.rows.map((r) => [r.metricId, r.date, r.group.toString()]));
    quarterlySectors(p);
    assert.equal(JSON.stringify(p.rows.map((r) => [r.metricId, r.date, r.group.toString()])), before);
  });

  it('rejects a malformed date', () => {
    const p = prepare(small([row('1', '2026-01-01', 'A', '5')]));
    const bad = { ...p, rows: [{ ...p.rows[0]!, date: '2026-13-01' }] };
    assert.throws(() => quarterlySectors(bad), DataError);
    assert.throws(() => quarterlySectors({ ...p, rows: [{ ...p.rows[0]!, date: '2026/01/01' }] }), DataError);
  });
});

describe('quarterlySectors on the demo dataset', () => {
  const p = prepare(loadLocalDataset().base);
  const quarters = quarterlySectors(p);

  it('gives the four fiscal quarters, four sectors each, and they add up to the annual actual', () => {
    assert.deepEqual(quarters.map((q) => q.key), ['2025-10', '2026-01', '2026-04', '2026-07']);
    assert.deepEqual(quarters.map((q) => q.days), [92, 90, 91, 92]);
    for (const q of quarters) {
      assert.deepEqual(Object.keys(q.bySector), ['energy', 'finance', 'foods', 'metals']);
      const sum = Object.values(q.bySector).reduce((a, v) => a.plus(v), new Decimal(0));
      assert.equal(sum.toFixed(2), q.total);
    }
    const annual = quarters.reduce((a, q) => a.plus(q.total), new Decimal(0)).toFixed(2);
    assert.equal(annual, simulate(p).base.full);
    assert.equal(annual, '44757399732.84');
  });

  it('matches the quarter totals the forecast notebook used for its evaluation (億円)', () => {
    const oku = quarters.map((q) => new Decimal(q.total).div(100_000_000).toDecimalPlaces(3).toString());
    assert.deepEqual(oku, ['115.933', '103.649', '112.378', '115.614']);
    // ノートブックが検証に使った直近四半期の実績: 115.6138958151001 億円
    assert.equal(quarters[3]!.total, '11561389581.51');
  });
});
