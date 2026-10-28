import { Decimal, fixed2, money } from './decimal.js';
import { DataError, LIMITS, ScenarioError, type Prepared } from './engine.js';

export interface FutureBaseline {
  asOf: string;
  period: { from: string; to: string };
  amountFull: string;
}

export interface FutureScenario {
  eventId: string;
  eventDate: string;
  scale: number;
}

export interface FuturePath {
  effectId: string;
  entityId: string;
  metricId: string;
}

export interface FutureResult {
  period: { from: string; to: string };
  asOf: string;
  baselineFull: string;
  scenarioFull: string;
  deltaFull: string;
  eventId: string;
  eventDate: string;
  scale: string;
  includedEffects: number;
  excludedEffects: number;
  historicalEffects: number;
  byEntity: { entityId: string; name: string; deltaFull: string }[];
}

const DAY_MS = 86_400_000;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL_STRING = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
// At 40 digits of Decimal precision, amounts below this bound retain every cent in addition.
const AMOUNT_LIMIT = new Decimal('1e38');
const identifier = (value: unknown): value is string => typeof value === 'string' && value.length > 0;

function day(value: string): number | undefined {
  if (typeof value !== 'string' || !DATE.test(value)) return undefined;
  const ms = Date.parse(`${value}T00:00:00.000Z`);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 10) !== value) return undefined;
  return ms / DAY_MS;
}

function eventStartDay(value: string): number | undefined {
  const date = day(value);
  if (date !== undefined) return date;
  if (typeof value !== 'string') return undefined;
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!m || day(m[1]!) === undefined || Number(m[2]) > 23 || Number(m[3]) > 59 || Number(m[4]) > 59) {
    return undefined;
  }
  if (m[5] !== 'Z' && (Number(m[5]!.slice(1, 3)) > 23 || Number(m[5]!.slice(4, 6)) > 59)) return undefined;
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return undefined;
  return day(new Date(ms).toISOString().slice(0, 10));
}

function checkedAmount(value: Decimal, what: string): Decimal {
  if (!value.isFinite() || value.abs().gte(AMOUNT_LIMIT)) throw new DataError(`${what} is not a safe finite amount`);
  return value;
}

function addAmounts(a: Decimal, b: Decimal, what: string): Decimal {
  return checkedAmount(a.plus(b), what);
}

