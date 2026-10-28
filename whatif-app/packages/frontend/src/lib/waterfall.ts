import type { Metric, SimulationResult } from './types';

// 差の内訳（イベント → 為替 → 持分 → 合計）の滝グラフ。
// 総額（約 447 億円）から始めると、差（数億〜数十億円）が小さすぎて読めず、軸を切り詰めると棒が嘘をつく。
// そこで 0 から始め、差だけを積み上げる。

export interface WaterfallBar {
  key: 'events' | 'fx' | 'ownership' | 'total';
  label: string;
  /** この段階の差（円・10 進文字列）。表示用。 */
  amount: string;
  /** 棒の始点と終点（円・表示の座標用。精度は要らない）。 */
  from: number;
  to: number;
  isTotal: boolean;
}

export interface Waterfall {
  bars: WaterfallBar[];
  /** 軸の下限・上限（円）。0 を必ず含む。 */
  min: number;
  max: number;
}

const LABELS: Record<WaterfallBar['key'], string> = {
  events: 'イベント',
  fx: '為替',
  ownership: '持分',
  total: '合計の差',
};

export function buildWaterfall(result: SimulationResult, metric: Metric): Waterfall {
  const steps: { key: 'events' | 'fx' | 'ownership'; amount: string }[] = [
    { key: 'events', amount: result.steps.events[metric] },
    { key: 'fx', amount: result.steps.fx[metric] },
    { key: 'ownership', amount: result.steps.ownership[metric] },
  ];

  const bars: WaterfallBar[] = [];
  let running = 0;
  for (const step of steps) {
    const n = Number(step.amount);
    // 動いていない段階は出さない（持分は、この画面では常に 0）
    if (n === 0 && step.key === 'ownership') continue;
    bars.push({ key: step.key, label: LABELS[step.key], amount: step.amount, from: running, to: running + n, isTotal: false });
    running += n;
  }
  bars.push({ key: 'total', label: LABELS.total, amount: result.delta[metric], from: 0, to: Number(result.delta[metric]), isTotal: true });

  const values = bars.flatMap((b) => [b.from, b.to, 0]);
  return { bars, min: Math.min(...values), max: Math.max(...values) };
}

/** 値を 0〜1 の位置にする（軸の範囲が 0 のときは中央）。 */
export function scalePosition(value: number, min: number, max: number): number {
  if (max === min) return 0.5;
  return (value - min) / (max - min);
}
