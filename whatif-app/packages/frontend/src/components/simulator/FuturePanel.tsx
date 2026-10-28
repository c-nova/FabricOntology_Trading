import { useMemo, useState, type CSSProperties } from 'react';

import { useForecast, useForecastSimulation } from '@/hooks/use-forecast';
import type { Api } from '@/lib/api';
import { eventName, sortEvents } from '@/lib/events';
import { formatDate, formatYenAsOku } from '@/lib/format';
import { buildChartQuarters } from '@/lib/quarters';
import type { ForecastLoaded, ModelEvent } from '@/lib/types';

import { ForecastChart } from './ForecastChart';
import { ErrorNotice, SectionLabel, Skeleton, Spinner } from './primitives';

function initialDate(from: string, to: string): string {
  const date = new Date(`${from}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 45);
  const value = date.toISOString().slice(0, 10);
  return value <= to ? value : from;
}

function FutureReady({ data, events, api }: {
  data: ForecastLoaded;
  events: readonly ModelEvent[];
  api?: Api;
}) {
  const { forecast } = data;
  const [eventId, setEventId] = useState(() => events.find((e) => e.eventId === 'FOD_NEG')?.eventId ?? events[0]!.eventId);
  const [eventDate, setEventDate] = useState(() => initialDate(forecast.baseline.period.from, forecast.baseline.period.to));
  const [percent, setPercent] = useState(100);
  const scenario = useMemo(() => ({ eventId, eventDate, scale: percent / 100 }), [eventId, eventDate, percent]);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(eventDate) &&
    eventDate >= forecast.baseline.period.from && eventDate <= forecast.baseline.period.to;
  const sim = useForecastSimulation(scenario, valid, api);
  const result = sim.result;
  const quarters = useMemo(() => buildChartQuarters(data, result), [data, result]);

  return (
    <div className="space-y-500">
      <div className="grid items-start gap-600 lg:grid-cols-[var(--spacing-rail)_1fr]">
        <div className="space-y-400 rounded-lg border border-border bg-card p-400">
          <h3 className="text-400 font-semibold text-foreground">未来のイベントを仮定</h3>
          <div className="space-y-100">
            <label htmlFor="future-event" className="text-300 font-medium text-foreground">過去イベントのパターン</label>
            <select id="future-event" value={eventId} onChange={(e) => setEventId(e.currentTarget.value)}
                    className="h-control w-full rounded-md border border-input bg-card px-200 text-300 text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              {sortEvents(events).map((event) => <option key={event.eventId} value={event.eventId}>{eventName(event)}</option>)}
            </select>
          </div>
          <div className="space-y-100">
            <label htmlFor="future-date" className="text-300 font-medium text-foreground">仮の発生日</label>
            <input id="future-date" type="date" min={forecast.baseline.period.from} max={forecast.baseline.period.to}
                   value={eventDate} onChange={(e) => setEventDate(e.currentTarget.value)}
                   className="h-control w-full rounded-md border border-input bg-card px-200 text-300 text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" />
            {!valid && <p role="alert" className="text-200 text-destructive">予測期間内の日付を指定してください。</p>}
          </div>
          <div className="space-y-100">
            <div className="flex items-center justify-between gap-200">
              <label htmlFor="future-scale" className="text-300 font-medium text-foreground">追加する影響の大きさ</label>
              <output htmlFor="future-scale" className="font-numeric text-300 tabular-nums">{percent}%</output>
            </div>
            <input id="future-scale" type="range" min="0" max="300" step="5" value={percent}
                   aria-valuetext={`過去の影響の ${percent}%`}
                   onChange={(e) => setPercent(e.currentTarget.valueAsNumber)} className="range"
                   style={{ '--neutral': '0%' } as CSSProperties} />
            <p className="text-200 text-muted-foreground">0%は追加なし。100%は過去の影響額をそのまま利用。</p>
          </div>
          <p className="text-200 text-muted-foreground">
            Graphのイベントから影響額・取引活動・日次指標への経路を取得し、Lakehouseの影響額と照合します。
          </p>
          {result && !sim.pending && (
            <p className="text-200 text-muted-foreground">
              照合 {result.historicalEffects} 件。期間内 {result.includedEffects} 件、
              期間外 {result.excludedEffects} 件。
            </p>
          )}
        </div>

        <div className="min-w-0 space-y-400">
          {sim.error && <ErrorNotice error={sim.error} onRetry={sim.retry} />}
          {sim.pending && <Spinner label={result ? '条件変更後を計算中（前の値を表示）…' : 'Graphの経路を照合して計算中…'} />}
          {result && (
            <div className={`grid gap-300 rounded-lg border border-border bg-card p-400 sm:grid-cols-3 ${sim.pending ? 'opacity-60' : ''}`}>
              <div><p className="text-200 text-muted-foreground">基準予測</p><p className="font-numeric text-500 font-semibold tabular-nums">{formatYenAsOku(result.baselineFull)}</p></div>
              <div><p className="text-200 text-muted-foreground">イベント想定後</p><p className="font-numeric text-500 font-semibold tabular-nums">{formatYenAsOku(result.scenarioFull)}</p></div>
              <div><p className="text-200 text-muted-foreground">予測との差</p><p className="font-numeric text-500 font-semibold tabular-nums">{formatYenAsOku(result.deltaFull, 2, true)}</p></div>
            </div>
          )}
          <section aria-labelledby="quarter-chart-label" className="space-y-300">
            <div className="flex flex-wrap items-baseline justify-between gap-200">
              <SectionLabel id="quarter-chart-label">四半期の EBITDA</SectionLabel>
              <span className="text-200 text-muted-foreground">全額連結・円換算</span>
            </div>
            <div className="rounded-lg border border-border bg-card p-400">
              <ForecastChart quarters={quarters} pending={sim.pending} />
            </div>
          </section>
          {result && (
            <>
              {sim.graph && (
                <details className="rounded-lg border border-border bg-card p-400">
                  <summary className="cursor-pointer text-300 font-semibold text-foreground">参照した過去のOntology経路</summary>
                  <div className="mt-200 space-y-100 text-300 text-foreground">
                    <p>イベント → 影響額 {sim.graph.effects}件 → 日次指標 {sim.graph.metrics}件 → 全社KPI {sim.graph.kpis}件</p>
                    <p>影響額 → 取引活動 {sim.graph.activities}件 → 契約 {sim.graph.contracts}件。根拠 {sim.graph.evidence}件。</p>
                    <p className="text-200 text-muted-foreground">表示は過去のGraphの関係です。未来イベントの実体は作成しません。</p>
                  </div>
                </details>
              )}
              <details className="rounded-lg border border-border bg-card p-400">
                <summary className="cursor-pointer text-300 font-semibold text-foreground">影響先の会社別内訳</summary>
                <ul className="mt-200 space-y-100">
                  {result.byEntity.map((company) => (
                    <li key={company.entityId} className="flex justify-between gap-300 text-300">
                      <span>{company.name}</span><span className="font-numeric tabular-nums">{formatYenAsOku(company.deltaFull, 2, true)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </>
          )}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-muted p-400 text-200 text-muted-foreground">
        <p>基準は {formatDate(forecast.baseline.asOf)} 時点の {forecast.model} の四半期予測（Notebook保存日 {formatDate(forecast.generatedAt)}）。未来は全額連結のみです。</p>
        <p>未来のイベントは発生予測ではなく、過去の円換算済み影響を時期と倍率を変えて追加する仮定です。将来の為替やAutoMLの再予測は行いません。基準予測にも過去イベントが含まれ得るため、二重計上の可能性があります。</p>
        <p>棒の業種別は、過去は実績、予測の四半期はAutoMLが会社ごとに出した予測の業種別合計です{data.forecastBySector === null ? '（保存された予測に会社別の値が無いため、予測の棒は内訳を出していません）' : ''}。イベント想定後の内訳は出していません。</p>
        <p>合成データによる探索的な結果です。現在のGraphから過去を再構成し、発生日・影響日に情報が利用可能だったと仮定しています。</p>
        <p>Notebookの更新は最大10分後にアプリへ反映されます。</p>
      </div>
    </div>
  );
}

export function FuturePanel({ events, api }: { events: readonly ModelEvent[]; api?: Api }) {
  const { state, retry } = useForecast(api);
  return (
    <section aria-labelledby="future-label" className="space-y-300 border-t border-border pt-600">
      <div className="space-y-100">
        <SectionLabel id="future-label">将来シミュレーション</SectionLabel>
        <p className="text-300 text-muted-foreground">実績から予測への流れと、イベントを仮定した場合を、折れ線で比べます。</p>
      </div>
      {state.phase === 'loading' && <><Spinner label="Notebookの保存済み予測を読み込み中…" /><Skeleton className="h-card" /></>}
      {state.phase === 'error' && <ErrorNotice error={state.error} onRetry={retry} />}
      {state.phase === 'ready' && events.length === 0 && <p className="text-300 text-muted-foreground">イベントがないため、将来シミュレーションを実行できません。</p>}
      {state.phase === 'ready' && events.length > 0 && <FutureReady data={state.data} events={events} api={api} />}
    </section>
  );
}
