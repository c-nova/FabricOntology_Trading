import { Moon, Sun } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useEventPaths } from '@/hooks/use-event-paths';
import { useModel } from '@/hooks/use-model';
import { useSimulation } from '@/hooks/use-simulation';
import { useTheme } from '@/hooks/theme.context';
import { type Api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { defaultPathEvent } from '@/lib/paths';
import { INITIAL_STATE, isDefault, type ScenarioState } from '@/lib/scenario';
import type { Metric, Model } from '@/lib/types';

import { Breakdown } from './Breakdown';
import { ConditionsPanel } from './ConditionsPanel';
import { FuturePanel } from './FuturePanel';
import { Notes } from './Notes';
import { PathPanel } from './PathPanel';
import { ResultBand, ResultBandSkeleton } from './ResultBand';
import { Waterfall } from './Waterfall';
import { METRICS } from './labels';
import { ErrorNotice, Segmented, SectionLabel, Skeleton, Spinner } from './primitives';

function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? 'ライトモードにする' : 'ダークモードにする'}
      className="inline-flex h-control w-control items-center justify-center rounded-md border border-input bg-card text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {isDark ? <Sun aria-hidden className="icon-size-300" /> : <Moon aria-hidden className="icon-size-300" />}
    </button>
  );
}

function Shell({ children, trailing }: { children: React.ReactNode; trailing?: React.ReactNode }) {
  return (
    <div className="min-h-full bg-background">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-300 px-500 py-300">
          <div className="min-w-0">
            <h1 className="font-heading text-500 font-bold leading-500 text-foreground">What-if シミュレータ</h1>
            <p className="text-200 text-muted-foreground">過去の実績と将来の予測を、条件変更後の EBITDA と比べる。</p>
          </div>
          <div className="flex items-center gap-300">
            {trailing}
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-content px-500 py-600">{children}</main>
    </div>
  );
}

function Loading({ elapsedSec }: { elapsedSec: number }) {
  return (
    <Shell>
      <div className="space-y-600">
        <div className="space-y-200">
          <Spinner label="オントロジーのグラフと Lakehouse に接続しています…" />
          <p className="text-300 text-muted-foreground">
            使われていなかった後の初回は、グラフの起動に最大 1 分ほどかかります。{elapsedSec > 0 && `（${elapsedSec} 秒経過）`}
          </p>
        </div>
        <ResultBandSkeleton />
        <div className="grid gap-600 lg:grid-cols-[var(--spacing-rail)_1fr]">
          <Skeleton className="h-card" />
          <Skeleton className="h-card" />
        </div>
      </div>
    </Shell>
  );
}

// モデルが読めた後の画面。条件の状態とシミュレーションは、ここで持つ。
function Ready({ model, api }: { model: Model; api?: Api }) {
  const [scenario, setScenario] = useState<ScenarioState>(INITIAL_STATE);
  const [metric, setMetric] = useState<Metric>('full');
  const [view, setView] = useState<'history' | 'future'>('history');
  const [visitedFuture, setVisitedFuture] = useState(false);
  const sim = useSimulation(scenario, true, api);

  // 経路を見せるイベント。まだ選んでいなければ、基準の影響が最大のイベントにする
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const suggested = useMemo(() => (sim.result ? defaultPathEvent(sim.result.eventImpacts) : undefined), [sim.result]);
  const selectedId = picked ?? suggested ?? model.events[0]?.eventId;
  const paths = useEventPaths(selectedId, api);

  const impact = sim.result?.eventImpacts.find((i) => i.eventId === selectedId);
  const changed = !isDefault(scenario);

  return (
    <Shell
      trailing={
        view === 'history' ? <Segmented
          legend="表示する指標"
          name="metric"
          value={metric}
          options={METRICS.map((m) => ({ id: m.id, label: m.label, title: m.hint }))}
          onChange={setMetric}
        /> : undefined
      }
    >
      <div className="space-y-600">
        <Segmented
          legend="分析の切り替え"
          name="analysis-view"
          value={view}
          options={[
            { id: 'history', label: '過去の実績' },
            { id: 'future', label: '将来の予測' },
          ]}
          onChange={(next) => {
            setView(next);
            if (next === 'future') setVisitedFuture(true);
          }}
        />
        <div hidden={view !== 'history'} className="space-y-600">
        <section aria-labelledby="result-label" className="space-y-300">
          <div className="flex flex-wrap items-baseline justify-between gap-200">
            <SectionLabel id="result-label">結果</SectionLabel>
            <p className="flex gap-x-300 text-200 text-muted-foreground">
              <span>{changed ? '条件を変更中' : '実績のまま'}</span>
              {sim.pending && <span>計算中…</span>}
            </p>
          </div>
          {sim.error && <ErrorNotice error={sim.error} />}
          {sim.result ? <ResultBand result={sim.result} metric={metric} pending={sim.pending} period={sim.result.period} /> : !sim.error && <ResultBandSkeleton />}
        </section>

        <div className="grid items-start gap-600 lg:grid-cols-[var(--spacing-rail)_1fr] xl:grid-cols-[var(--spacing-rail)_1fr_var(--spacing-aside)]">
          <aside aria-label="条件" className="lg:sticky lg:top-400">
            <ConditionsPanel events={model.events} state={scenario} onChange={setScenario} />
          </aside>

          <div className="min-w-0 space-y-600">
            {sim.result ? (
              <>
                <Waterfall result={sim.result} metric={metric} />
                <Breakdown result={sim.result} metric={metric} events={model.events} />
              </>
            ) : (
              !sim.error && <Skeleton className="h-card" />
            )}
          </div>

          <aside aria-label="Ontology の経路" className="min-w-0 lg:col-span-2 xl:col-span-1">
            <PathPanel events={model.events} selectedId={selectedId} onSelect={setPicked} state={paths.state} onRetry={paths.retry} impact={impact} />
          </aside>
        </div>

        <Notes />

        <p className="text-200 text-muted-foreground">
          {model.events.length} 件のイベント、{model.companies.length} 社。集計期間 {formatDate(model.period.from)}〜{formatDate(model.period.to)}。
        </p>
        </div>
        <div hidden={view !== 'future'} className="space-y-600">
          {visitedFuture && <FuturePanel events={model.events} api={api} />}
        </div>
      </div>
    </Shell>
  );
}

// 画面全体。モデル（イベントと会社の一覧）が読めるまで、条件は出さない。
export function Simulator({ api }: { api?: Api }) {
  const { state, retry } = useModel(api);

  if (state.phase === 'loading') return <Loading elapsedSec={state.elapsedSec} />;
  if (state.phase === 'error') {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl pt-800">
          <ErrorNotice error={state.error} onRetry={retry} />
        </div>
      </Shell>
    );
  }
  return <Ready model={state.model} api={api} />;
}
