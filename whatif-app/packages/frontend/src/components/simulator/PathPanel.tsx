import { ArrowDown, CircleCheck, TriangleAlert } from 'lucide-react';

import type { PathsState } from '@/hooks/use-event-paths';
import { eventName, eventPeriod, sortEvents } from '@/lib/events';
import { formatMillion, formatSignedMillion, subtract } from '@/lib/format';
import { buildChain, checkConsistency, groupByEntity } from '@/lib/paths';
import type { EventImpact, ModelEvent } from '@/lib/types';
import { cn } from '@/lib/utils';

import { activityLabel, directionLabel, sectorLabel } from './labels';
import { Chip, ErrorNotice, SectionLabel, Skeleton, Spinner } from './primitives';

function Chain({ state, event }: { state: Extract<PathsState, { phase: 'ready' }>; event: ModelEvent }) {
  const chain = buildChain(state.paths);
  const consistency = checkConsistency(state.paths, event);

  return (
    <div className="space-y-400">
      <ol className="space-y-100">
        {chain.map((node, i) => (
          <li key={node.type}>
            {node.via && (
              <p className="flex items-center gap-200 px-300 py-100 font-numeric text-200 text-muted-foreground">
                <ArrowDown aria-hidden className="icon-size-100 shrink-0" />
                <span>{node.from ? `${node.via}（${node.from}から）` : node.via}</span>
              </p>
            )}
            <div className={cn('flex items-baseline justify-between gap-300 rounded-md border px-300 py-200', i === 0 ? 'border-foreground bg-card' : 'border-border bg-card')}>
              <div className="min-w-0">
                <p className="text-300 font-semibold text-foreground">{node.label}</p>
                <p className="font-numeric text-200 text-muted-foreground">{node.type}</p>
              </div>
              <p className="shrink-0 font-numeric text-400 font-semibold tabular-nums text-foreground">
                {node.count.toLocaleString('ja-JP')}
                <span className="ml-100 text-200 font-normal text-muted-foreground">件</span>
              </p>
            </div>
          </li>
        ))}
      </ol>

      <p
        role="status"
        className={cn('flex items-start gap-200 rounded-md border px-300 py-200 text-300', consistency.match ? 'border-border text-foreground' : 'border-destructive text-destructive')}
      >
        {consistency.match ? <CircleCheck aria-hidden className="icon-size-200 mt-100 shrink-0 text-brand-foreground" /> : <TriangleAlert aria-hidden className="icon-size-200 mt-100 shrink-0" />}
        <span>
          {consistency.match
            ? `グラフと Lakehouse で、影響額の件数が一致しています（${consistency.graphEffects} 件）。`
            : `グラフ ${consistency.graphEffects} 件、Lakehouse ${consistency.lakehouseEffects} 件で、影響額の件数が一致していません。金額は Lakehouse の値で計算しています。`}
        </span>
      </p>
    </div>
  );
}

function ByEntity({ state }: { state: Extract<PathsState, { phase: 'ready' }> }) {
  const groups = groupByEntity(state.paths);
  return (
    <ul className="space-y-100">
      {groups.map((g) => (
        <li key={g.entityId} className="flex items-baseline justify-between gap-300 rounded-md border border-border bg-card px-300 py-200">
          <div className="min-w-0">
            <p className="truncate font-numeric text-300 text-foreground">{g.entityId}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-200 text-200">
              <dt className="text-muted-foreground">活動</dt>
              <dd className="min-w-0 break-words text-foreground">{g.activityTypes.map(activityLabel).join('・')}</dd>
              <dt className="text-muted-foreground">商品</dt>
              <dd className="min-w-0 break-words text-foreground">{g.commodities.join('・')}</dd>
            </dl>
          </div>
          <p className="shrink-0 font-numeric text-300 tabular-nums text-foreground">{g.effects} 件</p>
        </li>
      ))}
    </ul>
  );
}

export function PathPanel({
  events,
  selectedId,
  onSelect,
  state,
  onRetry,
  impact,
}: {
  events: readonly ModelEvent[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  state: PathsState;
  onRetry: () => void;
  impact: EventImpact | undefined;
}) {
  const sorted = sortEvents(events);
  const event = events.find((e) => e.eventId === selectedId);

  return (
    <div className="space-y-400">
      <div className="space-y-200">
        <SectionLabel id="path-label">Ontology の経路</SectionLabel>
        <p className="text-200 text-muted-foreground">
          選んだイベントが、オントロジーのグラフ上で何につながっているかを、グラフに問い合わせて表示します。金額は Lakehouse の値で計算しており、グラフは構造（つながり）を示します。
        </p>
      </div>

      <div className="space-y-100">
        <label htmlFor="path-event" className="text-300 font-semibold text-foreground">
          イベントを選ぶ
        </label>
        <select
          id="path-event"
          value={selectedId ?? ''}
          onChange={(e) => onSelect(e.currentTarget.value)}
          className="h-control w-full rounded-md border border-input bg-card px-300 text-300 text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {sorted.map((e) => (
            <option key={e.eventId} value={e.eventId}>
              {sectorLabel(e.sector)}・{eventName(e)}（{e.eventId}）
            </option>
          ))}
        </select>
      </div>

      {event && (
        <div className="space-y-200 rounded-lg border border-border bg-card p-300">
          <p className="flex flex-wrap items-center gap-x-200 gap-y-100">
            <Chip tone={event.direction === 'negative' ? 'negative' : 'positive'}>{directionLabel(event.direction)}</Chip>
            <span className="text-200 text-muted-foreground">重要度 {event.severity}</span>
            <span className="text-200 text-muted-foreground">{eventPeriod(event)}</span>
          </p>
          <p className="text-300 text-foreground">{eventName(event)}</p>
          {impact && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-300 gap-y-100 border-t border-border pt-200 text-200">
              <dt className="text-muted-foreground">影響額（全額連結）</dt>
              <dd className="text-right font-numeric tabular-nums text-foreground">
                {formatMillion(impact.baseFull)} → {formatMillion(impact.scenarioFull)}
              </dd>
              <dt className="text-muted-foreground">差（百万円）</dt>
              <dd className="text-right font-numeric font-semibold tabular-nums text-foreground">
                {formatSignedMillion(subtract(impact.scenarioFull, impact.baseFull))}
              </dd>
            </dl>
          )}
        </div>
      )}

      {state.phase === 'loading' && (
        <div className="space-y-300">
          <Spinner label="グラフに問い合わせています…（初回は最大 1 分ほどかかります）" />
          <Skeleton className="h-card" />
        </div>
      )}
      {state.phase === 'error' && <ErrorNotice error={state.error} onRetry={onRetry} />}
      {state.phase === 'ready' && event && (
        <>
          <Chain state={state} event={event} />
          <section aria-labelledby="by-entity-label" className="space-y-200">
            <SectionLabel id="by-entity-label">つながっている会社</SectionLabel>
            <ByEntity state={state} />
          </section>
          <p className="text-200 text-muted-foreground">グラフの問い合わせ: {(state.ms / 1000).toFixed(1)} 秒</p>
        </>
      )}
    </div>
  );
}
