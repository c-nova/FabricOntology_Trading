import { RotateCcw } from 'lucide-react';
import { useId, type CSSProperties } from 'react';

import { eventName, eventPeriod, sortEvents } from '@/lib/events';
import {
  EVENT_RANGE,
  FX_RANGE,
  PRESETS,
  eventPercentOf,
  isDefault,
  setEvent,
  setFx,
  type ScenarioState,
} from '@/lib/scenario';
import type { ModelEvent } from '@/lib/types';
import { cn } from '@/lib/utils';

import { Chip, SectionLabel } from './primitives';

// 更新は「前の状態 → 次の状態」の関数で受け渡す。再描画の前に操作が重なっても、後の操作が前の操作を消さない。
export type Update = (updater: (previous: ScenarioState) => ScenarioState) => void;
import { directionLabel, sectorLabel } from './labels';

// 「基準（変更なし）」の位置（0〜100%）。スライダーの溝の目印に使う。
const neutralAt = (min: number, max: number, neutral: number): string => `${((neutral - min) / (max - min)) * 100}%`;

const fxText = (percent: number): string =>
  percent === 0 ? '実績のまま' : percent < 0 ? `円高 ${Math.abs(percent)}%` : `円安 ${percent}%`;

const eventText = (percent: number): string =>
  percent === EVENT_RANGE.neutral ? '実績のまま（100%）' : percent === 0 ? '起きなかったことにする（0%）' : `影響を ${percent}% にする`;

function FxControl({ state, onChange }: { state: ScenarioState; onChange: Update }) {
  const id = useId();
  const style = { '--neutral': neutralAt(FX_RANGE.min, FX_RANGE.max, 0) } as CSSProperties;
  return (
    <div className="space-y-200">
      <div className="flex items-baseline justify-between gap-300">
        <label htmlFor={id} className="text-300 font-semibold text-foreground">
          為替（USD / 円）
        </label>
        <output htmlFor={id} className={cn('font-numeric text-300 tabular-nums', state.fxPercent === 0 ? 'text-muted-foreground' : 'font-semibold text-foreground')}>
          {fxText(state.fxPercent)}
        </output>
      </div>
      <input
        id={id}
        type="range"
        className="range"
        style={style}
        min={FX_RANGE.min}
        max={FX_RANGE.max}
        step={FX_RANGE.step}
        value={state.fxPercent}
        aria-valuetext={fxText(state.fxPercent)}
        onChange={(e) => {
          const value = e.currentTarget.valueAsNumber;
          onChange((prev) => setFx(prev, value));
        }}
      />
      <div className="flex justify-between text-200 text-muted-foreground" aria-hidden>
        <span>円高 {Math.abs(FX_RANGE.min)}%</span>
        <span>円安 {FX_RANGE.max}%</span>
      </div>
      <p className="text-200 text-muted-foreground">USD 建ての子会社の、円換算レートだけを動かします（為替ヘッジや価格転嫁は反映しません）。</p>
    </div>
  );
}

function EventControl({ event, state, onChange }: { event: ModelEvent; state: ScenarioState; onChange: Update }) {
  const id = useId();
  const percent = eventPercentOf(state, event.eventId);
  const changed = percent !== EVENT_RANGE.neutral;
  const style = { '--neutral': neutralAt(EVENT_RANGE.min, EVENT_RANGE.max, EVENT_RANGE.neutral) } as CSSProperties;
  const negative = event.direction === 'negative';

  return (
    <li className={cn('space-y-100 rounded-md border px-300 py-200', changed ? 'border-foreground bg-card' : 'border-transparent')}>
      <div className="flex items-start justify-between gap-300">
        <div className="min-w-0">
          <label htmlFor={id} className="block text-300 font-medium text-foreground">
            {eventName(event)}
          </label>
          <p className="flex flex-wrap items-center gap-x-200 gap-y-100 text-200 text-muted-foreground">
            <Chip tone={negative ? 'negative' : 'positive'}>{directionLabel(event.direction)}</Chip>
            <span className="font-numeric">{event.eventId}</span>
            <span>{eventPeriod(event)}</span>
          </p>
        </div>
        <output htmlFor={id} className={cn('shrink-0 font-numeric text-300 tabular-nums', changed ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
          {percent}%
        </output>
      </div>
      <input
        id={id}
        type="range"
        className="range"
        style={style}
        min={EVENT_RANGE.min}
        max={EVENT_RANGE.max}
        step={EVENT_RANGE.step}
        value={percent}
        aria-valuetext={eventText(percent)}
        onChange={(e) => {
          const value = e.currentTarget.valueAsNumber;
          onChange((prev) => setEvent(prev, event.eventId, value));
        }}
      />
    </li>
  );
}

export function ConditionsPanel({
  events,
  state,
  onChange,
  disabled,
}: {
  events: readonly ModelEvent[];
  state: ScenarioState;
  onChange: Update;
  disabled?: boolean;
}) {
  const sorted = sortEvents(events);
  const bySector = new Map<string, ModelEvent[]>();
  for (const e of sorted) bySector.set(e.sector, [...(bySector.get(e.sector) ?? []), e]);

  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-600">
      <legend className="sr-only">シナリオの条件</legend>

      <section aria-labelledby="presets-label" className="space-y-200">
        <SectionLabel id="presets-label">ワンタッチ</SectionLabel>
        <div className="flex flex-wrap gap-200">
          {PRESETS.filter((p) => p.id !== 'reset').map((p) => (
            <button
              key={p.id}
              type="button"
              title={p.hint}
              onClick={() => onChange((prev) => p.apply(prev, events))}
              className="h-control rounded-md border border-input bg-card px-300 text-300 font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            disabled={isDefault(state)}
            onClick={() => onChange((prev) => PRESETS.find((p) => p.id === 'reset')!.apply(prev, events))}
            className="inline-flex h-control items-center gap-100 rounded-md px-300 text-300 font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:text-muted-foreground disabled:no-underline"
          >
            <RotateCcw aria-hidden className="icon-size-200" />
            実績に戻す
          </button>
        </div>
      </section>

      <section aria-labelledby="fx-label" className="space-y-300">
        <SectionLabel id="fx-label">為替</SectionLabel>
        <FxControl state={state} onChange={onChange} />
      </section>

      <section aria-labelledby="events-label" className="space-y-300">
        <SectionLabel id="events-label">イベントの影響</SectionLabel>
        <p className="text-200 text-muted-foreground">
          100% が実績のままです。下げると影響が小さく、上げると大きくなります。変えたイベントは枠で示します。
        </p>
        <div className="space-y-400">
          {[...bySector.entries()].map(([sector, list]) => (
            <div key={sector} className="space-y-100">
              <h3 className="px-300 text-200 font-semibold text-muted-foreground">{sectorLabel(sector)}</h3>
              <ul className="space-y-100">
                {list.map((e) => (
                  <EventControl key={e.eventId} event={e} state={state} onChange={onChange} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </fieldset>
  );
}
