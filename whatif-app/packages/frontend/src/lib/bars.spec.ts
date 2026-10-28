import { describe, expect, it } from 'vitest';

import { geometry, rangeOf } from './bars';

describe('rangeOf', () => {
  it('0 を必ず含む', () => {
    expect(rangeOf(['-10', '-5'])).toEqual({ min: -10, max: 0 });
    expect(rangeOf(['5', '20'])).toEqual({ min: 0, max: 20 });
    expect(rangeOf([])).toEqual({ min: 0, max: 0 });
  });
  it('数値でないものは無視する', () => {
    expect(rangeOf(['abc', '-4', ''])).toEqual({ min: -4, max: 0 });
  });
});

describe('geometry', () => {
  it('負の棒は、0 から左へ伸びる', () => {
    const g = geometry(0, -50, -100, 100);
    expect(g.zero).toBe(50);
    expect(g.left).toBe(25);
    expect(g.width).toBe(25);
  });
  it('正の棒は、0 から右へ伸びる', () => {
    const g = geometry(0, 100, -100, 100);
    expect(g.left).toBe(50);
    expect(g.width).toBe(50);
  });
  it('積み上げの途中の棒は、始点から終点まで', () => {
    const g = geometry(20, -60, -100, 100);
    expect(g.left).toBe(20);
    expect(g.width).toBe(40);
  });
  it('0 でない値は、細すぎても消えない', () => {
    const g = geometry(0, 0.0001, -1000, 1000);
    expect(g.width).toBeGreaterThan(0.5);
  });
  it('0 の棒は、幅を持たない', () => {
    expect(geometry(0, 0, -100, 100).width).toBe(0);
  });
  it('範囲が 0 のときは、壊れずに中央へ置く', () => {
    expect(geometry(0, 0, 0, 0)).toEqual({ zero: 50, left: 50, width: 0 });
  });
  it('負だけの範囲では、0 は右端になる', () => {
    expect(geometry(0, -10, -10, 0).zero).toBe(100);
  });
});
