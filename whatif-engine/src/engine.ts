import { Decimal, ONE, ZERO, fixed2, money } from './decimal.js';
import type {
  BaseData,
  Breakdown,
  EventImpact,
  EventRow,
  Reconciliation,
  RowResult,
  Scenario,
  ScenarioResult,
  TotalsWire,
} from './types.js';

const GROUP_CURRENCY = 'JPY';

// 実行環境のロケールに左右されない並べ替え
const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export const LIMITS = {
  fxFactor: { min: new Decimal('0.1'), max: new Decimal(10) },
  eventScale: { min: ZERO, max: new Decimal(3) },
  ownership: { min: ZERO, max: ONE },
} as const;

export type ScenarioErrorCode =
  | 'UNKNOWN_EVENT'
  | 'UNKNOWN_ENTITY'
  | 'UNSUPPORTED_CURRENCY'
  | 'OUT_OF_RANGE'
  | 'BAD_NUMBER'
  | 'BAD_PERIOD';

export class ScenarioError extends Error {
  readonly code: ScenarioErrorCode;
  constructor(code: ScenarioErrorCode, message: string) {
    super(message);
    this.name = 'ScenarioError';
    this.code = code;
  }
}

export class DataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DataError';
  }
}

export interface PreparedCompany {
  entityId: string;
  name: string;
  sector: string;
  currency: string;
  ownership: Decimal;
}

export interface PreparedEffect {
  effectId: string;
  eventId: string;
  entityId: string;
  date: string;
  currency: string;
  local: Decimal;
  fx: Decimal;
  own: Decimal;
  full: Decimal;
  mgmt: Decimal;
  row: PreparedRow;
}

export interface PreparedRow {
  metricId: string;
  date: string;
  month: string;
  entityId: string;
  sector: string;
  currency: string;
  local: Decimal;
  fx: Decimal;
  own: Decimal;
  group: Decimal;
  mgmt: Decimal;
  effects: PreparedEffect[];
}

export interface Prepared {
  readonly companies: ReadonlyMap<string, PreparedCompany>;
  readonly rows: readonly PreparedRow[];
  readonly effects: readonly PreparedEffect[];
  readonly events: readonly EventRow[];
  readonly firstDate: string;
  readonly lastDate: string;
}

export function prepare(base: BaseData): Prepared {
  const companies = new Map<string, PreparedCompany>();
  for (const c of base.companies) {
    if (companies.has(c.entityId)) throw new DataError(`duplicate company ${c.entityId}`);
    companies.set(c.entityId, {
      entityId: c.entityId,
      name: c.entityName,
      sector: c.sectorCode,
      currency: c.currencyCode,
      ownership: new Decimal(c.ownershipRatio),
    });
  }

  const byMetric = new Map<string, PreparedRow>();
  const rows: PreparedRow[] = [];
  for (const r of base.ebitdaRows) {
    const company = companies.get(r.entityId);
    if (!company) throw new DataError(`row ${r.metricId}: unknown entity ${r.entityId}`);
    if (byMetric.has(r.metricId)) throw new DataError(`duplicate metric ${r.metricId}`);
    const row: PreparedRow = {
      metricId: r.metricId,
      date: r.date,
      month: r.date.slice(0, 7),
      entityId: r.entityId,
      sector: company.sector,
      currency: company.currency,
      local: new Decimal(r.amountLocal),
      fx: new Decimal(r.fxRateToGroup),
      own: company.ownership,
      group: new Decimal(r.amountGroup),
      mgmt: new Decimal(r.managementJpy),
      effects: [],
    };
    byMetric.set(row.metricId, row);
    rows.push(row);
  }
  if (rows.length === 0) throw new DataError('no EBITDA rows');
  rows.sort((a, b) => (a.date === b.date ? cmp(a.entityId, b.entityId) : cmp(a.date, b.date)));

  const eventIds = new Set(base.events.map((e) => e.eventId));
  const seen = new Set<string>();
  const effects: PreparedEffect[] = [];
  for (const e of base.effects) {
    const row = byMetric.get(e.metricId);
    if (!row) throw new DataError(`effect ${e.effectId}: ${e.metricId} is not an actual EBITDA row`);
    if (seen.has(e.effectId)) throw new DataError(`duplicate effect ${e.effectId}`);
    if (!eventIds.has(e.eventId)) throw new DataError(`effect ${e.effectId}: unknown event ${e.eventId}`);
    seen.add(e.effectId);
    const effect: PreparedEffect = {
      effectId: e.effectId,
      eventId: e.eventId,
      entityId: e.entityId,
      date: e.effectDate,
      currency: row.currency,
      local: new Decimal(e.deltaEbitdaLocal),
      fx: new Decimal(e.fxRateToGroup),
      own: new Decimal(e.ownershipRatio),
      full: new Decimal(e.deltaEbitdaFullJpy),
      mgmt: new Decimal(e.deltaManagementJpy),
      row,
    };
    row.effects.push(effect);
    effects.push(effect);
  }

  return {
    companies,
    rows,
    effects,
    events: [...base.events].sort((a, b) => cmp(a.eventId, b.eventId)),
    firstDate: rows[0]!.date,
    lastDate: rows[rows.length - 1]!.date,
  };
}