// This is an additive overlay on the supplied forecast, not an AutoML re-prediction.
export function simulateFuture(
  p: Prepared,
  baseline: FutureBaseline,
  scenario: FutureScenario,
  paths: readonly FuturePath[],
): FutureResult {
  const asOf = day(baseline.asOf);
  const from = day(baseline.period.from);
  const to = day(baseline.period.to);
  const eventDate = day(scenario.eventDate);
  if (asOf === undefined || from === undefined || to === undefined || eventDate === undefined ||
      from <= asOf || to < from || eventDate < from || eventDate > to) {
    throw new ScenarioError('BAD_PERIOD', 'dates must be valid UTC calendar dates, with the event in a period after asOf');
  }
  if (typeof scenario.scale !== 'number' || !Number.isFinite(scenario.scale)) {
    throw new ScenarioError('BAD_NUMBER', 'scale is not a finite number');
  }
  const scale = new Decimal(scenario.scale);
  if (scale.lt(LIMITS.eventScale.min) || scale.gt(LIMITS.eventScale.max)) {
    throw new ScenarioError('OUT_OF_RANGE', 'scale must be between 0 and 3');
  }
  if (typeof baseline.amountFull !== 'string' || !DECIMAL_STRING.test(baseline.amountFull)) {
    throw new DataError('baseline amount is not a decimal string');
  }
  const baselineFull = checkedAmount(money(checkedAmount(new Decimal(baseline.amountFull), 'baseline amount')), 'baseline amount');

  const events = p.events.filter((e) => e.eventId === scenario.eventId);
  if (events.length === 0) throw new ScenarioError('UNKNOWN_EVENT', `unknown event ${scenario.eventId}`);
  if (events.length !== 1) throw new DataError(`duplicate event ${scenario.eventId}`);
  const start = eventStartDay(events[0]!.startDate);
  if (start === undefined || start > asOf) throw new DataError(`event ${scenario.eventId} has an invalid or future start date`);

  const effects = p.effects.filter((e) => e.eventId === scenario.eventId);
  if (effects.length === 0 || !Array.isArray(paths) || paths.length === 0) {
    throw new DataError(`event ${scenario.eventId} has no effects or Graph paths`);
  }
  const AccDecimal = Decimal.clone({ precision: 41 + Math.ceil(Math.log10(effects.length)) });
  const byEffect = new Map<string, (typeof effects)[number]>();
  const byEntity = new Map<string, { name: string; delta: Decimal }>();
  for (const effect of effects) {
    const effectDay = day(effect.date);
    if (effectDay === undefined || effectDay < start || effectDay > asOf) {
      throw new DataError(`effect ${effect.effectId} has an invalid, pre-event, or future date`);
    }
    const company = p.companies.get(effect.entityId);
    if (!identifier(effect.effectId) || !identifier(effect.entityId) || !company || !effect.row || !identifier(effect.row.metricId) ||
        effect.row.entityId !== effect.entityId || effect.row.date !== effect.date) {
      throw new DataError(`effect ${effect.effectId} has an inconsistent company or metric`);
    }
    if (byEffect.has(effect.effectId)) throw new DataError(`duplicate effect ${effect.effectId}`);
    if (!Decimal.isDecimal(effect.full)) throw new DataError(`effect ${effect.effectId} has an invalid amount`);
    checkedAmount(effect.full, `effect ${effect.effectId}`);
    byEffect.set(effect.effectId, effect);
    byEntity.set(effect.entityId, { name: company.name, delta: new AccDecimal(0) });
  }
  const seen = new Set<string>();
  for (const path of paths) {
    if (!path || !identifier(path.effectId) || !identifier(path.entityId) ||
        !identifier(path.metricId) || seen.has(path.effectId)) {
      throw new DataError('duplicate or invalid Graph path');
    }
    const effect = byEffect.get(path.effectId);
    if (!effect || path.entityId !== effect.entityId || path.metricId !== effect.row.metricId) {
      throw new DataError(`Graph path does not match source effect ${path.effectId}`);
    }
    seen.add(path.effectId);
  }
  if (seen.size !== effects.length) throw new DataError('Graph paths are missing source effects');

  let delta = new AccDecimal(0);
  let includedEffects = 0;
  for (const effect of effects) {
    const projectedDay = eventDate + (day(effect.date)! - start);
    if (projectedDay > to) continue;
    includedEffects += 1;
    // Multiplication must be exact before the per-row money rounding.
    const precision = Math.max(40, effect.full.sd() + scale.sd());
    const Exact = Decimal.clone({ precision });
    const rowDelta = checkedAmount(money(new Exact(effect.full).times(scale)), `effect ${effect.effectId} scaled amount`);
    delta = delta.plus(rowDelta);
    const entity = byEntity.get(effect.entityId)!;
    entity.delta = entity.delta.plus(rowDelta);
  }
  checkedAmount(delta, 'total delta');
  for (const [entityId, entity] of byEntity) checkedAmount(entity.delta, `entity ${entityId} delta`);
  const scenarioFull = addAmounts(baselineFull, delta, 'scenario amount');
  return {
    period: { from: baseline.period.from, to: baseline.period.to },
    asOf: baseline.asOf,
    baselineFull: fixed2(baselineFull),
    scenarioFull: fixed2(scenarioFull),
    deltaFull: fixed2(delta),
    eventId: scenario.eventId,
    eventDate: scenario.eventDate,
    scale: scale.toString(),
    includedEffects,
    excludedEffects: effects.length - includedEffects,
    historicalEffects: effects.length,
    byEntity: [...byEntity.entries()]
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([entityId, entity]) => ({ entityId, name: entity.name, deltaFull: fixed2(entity.delta) })),
  };
}
