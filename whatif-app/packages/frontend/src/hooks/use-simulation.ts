import { useEffect, useMemo, useState } from 'react';

import { api as defaultApi, type Api } from '@/lib/api';
import { explainCode, explainThrown, type Explained } from '@/lib/errors';
import { sameScenario, toScenario, type ScenarioState } from '@/lib/scenario';
import type { SimulationResult } from '@/lib/types';

export interface SimulationState {
  /** 直近に成功した結果。条件を動かしている間も、置き換わるまで残す（画面が空にならない）。 */
  result: SimulationResult | undefined;
  /** 表示中の結果が、最新の条件のものではない（計算中）。 */
  pending: boolean;
  /** 最新の条件の計算が失敗したときだけ入る。条件を変えれば消える。 */
  error: Explained | undefined;
}

export const DEBOUNCE_MS = 250;

interface Settled {
  state: ScenarioState;
  result?: SimulationResult;
  error?: Explained;
}

// 条件が変わるたびに、少し待ってから計算する。
// 応答が逆順に返っても、最後に出した条件の結果だけを採用する（古い結果で上書きしない）。
// pending / error は「どの条件の結果か」から描画時に導く（effect 内で状態を同期しない）。
export function useSimulation(state: ScenarioState, enabled: boolean, api: Api = defaultApi): SimulationState {
  // 最後に成功した結果と、最後に決着した（成功か失敗の）条件
  const [lastGood, setLastGood] = useState<SimulationResult | undefined>(undefined);
  const [settled, setSettled] = useState<Settled | undefined>(undefined);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const timer = setTimeout(() => {
      void (async () => {
        let outcome: Settled;
        try {
          const out = await api.simulate(toScenario(state));
          outcome = out.ok ? { state, result: out.result } : { state, error: explainCode(out.code) };
        } catch (e) {
          outcome = { state, error: explainThrown(e) };
        }
        // 取り消された条件（その後に条件が変わった・画面を離れた）の応答は使わない
        if (cancelled) return;
        setSettled(outcome);
        if (outcome.result) setLastGood(outcome.result);
      })();
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [state, enabled, api]);

  return useMemo(() => {
    const decided = settled !== undefined && sameScenario(settled.state, state);
    return {
      result: lastGood,
      pending: enabled && !decided,
      error: decided ? settled.error : undefined,
    };
  }, [lastGood, settled, state, enabled]);
}
