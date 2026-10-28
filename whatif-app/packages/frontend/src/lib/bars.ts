// 0 を中心にした横棒の位置。負は左、正は右。値の絶対値が最大のものを、半幅いっぱいにする。

export interface BarGeometry {
  /** 0 の位置（左端からの割合 0〜100）。負の値があれば右へ寄る。 */
  zero: number;
  /** 棒の左端（左端からの割合）。 */
  left: number;
  /** 棒の幅（全幅に対する割合）。 */
  width: number;
}

const MIN_VISIBLE_PERCENT = 0.8;

/**
 * 値の範囲 [min, max]（0 を含む）の上で、from〜to の棒を、全幅に対する割合で返す。
 * 0 ではない値は、細すぎて消えないように最小の幅を持たせる。
 */
export function geometry(from: number, to: number, min: number, max: number): BarGeometry {
  const span = max - min;
  if (span === 0) return { zero: 50, left: 50, width: 0 };
  const pos = (v: number) => ((v - min) / span) * 100;
  const a = pos(Math.min(from, to));
  const b = pos(Math.max(from, to));
  const width = b - a;
  const visible = from !== to && width < MIN_VISIBLE_PERCENT ? MIN_VISIBLE_PERCENT : width;
  return { zero: pos(0), left: a, width: visible };
}

/** 一覧の値（円・文字列）から、共通の軸の範囲を求める。0 を必ず含む。 */
export function rangeOf(values: readonly string[]): { min: number; max: number } {
  let min = 0;
  let max = 0;
  for (const v of values) {
    const n = Number(v);
    if (!Number.isFinite(n)) continue;
    if (n < min) min = n;
    if (n > max) max = n;
  }
  return { min, max };
}
