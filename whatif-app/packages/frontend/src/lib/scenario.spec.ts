import { describe, expect, it } from 'vitest';

import {
  EVENT_RANGE,
  FX_RANGE,
  INITIAL_STATE,
  PRESETS,
  clampEvent,
  clampFx,
  eventPercentOf,
  factorString,
  isDefault,
  sameScenario,
  setEvent,
  setFx,
  toScenario,
} from './scenario';
import type { ModelEvent } from './types';

const event = (eventId: string, direction = 'negative'): ModelEvent => ({
  eventId,
  sector: 'foods',
  direction,
  severity: 5,
  startDate: '2026-02-09T00:00:00Z',
  endDate: '2026-02-23T00:00:00Z',
  narrative: '',
  effects: 84,
});

describe('factorString', () => {
  it('浮動小数点の誤差（0.9299999999999999 など）を、送る値に混ぜない', () => {
    expect(factorString(93)).toBe('0.93');
    expect(factorString(107)).toBe('1.07');
    expect(factorString(50)).toBe('0.50');
    expect(factorString(0)).toBe('0.00');
    expect(factorString(300)).toBe('3.00');
    // 素朴に 1 - 0.07 とすると誤差が出る例
    expect(String(1 - 0.07)).not.toBe('0.93');
  });
});

describe('toScenario', () => {
  it('何も変えなければ空のシナリオ（保存値のまま）になる', () => {
    expect(toScenario(INITIAL_STATE)).toEqual({});
    expect(isDefault(INITIAL_STATE)).toBe(true);
  });

  it('円高 10% は USD の倍率 0.90 になる（円安は 1.10）', () => {
    expect(toScenario(setFx(INITIAL_STATE, -10))).toEqual({ fx: { currency: 'USD', factor: '0.90' } });
    expect(toScenario(setFx(INITIAL_STATE, 10))).toEqual({ fx: { currency: 'USD', factor: '1.10' } });
  });

  it('食品損失を 50% 軽減すると、FOD_NEG の倍率が 0.50 になる', () => {
    expect(toScenario(setEvent(INITIAL_STATE, 'FOD_NEG', 50))).toEqual({ events: { FOD_NEG: '0.50' } });
  });

  it('倍率 100% に戻したイベントは送らない', () => {
    const changed = setEvent(INITIAL_STATE, 'FOD_NEG', 50);
    const back = setEvent(changed, 'FOD_NEG', 100);
    expect(toScenario(back)).toEqual({});
    expect(isDefault(back)).toBe(true);
  });

  it('複数の条件を同時に持てる', () => {
    const state = setEvent(setEvent(setFx(INITIAL_STATE, -5), 'FOD_NEG', 0), 'CROSS_NEG', 150);
    expect(toScenario(state)).toEqual({
      fx: { currency: 'USD', factor: '0.95' },
      events: { FOD_NEG: '0.00', CROSS_NEG: '1.50' },
    });
  });
});

describe('範囲の制限', () => {
  it('為替は −20〜+20、倍率は 0〜300 に収まり、刻みに揃う', () => {
    expect(clampFx(-99)).toBe(FX_RANGE.min);
    expect(clampFx(99)).toBe(FX_RANGE.max);
    expect(clampFx(3.4)).toBe(3);
    expect(clampEvent(-10)).toBe(EVENT_RANGE.min);
    expect(clampEvent(999)).toBe(EVENT_RANGE.max);
    expect(clampEvent(52)).toBe(50);
    expect(clampEvent(53)).toBe(55);
  });

  it('画面の範囲は、エンジンの許容範囲（為替 0.1〜10、倍率 0〜3）の内側にある', () => {
    expect(Number(factorString(100 + FX_RANGE.min))).toBeGreaterThanOrEqual(0.1);
    expect(Number(factorString(100 + FX_RANGE.max))).toBeLessThanOrEqual(10);
    expect(Number(factorString(EVENT_RANGE.min))).toBeGreaterThanOrEqual(0);
    expect(Number(factorString(EVENT_RANGE.max))).toBeLessThanOrEqual(3);
  });

  it('範囲外の値を入れても、状態は範囲内に直る', () => {
    expect(setFx(INITIAL_STATE, 500).fxPercent).toBe(20);
    expect(eventPercentOf(setEvent(INITIAL_STATE, 'A', 9999), 'A')).toBe(300);
  });
});

describe('状態の扱い', () => {
  it('元の状態を書き換えない', () => {
    const a = setEvent(INITIAL_STATE, 'A', 50);
    setEvent(a, 'B', 150);
    expect(a.eventPercent).toEqual({ A: 50 });
    expect(INITIAL_STATE.eventPercent).toEqual({});
  });

  it('未設定のイベントの倍率は 100%', () => {
    expect(eventPercentOf(INITIAL_STATE, 'ANY')).toBe(100);
  });

  it('同じシナリオかどうかを判定できる（表記ゆれに強い）', () => {
    expect(sameScenario(setFx(INITIAL_STATE, -10), setFx(INITIAL_STATE, -10))).toBe(true);
    expect(sameScenario(setFx(INITIAL_STATE, -10), setFx(INITIAL_STATE, -9))).toBe(false);
    expect(sameScenario(INITIAL_STATE, setEvent(INITIAL_STATE, 'A', 100))).toBe(true);
  });
});

describe('プリセット', () => {
  const events = [event('CROSS_NEG'), event('FOD_NEG'), event('FOD_POS', 'positive')];
  const byId = (id: string) => PRESETS.find((p) => p.id === id)!;

  it('食品損失を 50% 軽減は、FOD_NEG だけを 0.50 にする', () => {
    expect(toScenario(byId('food-loss-50').apply(INITIAL_STATE, events))).toEqual({ events: { FOD_NEG: '0.50' } });
  });

  it('FOD_NEG が無いモデルでは、最初の悪材料イベントに適用する（無ければ何もしない）', () => {
    expect(toScenario(byId('food-loss-50').apply(INITIAL_STATE, [event('FOD_POS', 'positive'), event('MTL_NEG')]))).toEqual({ events: { MTL_NEG: '0.50' } });
    expect(toScenario(byId('food-loss-50').apply(INITIAL_STATE, [event('FOD_POS', 'positive')]))).toEqual({});
  });

  it('円高・円安は為替だけを動かし、他の条件は保つ', () => {
    const withEvent = setEvent(INITIAL_STATE, 'CROSS_NEG', 150);
    expect(byId('yen-up-10').apply(withEvent, events)).toEqual({ fxPercent: -10, eventPercent: { CROSS_NEG: 150 } });
    expect(byId('yen-down-10').apply(INITIAL_STATE, events).fxPercent).toBe(10);
  });

  it('リセットはすべて実績のままに戻す', () => {
    const dirty = setEvent(setFx(INITIAL_STATE, 8), 'A', 20);
    expect(isDefault(byId('reset').apply(dirty, events))).toBe(true);
  });
});
