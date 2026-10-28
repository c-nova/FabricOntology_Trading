import type { ModelEvent, ScenarioInput } from './types';

// 画面の状態。スライダーは整数のステップで持つ（浮動小数点の誤差を、送る値に混ぜない）。
export interface ScenarioState {
  /** 円高円安（USD 建て子会社の円換算）。-20〜+20。マイナスが円高。 */
  fxPercent: number;
  /** イベントごとの倍率（%）。0〜300。100 が「そのまま」。キーが無いイベントは 100。 */
  eventPercent: Record<string, number>;
}

export const FX_RANGE = { min: -20, max: 20, step: 1 } as const;
export const EVENT_RANGE = { min: 0, max: 300, step: 5, neutral: 100 } as const;
export const FX_CURRENCY = 'USD';

export const INITIAL_STATE: ScenarioState = { fxPercent: 0, eventPercent: {} };

const clamp = (n: number, min: number, max: number): number => Math.min(max, Math.max(min, n));

const snap = (n: number, step: number): number => Math.round(n / step) * step;

export function clampFx(percent: number): number {
  return clamp(snap(percent, FX_RANGE.step), FX_RANGE.min, FX_RANGE.max);
}

export function clampEvent(percent: number): number {
  return clamp(snap(percent, EVENT_RANGE.step), EVENT_RANGE.min, EVENT_RANGE.max);
}

/** 整数のパーセントを、小数 2 桁の倍率の文字列にする。例: 93 → "0.93"、50 → "0.50" */
export function factorString(percent: number): string {
  return (percent / 100).toFixed(2);
}

export function eventPercentOf(state: ScenarioState, eventId: string): number {
  return state.eventPercent[eventId] ?? EVENT_RANGE.neutral;
}

export function setFx(state: ScenarioState, percent: number): ScenarioState {
  return { ...state, fxPercent: clampFx(percent) };
}

export function setEvent(state: ScenarioState, eventId: string, percent: number): ScenarioState {
  const next = { ...state.eventPercent };
  const value = clampEvent(percent);
  if (value === EVENT_RANGE.neutral) delete next[eventId];
  else next[eventId] = value;
  return { ...state, eventPercent: next };
}

export function isDefault(state: ScenarioState): boolean {
  return state.fxPercent === 0 && Object.keys(state.eventPercent).length === 0;
}

/**
 * Functions に渡すシナリオ。変更のない項目は送らない。
 * 為替の倍率は「円高 10%」なら 0.90（USD 1 ドルあたりの円が 10% 下がる）。
 */
export function toScenario(state: ScenarioState): ScenarioInput {
  const scenario: ScenarioInput = {};
  if (state.fxPercent !== 0) {
    scenario.fx = { currency: FX_CURRENCY, factor: factorString(100 + state.fxPercent) };
  }
  const events = Object.entries(state.eventPercent).filter(([, p]) => p !== EVENT_RANGE.neutral);
  if (events.length > 0) {
    scenario.events = Object.fromEntries(events.map(([id, p]) => [id, factorString(p)]));
  }
  return scenario;
}

/** 同じシナリオかどうか（デバウンス後の無駄な再計算を避ける）。 */
export function sameScenario(a: ScenarioState, b: ScenarioState): boolean {
  return JSON.stringify(toScenario(a)) === JSON.stringify(toScenario(b));
}

export interface Preset {
  id: string;
  label: string;
  hint: string;
  apply: (state: ScenarioState, events: readonly ModelEvent[]) => ScenarioState;
}

const worstNegativeEvent = (events: readonly ModelEvent[]): ModelEvent | undefined =>
  events.find((e) => e.eventId === 'FOD_NEG') ?? events.find((e) => e.direction === 'negative');

export const PRESETS: readonly Preset[] = [
  {
    id: 'reset',
    label: 'リセット',
    hint: '実績のままに戻す',
    apply: () => INITIAL_STATE,
  },
  {
    id: 'food-loss-50',
    label: '食品損失を 50% 軽減',
    hint: '食品の悪材料イベント（FOD_NEG）の影響を半分にする',
    apply: (state, events) => {
      const target = events.find((e) => e.eventId === 'FOD_NEG') ?? worstNegativeEvent(events);
      return target ? setEvent(state, target.eventId, 50) : state;
    },
  },
  {
    id: 'yen-up-10',
    label: '円高 10%',
    hint: 'USD 建て子会社の円換算レートが 10% 下がる',
    apply: (state) => setFx(state, -10),
  },
  {
    id: 'yen-down-10',
    label: '円安 10%',
    hint: 'USD 建て子会社の円換算レートが 10% 上がる',
    apply: (state) => setFx(state, 10),
  },
];
