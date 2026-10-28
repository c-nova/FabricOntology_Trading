import assert from 'node:assert/strict';
import { before, describe, it } from 'node:test';
import type { Decimal as DecimalBase } from 'decimal.js';
import { Decimal, money } from '../src/decimal.js';
import { prepare, reconcile, simulate, simulateRows, ScenarioError, DataError } from '../src/index.js';
import type { Prepared } from '../src/index.js';
import { loadLocalDataset, type LocalDataset } from '../src/local-loader.js';

// 文書に記載された値と、Step 3 のノートブックがクラウド上で出した値
const DOCUMENTED = {
  annualFull: '44757399732.84',
  annualManagement: '33547898914.09',
  fodNegFull: '-114461186.25',
  fodNegManagement: '-87630294.31',
  fodNegEffects: 84,
};

let ds: LocalDataset;
let p: Prepared;

before(() => {
  ds = loadLocalDataset();
  p = prepare(ds.base);
});

const D = (x: DecimalBase.Value) => new Decimal(x);
const sum = (xs: Iterable<string>) => [...xs].reduce((a, x) => a.plus(x), D(0));
const allEvents = (scale: number) => Object.fromEntries(p.events.map((e) => [e.eventId, scale]));

describe('保存値との照合（何も変えないとき）', () => {
  it('日次2,920行と効果1,344件が、保存値と同じ式で完全に再現できる', () => {
    const r = reconcile(p);
    assert.deepEqual(r, {
      rows: 2920,
      effects: 1344,
      groupMismatches: 0,
      managementMismatches: 0,
      effectFullMismatches: 0,
      effectManagementMismatches: 0,
      structuralIssues: [],
      ok: true,
    });
  });

  it('年間の実績EBITDAが文書の値と1銭まで一致する', () => {
    const r = simulate(p);
    assert.equal(r.base.full, DOCUMENTED.annualFull);
    assert.equal(r.base.management, DOCUMENTED.annualManagement);
    assert.deepEqual(r.scenario, r.base);
    assert.deepEqual(r.delta, { full: '0.00', management: '0.00' });
    assert.equal(r.stats.rowsTouched, 0);
  });

  it('日次のEBITDAが、KPI表（kpi_snapshot）の日次値と全日一致する', () => {
    const rows = simulateRows(p);
    const byDate = new Map<string, { full: Decimal; mgmt: Decimal }>();
    for (const r of rows) {
      const a = byDate.get(r.date) ?? { full: D(0), mgmt: D(0) };
      a.full = a.full.plus(r.group);
      a.mgmt = a.mgmt.plus(r.management);
      byDate.set(r.date, a);
    }
    const kpi = ds.reference.kpiDaily.filter((k) => k.scenario === 'actual');
    assert.equal(kpi.length, 730);
    for (const k of kpi) {
      const a = byDate.get(k.date)!;
      const expected = k.code === 'EBITDA_FULL_CONSOLIDATED' ? a.full : a.mgmt;
      assert.equal(expected.toFixed(2), D(k.amount).toFixed(2), `${k.code} ${k.date}`);
    }
  });

  it('Step 3 がクラウドで出した値（食品損失 −114,461,186.25 / 持分 −87,630,294.31、84件）と一致する', () => {
    const fod = simulate(p).eventImpacts.find((e) => e.eventId === 'FOD_NEG')!;
    assert.equal(fod.baseFull, DOCUMENTED.fodNegFull);
    assert.equal(fod.baseManagement, DOCUMENTED.fodNegManagement);
    assert.equal(fod.effects, DOCUMENTED.fodNegEffects);
  });
});

describe('全イベントを消すと、保存されているベースライン表になる', () => {
  it('2,920行すべてが、ベースラインの保存値と一致する', () => {
    const baseline = new Map(ds.reference.baselineRows.map((r) => [r.metricId.replace('_actual', '_baseline'), r]));
    assert.equal(baseline.size, 2920);
    let compared = 0;
    for (const row of simulateRows(p, { events: allEvents(0) })) {
      const ref = baseline.get(row.metricId.replace('_actual', '_baseline'))!;
      assert.equal(row.group, D(ref.amountGroup).toFixed(2), `group ${row.metricId}`);
      assert.equal(row.management, D(ref.managementJpy).toFixed(2), `management ${row.metricId}`);
      compared += 1;
    }
    assert.equal(compared, 2920);
  });

  it('合計も、ベースライン表の合計と一致する', () => {
    const r = simulate(p, { events: allEvents(0) });
    assert.equal(r.scenario.full, sum(ds.reference.baselineRows.map((b) => b.amountGroup)).toFixed(2));
    assert.equal(r.scenario.management, sum(ds.reference.baselineRows.map((b) => b.managementJpy)).toFixed(2));
  });
});

