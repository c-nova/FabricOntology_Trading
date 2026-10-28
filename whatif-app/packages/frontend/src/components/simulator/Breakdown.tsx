import { useId, useRef, useState, type KeyboardEvent } from 'react';

import { geometry, rangeOf } from '@/lib/bars';
import { eventName } from '@/lib/events';
import { formatMillion, formatSignedMillion, formatSignedYen, formatYen, subtract } from '@/lib/format';
import type { Breakdown as Row, Metric, ModelEvent, SimulationResult } from '@/lib/types';
import { cn } from '@/lib/utils';

import { sectorLabel } from './labels';
import { SectionLabel } from './primitives';

type Tab = 'entity' | 'sector' | 'month' | 'event';

const TABS: readonly { id: Tab; label: string }[] = [
  { id: 'entity', label: '会社別' },
  { id: 'sector', label: 'セクター別' },
  { id: 'month', label: '月別' },
  { id: 'event', label: 'イベント別' },
];

interface Line {
  key: string;
  label: string;
  sub?: string;
  base: string;
  scenario: string;
  delta: string;
}

function toLines(tab: Tab, result: SimulationResult, metric: Metric, events: readonly ModelEvent[]): Line[] {
  const fromRows = (rows: readonly Row[], label: (r: Row) => string, sub?: (r: Row) => string | undefined): Line[] =>
    rows.map((r) => ({ key: r.key, label: label(r), sub: sub?.(r), base: r.base[metric], scenario: r.scenario[metric], delta: r.delta[metric] }));

  if (tab === 'entity') return fromRows(result.byEntity, (r) => r.label, (r) => r.key);
  if (tab === 'sector') return fromRows(result.bySector, (r) => sectorLabel(r.key));
  if (tab === 'month') return fromRows(result.byMonth, (r) => r.label);

  const byId = new Map(events.map((e) => [e.eventId, e]));
  return result.eventImpacts.map((i) => {
    const base = metric === 'full' ? i.baseFull : i.baseManagement;
    const scenario = metric === 'full' ? i.scenarioFull : i.scenarioManagement;
    const event = byId.get(i.eventId);
    return { key: i.eventId, label: event ? eventName(event) : i.eventId, sub: i.eventId, base, scenario, delta: subtract(scenario, base) };
  });
}

const COLUMN_NOTE: Record<Tab, string> = {
  entity: '各社の EBITDA。USD 建ては円換算後の値です。',
  sector: '業種ごとの EBITDA の合計です。',
  month: '月ごとの EBITDA の合計です。',
  event: 'イベントが期間内に生んだ影響額の合計です。EBITDA 全体ではなく、イベント由来の分だけです。',
};

// 内訳の表。差の列に、0 を中心にした棒を添える。
export function Breakdown({ result, metric, events }: { result: SimulationResult; metric: Metric; events: readonly ModelEvent[] }) {
  const [tab, setTab] = useState<Tab>('entity');
  const baseId = useId();
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);

  const lines = toLines(tab, result, metric, events);
  const { min, max } = rangeOf(lines.map((l) => l.delta));

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    const target = e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : step === 0 ? undefined : (index + step + TABS.length) % TABS.length;
    if (target === undefined) return;
    e.preventDefault();
    setTab(TABS[target]!.id);
    tabs.current[target]?.focus();
  };

  return (
    <section aria-labelledby={`${baseId}-label`} className="space-y-300">
      <div className="flex flex-wrap items-baseline justify-between gap-200">
        <SectionLabel id={`${baseId}-label`}>内訳</SectionLabel>
        <p className="text-200 text-muted-foreground">単位は百万円</p>
      </div>

      <div role="tablist" aria-label="内訳の切り替え" className="flex flex-wrap gap-x-400 border-b border-border">
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`${baseId}-panel`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              '-mb-px h-control border-b-2 px-100 text-300 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
              tab === t.id ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id={`${baseId}-panel`} role="tabpanel" aria-labelledby={`${baseId}-tab-${tab}`} className="space-y-200">
        <p className="text-200 text-muted-foreground">{COLUMN_NOTE[tab]}</p>
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-table border-collapse text-300">
            <thead>
              <tr className="border-b border-border text-200 text-muted-foreground">
                <th scope="col" className="px-300 py-200 text-left font-semibold">項目</th>
                <th scope="col" className="px-300 py-200 text-right font-semibold">実績</th>
                <th scope="col" className="px-300 py-200 text-right font-semibold">シナリオ</th>
                <th scope="col" className="px-300 py-200 text-right font-semibold">差</th>
                <th scope="col" className="w-bar px-300 py-200 text-left font-semibold">
                  <span className="sr-only">差の大きさ</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => {
                const n = Number(l.delta);
                const g = geometry(0, n, min, max);
                return (
                  <tr key={l.key} className="border-b border-border last:border-b-0">
                    <th scope="row" className="px-300 py-200 text-left font-medium text-foreground">
                      {l.label}
                      {l.sub && <span className="block font-numeric text-200 font-normal text-muted-foreground">{l.sub}</span>}
                    </th>
                    <td className="px-300 py-200 text-right font-numeric tabular-nums text-muted-foreground" title={`${formatYen(l.base)} 円`}>
                      {formatMillion(l.base)}
                    </td>
                    <td className="px-300 py-200 text-right font-numeric tabular-nums text-foreground" title={`${formatYen(l.scenario)} 円`}>
                      {formatMillion(l.scenario)}
                    </td>
                    <td
                      className={cn('px-300 py-200 text-right font-numeric font-semibold tabular-nums', n < 0 ? 'text-destructive' : n > 0 ? 'text-brand-foreground' : 'text-muted-foreground')}
                      title={`${formatSignedYen(l.delta)} 円`}
                    >
                      {formatSignedMillion(l.delta)}
                    </td>
                    <td className="px-300 py-200">
                      <div aria-hidden className="relative h-300">
                        <div className="absolute inset-y-0 w-px bg-foreground" style={{ left: `${g.zero}%` }} />
                        {n !== 0 && <div className={cn('absolute inset-y-100 rounded-sm', n < 0 ? 'bg-destructive' : 'bg-brand')} style={{ left: `${g.left}%`, width: `${g.width}%` }} />}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
