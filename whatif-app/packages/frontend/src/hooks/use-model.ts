import { useCallback, useEffect, useRef, useState } from 'react';

import { api as defaultApi, type Api } from '@/lib/api';
import { explainCode, explainThrown, type Explained } from '@/lib/errors';
import type { Model } from '@/lib/types';

export type ModelState =
  | { phase: 'loading'; elapsedSec: number }
  | { phase: 'ready'; model: Model; source: 'cache' | 'loaded'; ms: number }
  | { phase: 'error'; error: Explained; code: string };

// 画面を開いたときに 1 回だけ読む。自動の再試行はしない（再試行は人が押す）。
export function useModel(api: Api = defaultApi): { state: ModelState; retry: () => void } {
  const [state, setState] = useState<ModelState>({ phase: 'loading', elapsedSec: 0 });
  const [attempt, setAttempt] = useState(0);
  // 古い呼び出しの結果が、新しい呼び出しの状態を上書きしないようにする
  const current = useRef(0);

  useEffect(() => {
    const id = ++current.current;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (current.current !== id) return;
      setState((s) => (s.phase === 'loading' ? { phase: 'loading', elapsedSec: Math.floor((Date.now() - startedAt) / 1000) } : s));
    }, 1000);

    void (async () => {
      try {
        const out = await api.loadModel();
        if (current.current !== id) return;
        if (out.ok) setState({ phase: 'ready', model: out.model, source: out.source, ms: Date.now() - startedAt });
        else setState({ phase: 'error', error: explainCode(out.code), code: out.code });
      } catch (error) {
        if (current.current !== id) return;
        setState({ phase: 'error', error: explainThrown(error), code: 'THROWN' });
      } finally {
        clearInterval(timer);
      }
    })();

    return () => {
      clearInterval(timer);
      // この呼び出しの結果は使わない
      current.current += 1;
    };
  }, [api, attempt]);

  const retry = useCallback(() => {
    setState({ phase: 'loading', elapsedSec: 0 });
    setAttempt((n) => n + 1);
  }, []);

  return { state, retry };
}