// エンジンとは別に、素朴に書いた総当たりの実装
function brute(scenario: { scale?: Record<string, number>; fx?: number; own?: Record<string, number> }) {
  const company = new Map(ds.base.companies.map((c) => [c.entityId, c]));
  const effectsByMetric = new Map<string, typeof ds.base.effects>();
  for (const e of ds.base.effects) effectsByMetric.set(e.metricId, [...(effectsByMetric.get(e.metricId) ?? []), e]);
  let full = D(0);
  let mgmt = D(0);
  for (const r of ds.base.ebitdaRows) {
    const c = company.get(r.entityId)!;
    let local = D(r.amountLocal);
    for (const e of effectsByMetric.get(r.metricId) ?? []) {
      const s = scenario.scale?.[e.eventId];
      if (s !== undefined) local = local.minus(D(e.deltaEbitdaLocal).times(D(1).minus(s)));
    }
    const fx = D(r.fxRateToGroup).times(c.currencyCode === 'USD' && scenario.fx !== undefined ? scenario.fx : 1);
    const own = scenario.own?.[r.entityId] ?? c.ownershipRatio;
    const untouched =
      !(effectsByMetric.get(r.metricId) ?? []).some((e) => scenario.scale?.[e.eventId] !== undefined && scenario.scale[e.eventId] !== 1) &&
      !(c.currencyCode === 'USD' && scenario.fx !== undefined && scenario.fx !== 1) &&
      scenario.own?.[r.entityId] === undefined;
    full = full.plus(untouched ? r.amountGroup : money(local.times(fx)));
    mgmt = mgmt.plus(untouched ? r.managementJpy : money(local.times(fx).times(own)));
  }
  return { full: full.toFixed(2), management: mgmt.toFixed(2) };
}

// 段階ごと（イベントのみ → 為替を追加 → 持分を追加）の合計。エンジンの段階分けとは別に素朴に書く
function bruteStages(scenario: { scale?: Record<string, number>; fx?: number; own?: Record<string, number> }) {
  const company = new Map(ds.base.companies.map((c) => [c.entityId, c]));
  const effectsByMetric = new Map<string, typeof ds.base.effects>();
  for (const e of ds.base.effects) effectsByMetric.set(e.metricId, [...(effectsByMetric.get(e.metricId) ?? []), e]);
  const acc = { s1: [D(0), D(0)], s2: [D(0), D(0)], s3: [D(0), D(0)] };
  for (const r of ds.base.ebitdaRows) {
    const c = company.get(r.entityId)!;
    const es = effectsByMetric.get(r.metricId) ?? [];
    let local = D(r.amountLocal);
    let eventTouched = false;
    for (const e of es) {
      const s = scenario.scale?.[e.eventId];
      if (s !== undefined && s !== 1) {
        local = local.minus(D(e.deltaEbitdaLocal).times(D(1).minus(s)));
        eventTouched = true;
      }
    }
    const fxTouched = c.currencyCode === 'USD' && scenario.fx !== undefined && scenario.fx !== 1;
    const ownTouched = scenario.own?.[r.entityId] !== undefined;
    const fx0 = D(r.fxRateToGroup);
    const fx1 = fxTouched ? fx0.times(scenario.fx!) : fx0;
    const own0 = D(c.ownershipRatio);
    const own1 = ownTouched ? D(scenario.own![r.entityId]!) : own0;
    const stage = (touched: boolean, fx: Decimal, own: Decimal): [Decimal, Decimal] =>
      touched ? [money(local.times(fx)), money(local.times(fx).times(own))] : [D(r.amountGroup), D(r.managementJpy)];
    const s1 = stage(eventTouched, fx0, own0);
    const s2 = stage(eventTouched || fxTouched, fx1, own0);
    const s3 = stage(eventTouched || fxTouched || ownTouched, fx1, own1);
    for (const [k, v] of [['s1', s1], ['s2', s2], ['s3', s3]] as const) {
      acc[k][0] = acc[k][0].plus(v[0]);
      acc[k][1] = acc[k][1].plus(v[1]);
    }
  }
  const t = (v: Decimal[]) => ({ full: v[0]!.toFixed(2), management: v[1]!.toFixed(2) });
  return { s1: t(acc.s1), s2: t(acc.s2), s3: t(acc.s3) };
}

