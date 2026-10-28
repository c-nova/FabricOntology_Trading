import { useState } from 'react';

import { getRayfinClient } from '@/lib/rayfin-client';

// 検証用の足場。デプロイ後の Functions（アプリの ID で Graph・Lakehouse に届くか）を確かめるためだけの画面で、
// 本画面を作る段階で置き換える。値は加工せず、そのまま表示する。

type Call = 'probe' | 'loadModel' | 'simulate' | 'eventPaths';

interface Outcome {
  call: Call;
  ms: number;
  body: unknown;
}

const SCENARIO = { events: { FOD_NEG: 0.5 }, fx: { currency: 'USD', factor: 0.9 } };

// 経過時間の計測（コンポーネントの外に置き、レンダー中に不純な関数を呼ばない）
async function timed<T>(fn: () => Promise<T>): Promise<{ value: T; ms: number }> {
  const t0 = performance.now();
  const value = await fn();
  return { value, ms: Math.round(performance.now() - t0) };
}

export function Diagnostics() {
  const [busy, setBusy] = useState<Call | null>(null);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function run(call: Call) {
    setBusy(call);
    setError(null);
    try {
      const client = await getRayfinClient();
      const { value, ms } = await timed(async (): Promise<unknown> => {
        if (call === 'probe') return client.functions.probe.invoke();
        if (call === 'loadModel') return client.functions.loadModel.invoke();
        if (call === 'simulate') return client.functions.simulate.invoke({ scenario: SCENARIO });
        return client.functions.eventPaths.invoke({ eventId: 'FOD_NEG' });
      });
      setOutcomes((prev) => [{ call, ms, body: value }, ...prev]);
    } catch (e) {
      setError(`${call}: ${e instanceof Error ? e.name + ': ' + e.message : 'unknown error'}`);
    } finally {
      setBusy(null);
    }
  }

  const calls: Call[] = ['probe', 'loadModel', 'simulate', 'eventPaths'];

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <header>
        <h1 className="text-xl font-semibold">Functions の接続診断（検証用）</h1>
        <p className="text-sm text-muted-foreground">
          デプロイされた Functions が、アプリの ID で Ontology のグラフと Lakehouse に届くかを確かめます。初回の Graph は最大約1分かかります。
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {calls.map((c) => (
          <button
            key={c}
            type="button"
            data-testid={`run-${c}`}
            disabled={busy !== null}
            onClick={() => void run(c)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            {busy === c ? `${c} を実行中…` : c}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" data-testid="error" className="rounded-md border border-destructive p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <ol className="space-y-3">
        {outcomes.map((o, i) => (
          <li key={`${o.call}-${i}`} className="rounded-md border border-border p-3" data-testid={`outcome-${o.call}`}>
            <p className="text-sm font-medium">
              {o.call} <span className="text-muted-foreground">({o.ms} ms)</span>
            </p>
            <pre className="mt-2 max-h-96 overflow-auto text-xs">{JSON.stringify(o.body, null, 2)}</pre>
          </li>
        ))}
      </ol>
    </main>
  );
}
