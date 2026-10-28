import { useEffect, useState } from 'react';

import { api as defaultApi, type Api } from '@/lib/api';
import { explainCode, explainThrown, type Explained } from '@/lib/errors';
import type { GraphPath } from '@/lib/types';

export type PathsState =
  | { phase: 'idle' }
  | { phase: 'loading'; eventId: string }
  | { phase: 'ready'; eventId: string; paths: GraphPath[]; ms: number }
  | { phase: 'error'; eventId: string; error: Explained };

interface Entry {
  paths: GraphPath[];
  ms: number;
}

// イベントごとに経路を取る。同じイベントは再取得しない（Graph は 1〜3 秒、初回は最大 1 分）。
// 保持するのは「取れた結果」と「失敗」だけ。読み込み中などの表示状態は、いまのイベントから描画時に導く。
export function useEventPaths(eventId: string | undefined, api: Api = defaultApi): { state: PathsState; retry: () => void } {
  const [entries, setEntries] = useState<ReadonlyMap<string, Entry>>(() => new Map());
  const [failures, setFailures] = useState<ReadonlyMap<string, Explained>>(() => new Map());
  // 再試行のたびに増やして、effect をやり直す
  const [attempt, setAttempt] = useState(0);

  const known = eventId !== undefined && (entries.has(eventId) || failures.has(eventId));

  useEffect(() => {
    if (eventId === undefined || known) return;
    let cancelled = false;
    const startedAt = Date.now();

    void (async () => {
      try {
        const out = await api.eventPaths(eventId);
        // イベントを切り替えた後に返った応答は、使わない
        if (cancelled) return;
        if (out.ok) setEntries((prev) => new Map(prev).set(eventId, { paths: out.paths, ms: Date.now() - startedAt }));
        else setFailures((prev) => new Map(prev).set(eventId, explainCode(out.code)));
      } catch (e) {
        if (cancelled) return;
        setFailures((prev) => new Map(prev).set(eventId, explainThrown(e)));
      }
    })();

    return () => {
      cancelled = true;
    };
    // known は、結果が入ったら effect を止めるために見る（結果が入った後の再実行で、再取得しない）
  }, [eventId, known, api, attempt]);

  let state: PathsState = { phase: 'idle' };
  if (eventId !== undefined) {
    const entry = entries.get(eventId);
    const failure = failures.get(eventId);
    if (entry) state = { phase: 'ready', eventId, paths: entry.paths, ms: entry.ms };
    else if (failure) state = { phase: 'error', eventId, error: failure };
    else state = { phase: 'loading', eventId };
  }

  const retry = () => {
    if (eventId === undefined) return;
    setFailures((prev) => {
      const next = new Map(prev);
      next.delete(eventId);
      return next;
    });
    setAttempt((n) => n + 1);
  };

  return { state, retry };
}