describe('段階ごとの値が、独立した実装と一致する', () => {
  const cases: [string, Parameters<typeof simulate>[1], Parameters<typeof brute>[0]][] = [
    ['イベントだけ', { events: { FOD_NEG: 0.5 } }, { scale: { FOD_NEG: 0.5 } }],
    ['為替だけ', { fx: { factor: 0.9 } }, { fx: 0.9 }],
    ['持分だけ', { ownership: { SUB_FOD_JP_01: 1 } }, { own: { SUB_FOD_JP_01: 1 } }],
    ['イベントと為替', { events: { FOD_NEG: 0.5 }, fx: { factor: 0.9 } }, { scale: { FOD_NEG: 0.5 }, fx: 0.9 }],
    ['全部入り', { events: { FOD_NEG: 0, ENE_NEG: 0.7 }, fx: { factor: 0.85 }, ownership: { SUB_ENE_US_01: 1, SUB_FOD_JP_01: 0.3 } }, { scale: { FOD_NEG: 0, ENE_NEG: 0.7 }, fx: 0.85, own: { SUB_ENE_US_01: 1, SUB_FOD_JP_01: 0.3 } }],
  ];
  for (const [name, scenario, ref] of cases) {
    it(name, () => {
      const r = simulate(p, scenario);
      const b = bruteStages(ref);
      const base = r.base;
      const diff = (x: { full: string; management: string }, y: { full: string; management: string }) => ({
        full: D(x.full).minus(y.full).toFixed(2),
        management: D(x.management).minus(y.management).toFixed(2),
      });
      assert.deepEqual(r.steps.events, diff(b.s1, base), 'steps.events');
      assert.deepEqual(r.steps.fx, diff(b.s2, b.s1), 'steps.fx');
      assert.deepEqual(r.steps.ownership, diff(b.s3, b.s2), 'steps.ownership');
      assert.deepEqual(r.scenario, b.s3, 'scenario');
    });
  }
});

describe('エンジンと、独立した総当たり実装の一致', () => {
  const cases: [string, Parameters<typeof simulate>[1], Parameters<typeof brute>[0]][] = [
    ['食品損失を50%軽減', { events: { FOD_NEG: 0.5 } }, { scale: { FOD_NEG: 0.5 } }],
    ['円高10%', { fx: { factor: 0.9 } }, { fx: 0.9 }],
    ['円安10%', { fx: { factor: 1.1 } }, { fx: 1.1 }],
    ['食品損失50%軽減 + 円高10%', { events: { FOD_NEG: 0.5 }, fx: { factor: 0.9 } }, { scale: { FOD_NEG: 0.5 }, fx: 0.9 }],
    ['複数イベントを同時に調整', { events: { FOD_NEG: 0.3, CROSS_NEG: 1.5, MTL_POS: 0 } }, { scale: { FOD_NEG: 0.3, CROSS_NEG: 1.5, MTL_POS: 0 } }],
    ['持分の変更 + 為替', { ownership: { SUB_FOD_JP_01: 1, SUB_MTL_US_01: 0.8 }, fx: { factor: 1.05 } }, { own: { SUB_FOD_JP_01: 1, SUB_MTL_US_01: 0.8 }, fx: 1.05 }],
    ['全部入り', { events: { FOD_NEG: 0, ENE_NEG: 0.7 }, fx: { factor: 0.85 }, ownership: { SUB_ENE_US_01: 1 } }, { scale: { FOD_NEG: 0, ENE_NEG: 0.7 }, fx: 0.85, own: { SUB_ENE_US_01: 1 } }],
  ];
  for (const [name, scenario, bruteScenario] of cases) {
    it(name, () => {
      const r = simulate(p, scenario);
      const b = brute(bruteScenario);
      assert.equal(r.scenario.full, b.full);
      assert.equal(r.scenario.management, b.management);
    });
  }
});

