// 四半期グラフの目盛り・座標。描画（SVG）から切り離した、純粋な計算。
// 値はすべて億円（表示・描画専用。精度が要る計算には使わない）。

/** 円（10進の文字列）→ 億円。描画専用。 */
export const toOku = (yen: string): number => Number(yen) / 1e8;

const ROUND = 1e6;
const clean = (n: number): number => Math.round(n * ROUND) / ROUND;

/** 「1・2・5」× 10のべき乗のうち、区間の数が maxIntervals 以下になる、最小の刻み。 */
export function niceStep(range: number, maxIntervals: number): number {
  if (!(range > 0) || !Number.isFinite(range)) return 1;
  for (let exp = -3; exp <= 12; exp += 1) {
    for (const base of [1, 2, 5]) {
      const step = base * 10 ** exp;
      if (range / step <= maxIntervals) return clean(step);
    }
  }
  return 10 ** 12;
}

export interface Domain {
  lo: number;
  hi: number;
  step: number;
}

/**
 * 折れ線の軸の範囲。差が見えるように、値の範囲に余白を足した幅に合わせる（0から始めない）。
 * 値がすべて同じでも、見える幅を持たせる。
 */
export function lineDomain(values: readonly number[]): Domain {
  const v = values.filter(Number.isFinite);
  if (v.length === 0) return { lo: 0, hi: 1, step: 1 };
  const min = Math.min(...v);
  const max = Math.max(...v);
  const span = Math.max(max - min, Math.abs(max) * 0.02, 1e-6);
  const pad = span * 0.25;
  const step = niceStep(span + 2 * pad, 5);
  let lo = clean(Math.floor((min - pad) / step) * step);
  const hi = clean(Math.ceil((max + pad) / step) * step);
  if (min >= 0 && lo < 0) lo = 0;
  return { lo, hi: hi > lo ? hi : clean(lo + step), step };
}

/** 積み上げ棒の軸。0 から始め、いちばん高い棒が、軸の高さの約88%になるようにする。 */
export function barDomain(maxTotal: number): Domain {
  if (!(maxTotal > 0) || !Number.isFinite(maxTotal)) return { lo: 0, hi: 1, step: 1 };
  const want = maxTotal / 0.88;
  const step = niceStep(want, 3);
  return { lo: 0, hi: clean(Math.ceil(want / step) * step), step };
}

export function ticksOf({ lo, hi, step }: Domain): number[] {
  const n = Math.round((hi - lo) / step);
  return Array.from({ length: n + 1 }, (_, i) => clean(lo + i * step));
}

export interface Plot {
  width: number;
  height: number;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  w: number;
  h: number;
}

export const MARGIN = { left: 44, right: 48, top: 40, bottom: 56 } as const;
// 狭い幅では、左右の余白を詰めて、区画（四半期ごとの幅）を広く取る
const MARGIN_COMPACT = { left: 34, right: 40, top: 40, bottom: 52 } as const;
export const MIN_WIDTH = 300;
/** この幅より狭いときは、四半期ラベルを短くする（隣のラベルと重ならないように） */
export const COMPACT_BELOW = 520;

export const isCompact = (width: number): boolean => width < COMPACT_BELOW;

export function plotOf(width: number): Plot {
  const w0 = Math.max(MIN_WIDTH, Math.round(width));
  const m = isCompact(w0) ? MARGIN_COMPACT : MARGIN;
  const height = Math.round(Math.min(400, Math.max(isCompact(w0) ? 300 : 320, w0 * 0.5)));
  return {
    width: w0,
    height,
    x0: m.left,
    x1: w0 - m.right,
    y0: m.top,
    y1: height - m.bottom,
    w: w0 - m.left - m.right,
    h: height - m.top - m.bottom,
  };
}

/** 軸が使う、プロットの高さの範囲（下を0、上を1とした割合）。折れ線は上、棒は下に置き、少し重ねる。 */
export interface Band {
  from: number;
  to: number;
}
export const LINE_BAND: Band = { from: 0.36, to: 1 };
export const BAR_BAND: Band = { from: 0, to: 0.58 };

/** 値の、縦の位置（SVGのy）。範囲の外の値は、そのまま外にはみ出す。 */
export function yOf(value: number, domain: Domain, band: Band, plot: Plot): number {
  const t = domain.hi === domain.lo ? 0 : (value - domain.lo) / (domain.hi - domain.lo);
  return plot.y1 - (band.from + t * (band.to - band.from)) * plot.h;
}

/** n 個の区画の、i 番目の中心のx。 */
export function slotCenter(i: number, n: number, plot: Plot): number {
  return plot.x0 + ((i + 0.5) * plot.w) / Math.max(1, n);
}

/** 棒の幅。区画の半分ほど。広い画面でも太くなりすぎないようにする。 */
export function barWidth(n: number, plot: Plot): number {
  return Math.max(10, Math.min(72, (plot.w / Math.max(1, n)) * 0.5));
}
