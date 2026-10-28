import { ArrowDownRight, ArrowUpRight } from 'lucide-react';

import { formatDate, formatOku, formatPercent, formatSignedOku, formatSignedYen, formatYen, isNumeric } from '@/lib/format';
import type { Metric, SimulationResult } from '@/lib/types';
import { cn } from '@/lib/utils';

import { METRICS } from './labels';
import { Skeleton } from './primitives';

type Direction = 'down' | 'up' | 'flat';

const directionOf = (delta: string): Direction => {
  if (!isNumeric(delta)) return 'flat';
  const n = Number(delta);
  return n < 0 ? 'down' : n > 0 ? 'up' : 'flat';
};

const WORD: Record<Direction, string> = { down: '減少', up: '増加', flat: '変化なし' };

const TONE: Record<Direction, string> = {
  down: 'text-destructive',
  up: 'text-brand-foreground',
  flat: 'text-muted-foreground',
};

// 変化なしのときは、アイコンを出さない（横線が「一」の文字に見えてしまう）。
function Arrow({ direction, className }: { direction: Direction; className?: string }) {
  if (direction === 'flat') return null;
  const Icon = direction === 'down' ? ArrowDownRight : ArrowUpRight;
  return <Icon aria-hidden className={className} />;
}

function Figure({ result, metric, selected, pending }: { result: SimulationResult; metric: Metric; selected: boolean; pending: boolean }) {
  const meta = METRICS.find((m) => m.id === metric)!;
  const base = result.base[metric];
  const scenario = result.scenario[metric];
  const delta = result.delta[metric];
  const direction = directionOf(delta);

  return (
    <section
      aria-label={meta.label}
      className={cn(
        '@container flex min-w-0 flex-col gap-300 rounded-lg border bg-card p-500 transition-opacity',
        selected ? 'border-foreground' : 'border-border',
        pending && 'opacity-60',
      )}
    >
      <header className="flex items-baseline justify-between gap-300">
        <h3 className="text-300 font-semibold text-foreground" title={meta.hint}>
          {meta.label}
        </h3>
        <span className="text-200 text-muted-foreground">年間 EBITDA</span>
      </header>

      <dl className="grid grid-cols-2 gap-300">
        <div>
          <dt className="text-200 text-muted-foreground">実績</dt>
          <dd className="font-numeric text-600 font-semibold tabular-nums text-foreground @lg:text-hero-700" title={`${formatYen(base)} 円`}>
            {formatOku(base)}
          </dd>
        </div>
        <div>
          <dt className="text-200 text-muted-foreground">条件変更後</dt>
          <dd className="font-numeric text-600 font-bold tabular-nums text-foreground @lg:text-hero-700" title={`${formatYen(scenario)} 円`}>
            {formatOku(scenario)}
          </dd>
        </div>
      </dl>

      <p className={cn('flex flex-wrap items-center gap-x-200 text-300 font-medium', TONE[direction])}>
        <span className="text-muted-foreground">実績との差</span>
        <Arrow direction={direction} className="icon-size-200 shrink-0" />
        <span>{WORD[direction]}</span>
        <span className="font-numeric tabular-nums">{formatSignedOku(delta)}</span>
        {direction !== 'flat' && <span className="font-numeric tabular-nums">{formatPercent(delta, base)}</span>}
      </p>
      <p className="font-numeric text-200 tabular-nums text-muted-foreground">差 {formatSignedYen(delta)} 円</p>
    </section>
  );
}

export function ResultBandSkeleton() {
  return (
    <div aria-hidden className="grid gap-400 md:grid-cols-2">
      <Skeleton className="h-card" />
      <Skeleton className="h-card" />
    </div>
  );
}

// 画面の主役。全額連結と持分管理の両方を、いつも並べて出す。
export function ResultBand({ result, metric, pending, period }: { result: SimulationResult; metric: Metric; pending: boolean; period: { from: string; to: string } }) {
  return (
    <div className="space-y-300">
      <div className="grid gap-400 md:grid-cols-2">
        <Figure result={result} metric="full" selected={metric === 'full'} pending={pending} />
        <Figure result={result} metric="management" selected={metric === 'management'} pending={pending} />
      </div>
      <p className="text-200 text-muted-foreground">
        架空データによる試算です（下の「この画面の読み方」を参照）。年間 EBITDA（{formatDate(period.from)}〜{formatDate(period.to)}）。増減は、赤＝減少、青＝増加で、符号と文字も付けています。
      </p>
      {/* 確定した値だけを読み上げる（スライダーを動かす途中の値は読まない） */}
      <p className="sr-only" role="status" aria-live="polite">
        {pending
          ? ''
          : `全額連結 ${WORD[directionOf(result.delta.full)]} ${formatSignedOku(result.delta.full)}。持分管理 ${WORD[directionOf(result.delta.management)]} ${formatSignedOku(result.delta.management)}。`}
      </p>
    </div>
  );
}