describe('比例の期待値との差（丸めの粒度）', () => {
  it('食品損失を50%軽減すると、比例配分の +57,230,593.13 円と一致する', () => {
    const r = simulate(p, { events: { FOD_NEG: 0.5 } });
    assert.equal(r.delta.full, '57230593.13');
  });

  it('食品損失を消すと +114,461,186.25 円との差は2銭（行ごとの丸めの粒度）', () => {
    const r = simulate(p, { events: { FOD_NEG: 0 } });
    assert.equal(r.delta.full, '114461186.23');
    assert.ok(D(r.delta.full).minus(D(DOCUMENTED.fodNegFull).neg()).abs().lte('0.05'));
  });

  it('円高10%は、合計に10%を掛けた近似（−2,328,820,955.84）と1円以内', () => {
    const r = simulate(p, { fx: { factor: 0.9 } });
    assert.ok(D(r.delta.full).minus('-2328820955.84').abs().lt(1), r.delta.full);
    assert.ok(D(r.delta.management).minus('-1409756134.73').abs().lt(1), r.delta.management);
  });
});

describe('イベント別の影響額（効果の粒度）', () => {
  const effects = () => ds.base.effects;
  const bruteImpact = (eventId: string, scale: number, fx: number, own?: Record<string, number>) => {
    const company = new Map(ds.base.companies.map((c) => [c.entityId, c]));
    let full = D(0);
    let mgmt = D(0);
    for (const e of effects().filter((x) => x.eventId === eventId)) {
      const c = company.get(e.entityId)!;
      const local = D(e.deltaEbitdaLocal).times(scale);
      const rate = D(e.fxRateToGroup).times(c.currencyCode === 'USD' ? fx : 1);
      full = full.plus(money(local.times(rate)));
      mgmt = mgmt.plus(money(local.times(rate).times(own?.[e.entityId] ?? e.ownershipRatio)));
    }
    return { full: full.toFixed(2), management: mgmt.toFixed(2) };
  };

  it('倍率と為替と持分を反映した影響額が、独立した計算と一致する', () => {
    const own = { SUB_FOD_JP_01: 1 };
    const r = simulate(p, { events: { FOD_NEG: 0.5, CROSS_NEG: 2 }, fx: { factor: 0.9 }, ownership: own });
    for (const [id, scale] of [['FOD_NEG', 0.5], ['CROSS_NEG', 2], ['MTL_POS', 1]] as const) {
      const got = r.eventImpacts.find((e) => e.eventId === id)!;
      const want = bruteImpact(id, scale, 0.9, own);
      assert.equal(got.scenarioFull, want.full, `${id} full`);
      assert.equal(got.scenarioManagement, want.management, `${id} management`);
      assert.equal(got.scale, String(scale));
    }
  });

  it('何も変えなければ、保存値そのもの', () => {
    for (const e of simulate(p).eventImpacts) {
      assert.equal(e.scenarioFull, e.baseFull, e.eventId);
      assert.equal(e.scenarioManagement, e.baseManagement, e.eventId);
    }
  });

  it('為替だけを変えると、JPY建ての効果は動かず、USD建ての効果だけが動く', () => {
    const r = simulate(p, { fx: { factor: 0.5 } });
    const fod = r.eventImpacts.find((e) => e.eventId === 'FOD_NEG')!;
    const jpy = effects().filter((e) => e.eventId === 'FOD_NEG' && e.entityId.endsWith('_JP_01'));
    const usd = effects().filter((e) => e.eventId === 'FOD_NEG' && e.entityId.endsWith('_US_01'));
    const jpySum = jpy.reduce((a, e) => a.plus(e.deltaEbitdaFullJpy), D(0));
    const usdBase = usd.reduce((a, e) => a.plus(e.deltaEbitdaFullJpy), D(0));
    assert.equal(fod.baseFull, jpySum.plus(usdBase).toFixed(2));
    assert.ok(D(fod.scenarioFull).minus(jpySum).minus(usdBase.times(0.5)).abs().lt(1));
  });
});

describe('結果に添える情報', () => {
  it('適用した内容が、正規化された文字列で返る', () => {
    const r = simulate(p, { fx: { factor: 0.9 }, events: { FOD_NEG: 0.5, MTL_NEG: 1 }, ownership: { SUB_FOD_JP_01: 1, SUB_MTL_US_01: 0.51 } });
    assert.deepEqual(r.applied, {
      fx: { currency: 'USD', factor: '0.9' },
      events: { FOD_NEG: '0.5', MTL_NEG: '1' },
      ownership: { SUB_FOD_JP_01: '1', SUB_MTL_US_01: '0.51' },
    });
    assert.deepEqual(simulate(p).applied, { fx: null, events: {}, ownership: {} });
    assert.deepEqual(r.period, { from: '2025-10-01', to: '2026-09-30' });
  });

  it('再計算した行数が分かり、触れない行は数えない', () => {
    assert.equal(simulate(p, {}).stats.rowsTouched, 0);
    assert.equal(simulate(p, { events: { FOD_NEG: 1 } }).stats.rowsTouched, 0);
    assert.equal(simulate(p, { fx: { factor: 1 } }).stats.rowsTouched, 0);
    assert.equal(simulate(p, { ownership: { SUB_FOD_JP_01: 0.51 } }).stats.rowsTouched, 0);
    assert.equal(simulate(p, { fx: { factor: 0.9 } }).stats.rowsTouched, 1460);
    assert.equal(simulate(p, { ownership: { SUB_FOD_JP_01: 1 } }).stats.rowsTouched, 365);
    const fod = simulate(p, { events: { FOD_NEG: 0 } });
    const rows = new Set(ds.base.effects.filter((e) => e.eventId === 'FOD_NEG').map((e) => e.metricId));
    assert.equal(fod.stats.rowsTouched, rows.size);
    assert.equal(fod.stats.rows, 2920);
  });
});