interface Plan {
  fxCurrency: string;
  factor: Decimal;
  fxActive: boolean;
  fxGiven: boolean;
  // 倍率が 1 でないイベントだけ
  adjust: Map<string, Decimal>;
  scales: Map<string, Decimal>;
  // 現在の持分と異なる子会社だけ
  ownership: Map<string, Decimal>;
  ownershipGiven: Map<string, Decimal>;
  from: string;
  to: string;
}

function toDecimal(value: string | number, what: string): Decimal {
  let d: Decimal;
  try {
    d = new Decimal(value);
  } catch {
    throw new ScenarioError('BAD_NUMBER', `${what} is not a number`);
  }
  if (!d.isFinite()) throw new ScenarioError('BAD_NUMBER', `${what} is not a finite number`);
  return d;
}

function inRange(d: Decimal, min: Decimal, max: Decimal, what: string): Decimal {
  if (d.lt(min) || d.gt(max)) {
    throw new ScenarioError('OUT_OF_RANGE', `${what} must be between ${min.toString()} and ${max.toString()}`);
  }
  return d;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function resolve(p: Prepared, s: Scenario): Plan {
  const fxCurrency = (s.fx?.currency ?? 'USD').toUpperCase();
  let factor = ONE;
  if (s.fx) {
    factor = inRange(toDecimal(s.fx.factor, 'fx.factor'), LIMITS.fxFactor.min, LIMITS.fxFactor.max, 'fx.factor');
    if (fxCurrency === GROUP_CURRENCY) {
      throw new ScenarioError('UNSUPPORTED_CURRENCY', 'JPY is the group currency and its rate is fixed at 1');
    }
    if (![...p.companies.values()].some((c) => c.currency === fxCurrency)) {
      throw new ScenarioError('UNSUPPORTED_CURRENCY', `no company reports in ${fxCurrency}`);
    }
  }

  const eventIds = new Set(p.events.map((e) => e.eventId));
  const adjust = new Map<string, Decimal>();
  const scales = new Map<string, Decimal>();
  for (const [eventId, raw] of Object.entries(s.events ?? {})) {
    if (!eventIds.has(eventId)) throw new ScenarioError('UNKNOWN_EVENT', `unknown event ${eventId}`);
    const scale = inRange(toDecimal(raw, `events.${eventId}`), LIMITS.eventScale.min, LIMITS.eventScale.max, `events.${eventId}`);
    scales.set(eventId, scale);
    if (!scale.eq(ONE)) adjust.set(eventId, scale);
  }

  const ownership = new Map<string, Decimal>();
  const ownershipGiven = new Map<string, Decimal>();
  for (const [entityId, raw] of Object.entries(s.ownership ?? {})) {
    const company = p.companies.get(entityId);
    if (!company) throw new ScenarioError('UNKNOWN_ENTITY', `unknown entity ${entityId}`);
    const ratio = inRange(toDecimal(raw, `ownership.${entityId}`), LIMITS.ownership.min, LIMITS.ownership.max, `ownership.${entityId}`);
    ownershipGiven.set(entityId, ratio);
    if (!ratio.eq(company.ownership)) ownership.set(entityId, ratio);
  }

  const from = s.period?.from ?? p.firstDate;
  const to = s.period?.to ?? p.lastDate;
  if (!DATE.test(from) || !DATE.test(to) || from > to) {
    throw new ScenarioError('BAD_PERIOD', 'period must be YYYY-MM-DD dates with from <= to');
  }

  return {
    fxCurrency,
    factor,
    fxActive: !factor.eq(ONE),
    fxGiven: s.fx !== undefined,
    adjust,
    scales,
    ownership,
    ownershipGiven,
    from,
    to,
  };
}

interface Staged {
  g1: Decimal;
  m1: Decimal;
  g2: Decimal;
  m2: Decimal;
  g3: Decimal;
  m3: Decimal;
  touched: boolean;
}

// S0 = 実績（保存値）→ S1 = イベント調整後 → S2 = さらに為替 → S3 = さらに持分。
// 何も変わらない行は保存値をそのまま使う。変わる行だけ、生成側と同じ式（行ごとに小数2桁）で再計算する。
function stage(row: PreparedRow, plan: Plan): Staged {
  const eventTouched = plan.adjust.size > 0 && row.effects.some((e) => plan.adjust.has(e.eventId));
  const fxTouched = plan.fxActive && row.currency === plan.fxCurrency;
  const newOwn = plan.ownership.get(row.entityId);
  if (!eventTouched && !fxTouched && newOwn === undefined) {
    return { g1: row.group, m1: row.mgmt, g2: row.group, m2: row.mgmt, g3: row.group, m3: row.mgmt, touched: false };
  }

  // 効果の倍率は現地通貨でも丸めずに比例させる。現地で小数2桁に丸めると、USD 子会社では
  // 為替（約155円/ドル）で増幅され、50%でも期待値から約20円ずれる。丸めは円換算の行ごとにだけ行う
  let local = row.local;
  if (eventTouched) {
    for (const e of row.effects) {
      const scale = plan.adjust.get(e.eventId);
      if (scale !== undefined) local = local.minus(e.local.times(ONE.minus(scale)));
    }
  }
  const fx1 = fxTouched ? row.fx.times(plan.factor) : row.fx;
  const own1 = newOwn ?? row.own;
  const moved = eventTouched || fxTouched;

  const g1 = eventTouched ? money(local.times(row.fx)) : row.group;
  const m1 = eventTouched ? money(local.times(row.fx).times(row.own)) : row.mgmt;
  const g2 = moved ? money(local.times(fx1)) : row.group;
  const m2 = moved ? money(local.times(fx1).times(row.own)) : row.mgmt;
  const m3 = moved || newOwn !== undefined ? money(local.times(fx1).times(own1)) : row.mgmt;
  return { g1, m1, g2, m2, g3: g2, m3, touched: true };
}

class Acc {
  g0 = ZERO;
  m0 = ZERO;
  g3 = ZERO;
  m3 = ZERO;
  constructor(readonly label: string) {}
}

const wire = (g: Decimal, m: Decimal): TotalsWire => ({ full: fixed2(g), management: fixed2(m) });

function breakdown(map: Map<string, Acc>): Breakdown[] {
  return [...map.entries()]
    .sort(([a], [b]) => cmp(a, b))
    .map(([key, a]) => ({
      key,
      label: a.label,
      base: wire(a.g0, a.m0),
      scenario: wire(a.g3, a.m3),
      delta: wire(a.g3.minus(a.g0), a.m3.minus(a.m0)),
    }));
}

function bump(map: Map<string, Acc>, key: string, label: string, row: PreparedRow, s: Staged): void {
  let a = map.get(key);
  if (!a) {
    a = new Acc(label);
    map.set(key, a);
  }
  a.g0 = a.g0.plus(row.group);
  a.m0 = a.m0.plus(row.mgmt);
  a.g3 = a.g3.plus(s.g3);
  a.m3 = a.m3.plus(s.m3);
}

function impacts(p: Prepared, plan: Plan): EventImpact[] {
  const acc = new Map<string, { n: number; bf: Decimal; sf: Decimal; bm: Decimal; sm: Decimal }>();
  for (const ev of p.events) acc.set(ev.eventId, { n: 0, bf: ZERO, sf: ZERO, bm: ZERO, sm: ZERO });

  for (const e of p.effects) {
    if (e.date < plan.from || e.date > plan.to) continue;
    const scale = plan.adjust.get(e.eventId);
    const fxTouched = plan.fxActive && e.currency === plan.fxCurrency;
    const newOwn = plan.ownership.get(e.entityId);
    let sf = e.full;
    let sm = e.mgmt;
    if (scale !== undefined || fxTouched || newOwn !== undefined) {
      const local = scale !== undefined ? e.local.times(scale) : e.local;
      const fx = fxTouched ? e.fx.times(plan.factor) : e.fx;
      sf = money(local.times(fx));
      sm = money(local.times(fx).times(newOwn ?? e.own));
    }
    const a = acc.get(e.eventId)!;
    a.n += 1;
    a.bf = a.bf.plus(e.full);
    a.sf = a.sf.plus(sf);
    a.bm = a.bm.plus(e.mgmt);
    a.sm = a.sm.plus(sm);
  }

  return p.events.map((ev) => {
    const a = acc.get(ev.eventId)!;
    return {
      eventId: ev.eventId,
      scale: (plan.scales.get(ev.eventId) ?? ONE).toString(),
      effects: a.n,
      baseFull: fixed2(a.bf),
      scenarioFull: fixed2(a.sf),
      baseManagement: fixed2(a.bm),
      scenarioManagement: fixed2(a.sm),
    };
  });
}

export function simulate(p: Prepared, scenario: Scenario = {}): ScenarioResult {
  const plan = resolve(p, scenario);
  let g0 = ZERO, m0 = ZERO, g1 = ZERO, m1 = ZERO, g2 = ZERO, m2 = ZERO, g3 = ZERO, m3 = ZERO;
  const byEntity = new Map<string, Acc>();
  const bySector = new Map<string, Acc>();
  const byMonth = new Map<string, Acc>();
  let rows = 0;
  let rowsTouched = 0;

  for (const row of p.rows) {
    if (row.date < plan.from || row.date > plan.to) continue;
    const s = stage(row, plan);
    rows += 1;
    if (s.touched) rowsTouched += 1;
    g0 = g0.plus(row.group);
    m0 = m0.plus(row.mgmt);
    g1 = g1.plus(s.g1);
    m1 = m1.plus(s.m1);
    g2 = g2.plus(s.g2);
    m2 = m2.plus(s.m2);
    g3 = g3.plus(s.g3);
    m3 = m3.plus(s.m3);
    bump(byEntity, row.entityId, p.companies.get(row.entityId)!.name, row, s);
    bump(bySector, row.sector, row.sector, row, s);
    bump(byMonth, row.month, row.month, row, s);
  }

  const eventImpacts = impacts(p, plan);
  return {
    period: { from: plan.from, to: plan.to },
    applied: {
      fx: plan.fxGiven ? { currency: plan.fxCurrency, factor: plan.factor.toString() } : null,
      events: Object.fromEntries([...plan.scales].map(([k, v]) => [k, v.toString()])),
      ownership: Object.fromEntries([...plan.ownershipGiven].map(([k, v]) => [k, v.toString()])),
    },
    base: wire(g0, m0),
    scenario: wire(g3, m3),
    delta: wire(g3.minus(g0), m3.minus(m0)),
    steps: {
      events: wire(g1.minus(g0), m1.minus(m0)),
      fx: wire(g2.minus(g1), m2.minus(m1)),
      ownership: wire(g3.minus(g2), m3.minus(m2)),
    },
    byEntity: breakdown(byEntity),
    bySector: breakdown(bySector),
    byMonth: breakdown(byMonth),
    eventImpacts,
    stats: { rows, rowsTouched, effects: eventImpacts.reduce((n, e) => n + e.effects, 0) },
  };
}

// 期間で絞らず、全行のシナリオ後の値を返す（ドリルダウンや検証用）
export function simulateRows(p: Prepared, scenario: Scenario = {}): RowResult[] {
  const plan = resolve(p, { ...scenario, period: undefined });
  return p.rows.map((row) => {
    const s = stage(row, plan);
    return {
      metricId: row.metricId,
      date: row.date,
      entityId: row.entityId,
      baseGroup: fixed2(row.group),
      baseManagement: fixed2(row.mgmt),
      group: fixed2(s.g3),
      management: fixed2(s.m3),
    };
  });
}

// 取り込んだデータが、保存値と同じ式で再現できるか（実データ読み込み直後の自己検査）
export function reconcile(p: Prepared): Reconciliation {
  let groupMismatches = 0;
  let managementMismatches = 0;
  let effectFullMismatches = 0;
  let effectManagementMismatches = 0;
  const structuralIssues: string[] = [];
  const note = (message: string) => {
    if (structuralIssues.length < 10) structuralIssues.push(message);
  };

  for (const r of p.rows) {
    if (!money(r.local.times(r.fx)).eq(r.group)) groupMismatches += 1;
    if (!money(r.local.times(r.fx).times(r.own)).eq(r.mgmt)) managementMismatches += 1;
  }
  for (const e of p.effects) {
    if (!money(e.local.times(e.fx)).eq(e.full)) effectFullMismatches += 1;
    if (!money(e.local.times(e.fx).times(e.own)).eq(e.mgmt)) effectManagementMismatches += 1;
    if (e.entityId !== e.row.entityId || e.date !== e.row.date) note(`${e.effectId}: entity/date differs from ${e.row.metricId}`);
    if (!e.fx.eq(e.row.fx)) note(`${e.effectId}: fx differs from ${e.row.metricId}`);
    if (!e.own.eq(e.row.own)) note(`${e.effectId}: ownership differs from company master`);
  }

  const ok =
    groupMismatches + managementMismatches + effectFullMismatches + effectManagementMismatches === 0 &&
    structuralIssues.length === 0;
  return {
    rows: p.rows.length,
    effects: p.effects.length,
    groupMismatches,
    managementMismatches,
    effectFullMismatches,
    effectManagementMismatches,
    structuralIssues,
    ok,
  };
}
