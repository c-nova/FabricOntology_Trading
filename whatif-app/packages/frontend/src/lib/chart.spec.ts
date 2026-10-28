import { describe, expect, it } from 'vitest';

import { BAR_BAND, LINE_BAND, barDomain, barWidth, isCompact, lineDomain, niceStep, plotOf, slotCenter, ticksOf, toOku, yOf } from './chart';

describe('niceStep', () => {
  it('1・2・5 の刻みで、区間が上限以内になる最小のものを選ぶ', () => {
    expect(niceStep(18.4, 5)).toBe(5);
    expect(niceStep(12, 5)).toBe(5);
    expect(niceStep(131.7, 3)).toBe(50);
    expect(niceStep(9.9, 5)).toBe(2);
    expect(niceStep(0.37, 5)).toBe(0.1);
    expect(niceStep(2500, 5)).toBe(500);
  });

  it('不正な幅でも、有限の刻みを返す', () => {
    for (const bad of [0, -3, Number.NaN, Number.POSITIVE_INFINITY]) expect(niceStep(bad, 5)).toBe(1);
  });
});

describe('lineDomain（折れ線の軸）', () => {
  it('実績と予測の値が収まり、差が見える幅になる（0から始めない）', () => {
    const d = lineDomain([115.93, 103.65, 112.38, 115.61, 114.9, 113.75]);
    expect(d).toEqual({ lo: 100, hi: 120, step: 5 });
    expect(ticksOf(d)).toEqual([100, 105, 110, 115, 120]);
  });

  it('大きく下がる仮定でも、値は軸の中に収まる', () => {
    const values = [115.93, 103.65, 112.38, 115.61, 114.9, 94.5];
    const d = lineDomain(values);
    expect(d.lo).toBeLessThanOrEqual(94.5);
    expect(d.hi).toBeGreaterThanOrEqual(115.93);
    expect(d.lo).toBeGreaterThanOrEqual(0);
  });

  it('値がすべて同じでも、見える幅を持ち、有限の値だけを使う', () => {
    const d = lineDomain([50, 50, 50]);
    expect(d.hi).toBeGreaterThan(d.lo);
    expect(d.lo).toBeLessThanOrEqual(50);
    expect(d.hi).toBeGreaterThanOrEqual(50);
    expect(lineDomain([Number.NaN])).toEqual({ lo: 0, hi: 1, step: 1 });
    expect(lineDomain([])).toEqual({ lo: 0, hi: 1, step: 1 });
    expect(lineDomain([10, Number.NaN, 12]).lo).toBeLessThanOrEqual(10);
  });

  it('値が正のときは、軸が0を下回らない', () => {
    expect(lineDomain([0.4, 0.5]).lo).toBeGreaterThanOrEqual(0);
  });
});

describe('barDomain（積み上げ棒の軸）', () => {
  it('0から始まり、いちばん高い棒が軸の約88%以内に収まる', () => {
    const d = barDomain(115.93);
    expect(d).toEqual({ lo: 0, hi: 150, step: 50 });
    expect(115.93 / d.hi).toBeLessThan(0.88);
    expect(ticksOf(d)).toEqual([0, 50, 100, 150]);
  });

  it('値が0や不正でも、描画できる軸を返す', () => {
    expect(barDomain(0)).toEqual({ lo: 0, hi: 1, step: 1 });
    expect(barDomain(Number.NaN)).toEqual({ lo: 0, hi: 1, step: 1 });
  });
});

describe('座標', () => {
  const plot = plotOf(800);

  it('幅から、プロットの領域と高さが決まる。狭すぎる幅は最小幅に切り上げる', () => {
    expect(plot).toMatchObject({ width: 800, height: 400, x0: 44, x1: 752, y0: 40, y1: 344, w: 708, h: 304 });
    expect(plotOf(100).width).toBe(300);
  });

  it('狭い幅では、左右の余白を詰めて区画を広く取り、ラベルを短縮する対象にする', () => {
    expect(isCompact(519)).toBe(true);
    expect(isCompact(520)).toBe(false);
    const narrow = plotOf(390);
    expect(narrow.x0).toBe(34);
    expect(narrow.width - narrow.x1).toBe(40);
    expect(narrow.w / 5).toBeGreaterThan(plotOf(300).w / 5 - 1e-9);
    // 区画は、短縮したラベル（約40px）が収まる広さがある
    expect(plotOf(301).w / 5).toBeGreaterThanOrEqual(44);
    expect(plotOf(390).height).toBe(300);
  });

  it('折れ線の軸は上の帯、棒の軸は下の帯に置き、下端と上端が帯の端に一致する', () => {
    const line = lineDomain([103.65, 115.93]);
    expect(yOf(line.hi, line, LINE_BAND, plot)).toBeCloseTo(plot.y1 - plot.h, 6);
    expect(yOf(line.lo, line, LINE_BAND, plot)).toBeCloseTo(plot.y1 - LINE_BAND.from * plot.h, 6);
    const bar = barDomain(115.93);
    expect(yOf(0, bar, BAR_BAND, plot)).toBeCloseTo(plot.y1, 6);
    expect(yOf(bar.hi, bar, BAR_BAND, plot)).toBeCloseTo(plot.y1 - BAR_BAND.to * plot.h, 6);
    // 帯は一部重なってよい（線は棒の背景の上を通る）が、折れ線の帯の下端は、棒の帯の上端より下にある
    expect(LINE_BAND.from).toBeLessThan(BAR_BAND.to);
  });

  it('値が大きいほど、上（yが小さい）に来る', () => {
    const line = lineDomain([100, 120]);
    expect(yOf(115, line, LINE_BAND, plot)).toBeLessThan(yOf(105, line, LINE_BAND, plot));
  });

  it('区画の中心は等間隔で、棒の幅は区画の半分以内に収まる', () => {
    const xs = [0, 1, 2, 3, 4].map((i) => slotCenter(i, 5, plot));
    expect(xs[0]).toBeCloseTo(44 + 708 / 10, 6);
    expect(xs[4]).toBeCloseTo(752 - 708 / 10, 6);
    expect(xs[1]! - xs[0]!).toBeCloseTo(xs[4]! - xs[3]!, 6);
    expect(barWidth(5, plot)).toBeLessThanOrEqual(72);
    expect(barWidth(5, plot)).toBeLessThanOrEqual(plot.w / 5 / 2 + 1e-9);
    expect(barWidth(5, plotOf(300))).toBeGreaterThanOrEqual(10);
  });
});

describe('toOku', () => {
  it('円の文字列を、億円の数値にする（描画専用）', () => {
    expect(toOku('11489536832.22')).toBeCloseTo(114.8953683222, 9);
    expect(toOku('-114461186.25')).toBeCloseTo(-1.1446118625, 9);
  });
});