describe('集計のキー', () => {
  it('業種別のキーは業種コード、子会社別のキーは子会社IDで、名称が付く', () => {
    const r = simulate(p);
    assert.deepEqual(r.bySector.map((x) => x.key), [...new Set(ds.base.companies.map((c) => c.sectorCode))].sort());
    assert.deepEqual(r.byEntity.map((x) => x.key), ds.base.companies.map((c) => c.entityId).sort());
    assert.ok(r.byEntity.every((x) => x.label === ds.base.companies.find((c) => c.entityId === x.key)!.entityName));
    assert.equal(r.bySector.length, 4);
  });
});

describe('分解と集計の整合', () => {
  const scenario = { events: { FOD_NEG: 0.5, CROSS_NEG: 0.8 }, fx: { factor: 0.9 }, ownership: { SUB_FOD_JP_01: 1 } };

  it('イベント → 為替 → 持分の3段階の合計が、全体の差と厳密に一致する', () => {
    const r = simulate(p, scenario);
    for (const k of ['full', 'management'] as const) {
      assert.equal(sum([r.steps.events[k], r.steps.fx[k], r.steps.ownership[k]]).toFixed(2), r.delta[k]);
    }
    assert.equal(r.steps.ownership.full, '0.00');
  });

  it('子会社別・業種別・月別の合計が、全体と厳密に一致する', () => {
    const r = simulate(p, scenario);
    for (const dim of [r.byEntity, r.bySector, r.byMonth]) {
      for (const k of ['full', 'management'] as const) {
        assert.equal(sum(dim.map((d) => d.scenario[k])).toFixed(2), r.scenario[k]);
        assert.equal(sum(dim.map((d) => d.base[k])).toFixed(2), r.base[k]);
        assert.equal(sum(dim.map((d) => d.delta[k])).toFixed(2), r.delta[k]);
      }
    }
    assert.equal(r.byEntity.length, 8);
    assert.equal(r.byMonth.length, 12);
  });

  it('持分の変更は持分管理EBITDAにだけ効き、差は「全額 − 持分管理」に一致する', () => {
    const r = simulate(p, { ownership: { SUB_FOD_JP_01: 1 } });
    const e = r.byEntity.find((x) => x.key === 'SUB_FOD_JP_01')!;
    assert.equal(r.delta.full, '0.00');
    assert.equal(r.delta.management, D(e.base.full).minus(e.base.management).toFixed(2));
  });

  it('JPY建ての子会社は為替の影響を受けない', () => {
    const r = simulate(p, { fx: { factor: 0.5 } });
    for (const e of r.byEntity.filter((x) => x.key.endsWith('_JP_01'))) {
      assert.deepEqual(e.delta, { full: '0.00', management: '0.00' }, e.key);
    }
    assert.ok(r.byEntity.filter((x) => x.key.endsWith('_US_01')).every((e) => D(e.delta.full).lt(0)));
  });
});

describe('期間の指定', () => {
  it('12か月の合計が年間と一致し、1か月だけの指定は、その月の値になる', () => {
    const s = { events: { FOD_NEG: 0.5 }, fx: { factor: 0.9 } };
    const year = simulate(p, s);
    const parts = year.byMonth.map((m) => simulate(p, { ...s, period: { from: `${m.key}-01`, to: `${m.key}-31` } }));
    assert.equal(sum(parts.map((x) => x.scenario.full)).toFixed(2), year.scenario.full);
    assert.equal(sum(parts.map((x) => x.delta.management)).toFixed(2), year.delta.management);
    const feb = year.byMonth.find((m) => m.key === '2026-02')!;
    assert.deepEqual(parts[year.byMonth.indexOf(feb)]!.scenario, feb.scenario);
  });

  it('イベント別の影響額も、期間で絞られる', () => {
    const r = simulate(p, { period: { from: '2026-02-01', to: '2026-02-28' } });
    const all = simulate(p).eventImpacts.reduce((n, e) => n + e.effects, 0);
    assert.ok(r.stats.effects > 0 && r.stats.effects < all);
  });
});

