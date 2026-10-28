import { geometry } from '@/lib/bars';
import { formatSignedMillion, formatSignedYen } from '@/lib/format';
import type { Metric, SimulationResult } from '@/lib/types';
import { buildWaterfall } from '@/lib/waterfall';
import { cn } from '@/lib/utils';

import { METRICS } from './labels';
import { SectionLabel } from './primitives';

const STEP_NOTE: Record<string, string> = {
  events: 'イベントの影響を変えた分',
  fx: '円換算レートを変えた分',
  ownership: '持分比率を変えた分',
  total: '上の段階の合計',
};

// 差の内訳。0 から始めて、段階ごとの差だけを積み上げる（総額から始めると、差が小さくて読めない）。
export function Waterfall({ result, metric }: { result: SimulationResult; metric: Metric }) {
  const w = buildWaterfall(result, metric);
  const meta = METRICS.find((m) => m.id === metric)!;

  return (
    <section aria-labelledby="waterfall-label" className="space-y-300">
      <div className="flex flex-wrap items-baseline justify-between gap-200">
        <SectionLabel id="waterfall-label">差の内訳</SectionLabel>
        <p className="text-200 text-muted-foreground">{meta.label}・単位は百万円</p>
      </div>

      <ol className="space-y-200">
        {w.bars.map((b) => {
          const g = geometry(b.from, b.to, w.min, w.max);
          const n = Number(b.amount);
          const negative = n < 0;
          return (
            <li key={b.key} className={cn('grid items-center gap-x-300 gap-y-100 grid-cols-[1fr_auto] md:grid-cols-[var(--spacing-label)_1fr_var(--spacing-amount)]', b.isTotal && 'border-t border-foreground pt-200')}>
              <div className="min-w-0">
                <p className={cn('text-300 text-foreground', b.isTotal ? 'font-bold' : 'font-medium')}>{b.label}</p>
                <p className="text-200 text-muted-foreground">{STEP_NOTE[b.key]}</p>
              </div>

              {/* 棒。0 の位置に縦線を引く。狭い幅では、ラベルと金額の下に全幅で置く */}
              <div aria-hidden className="relative order-last col-span-2 h-control md:order-none md:col-span-1">
                <div className="absolute inset-y-0 w-px bg-foreground" style={{ left: `${g.zero}%` }} />
                {n !== 0 && (
                  <div
                    className={cn('absolute inset-y-200 rounded-sm', negative ? 'bg-destructive' : 'bg-brand', !b.isTotal && 'opacity-80')}
                    style={{ left: `${g.left}%`, width: `${g.width}%` }}
                  />
                )}
              </div>

              <p className={cn('font-numeric text-300 tabular-nums text-right', negative ? 'text-destructive' : n > 0 ? 'text-brand-foreground' : 'text-muted-foreground', b.isTotal && 'font-bold')} title={`${formatSignedYen(b.amount)} 円`}>
                {formatSignedMillion(b.amount)}
              </p>
            </li>
          );
        })}
      </ol>
      <p className="text-200 text-muted-foreground">
        段階は「イベント → 為替」の順に分けています。順序を変えると各段階の金額は変わりますが、合計は変わりません。
      </p>
    </section>
  );
}