describe('入力の検証', () => {
  const code = (fn: () => unknown) => {
    try {
      fn();
    } catch (e) {
      assert.ok(e instanceof ScenarioError, String(e));
      return e.code;
    }
    return 'NO_ERROR';
  };

  it('範囲外・不正・未知の指定は、理由のコード付きで拒否する', () => {
    assert.equal(code(() => simulate(p, { fx: { factor: 0 } })), 'OUT_OF_RANGE');
    assert.equal(code(() => simulate(p, { fx: { factor: 11 } })), 'OUT_OF_RANGE');
    assert.equal(code(() => simulate(p, { fx: { factor: 'abc' } })), 'BAD_NUMBER');
    assert.equal(code(() => simulate(p, { fx: { currency: 'JPY', factor: 0.9 } })), 'UNSUPPORTED_CURRENCY');
    assert.equal(code(() => simulate(p, { fx: { currency: 'EUR', factor: 0.9 } })), 'UNSUPPORTED_CURRENCY');
    assert.equal(code(() => simulate(p, { events: { FOD_NEG: -0.1 } })), 'OUT_OF_RANGE');
    assert.equal(code(() => simulate(p, { events: { FOD_NEG: 3.01 } })), 'OUT_OF_RANGE');
    assert.equal(code(() => simulate(p, { events: { NO_SUCH: 0.5 } })), 'UNKNOWN_EVENT');
    assert.equal(code(() => simulate(p, { ownership: { NO_SUCH: 0.5 } })), 'UNKNOWN_ENTITY');
    assert.equal(code(() => simulate(p, { ownership: { SUB_FOD_JP_01: 1.01 } })), 'OUT_OF_RANGE');
    assert.equal(code(() => simulate(p, { period: { from: '2026-03-01', to: '2026-02-01' } })), 'BAD_PERIOD');
    assert.equal(code(() => simulate(p, { period: { from: '2026/03/01' } })), 'BAD_PERIOD');
  });

  it('境界値は受け付ける', () => {
    assert.equal(code(() => simulate(p, { fx: { factor: 0.1 }, events: { FOD_NEG: 3 }, ownership: { SUB_FOD_JP_01: 0 } })), 'NO_ERROR');
  });
});

describe('データの取り込みの検証', () => {
  it('不整合なデータは、取り込み時に拒否する', () => {
    const base = ds.base;
    assert.throws(() => prepare({ ...base, ebitdaRows: [] }), DataError);
    assert.throws(() => prepare({ ...base, ebitdaRows: [...base.ebitdaRows, base.ebitdaRows[0]!] }), /duplicate metric/);
    assert.throws(() => prepare({ ...base, effects: [...base.effects, { ...base.effects[0]!, effectId: 'X', metricId: 'NO_SUCH' }] }), /not an actual EBITDA row/);
    assert.throws(() => prepare({ ...base, effects: [...base.effects, base.effects[0]!] }), /duplicate effect/);
    assert.throws(() => prepare({ ...base, effects: [{ ...base.effects[0]!, eventId: 'NO_SUCH' }] }), /unknown event/);
  });

  it('保存値と食い違うデータは、自己検査で検出する', () => {
    const tampered = structuredClone(ds.base);
    tampered.ebitdaRows[10]!.amountGroup = '1.00';
    tampered.effects[5]!.deltaEbitdaFullJpy = '2.00';
    const r = reconcile(prepare(tampered));
    assert.equal(r.ok, false);
    assert.equal(r.groupMismatches, 1);
    assert.equal(r.effectFullMismatches, 1);
  });
});

describe('再実行しても結果が変わらない', () => {
  it('同じシナリオは同じ結果で、元データも変化しない', () => {
    const s = { events: { FOD_NEG: 0.25 }, fx: { factor: 0.93 } };
    const first = simulate(p, s);
    simulate(p, { events: allEvents(0), fx: { factor: 2 } });
    assert.deepEqual(simulate(p, s), first);
    assert.equal(simulate(p).base.full, DOCUMENTED.annualFull);
  });
});
