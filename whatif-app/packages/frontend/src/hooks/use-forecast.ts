import { useEffect, useState } from 'react';

import { api as defaultApi, type Api } from '@/lib/api';
import { explainCode, explainThrown, type Explained } from '@/lib/errors';
import type { ForecastGraph, ForecastLoaded, ForecastResult, ForecastScenario } from '@/lib/types';

type ForecastState =
  | { phase: 'loading' }
  | { phase: 'ready'; data: ForecastLoaded }
  | { phase: 'error'; error: Explained };

export function useForecast(api: Api = defaultApi) {
  const [state, setState] = useState<ForecastState>({ phase: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const out = await api.loadForecast();
        if (!cancelled) setState(out.ok ? { phase: 'ready', data: out } : { phase: 'error', error: explainCode(out.code) });
      } catch (error) {
        if (!cancelled) setState({ phase: 'error', error: explainThrown(error) });
      }
    })();
    return () => { cancelled = true; };
  }, [api, attempt]);
  return {
    state,
    retry: () => { setState({ phase: 'loading' }); setAttempt((n) => n + 1); },
  };
}

interface Settled {
  scenario: ForecastScenario;
  result?: ForecastResult;
  graph?: ForecastGraph;
  error?: Explained;
}

const same = (a: ForecastScenario, b: ForecastScenario) =>
  a.eventId === b.eventId && a.eventDate === b.eventDate && a.scale === b.scale;

export function useForecastSimulation(scenario: ForecastScenario, valid: boolean, api: Api = defaultApi) {
  const [settled, setSettled] = useState<Settled>();
  const [lastGood, setLastGood] = useState<{ result: ForecastResult; graph: ForecastGraph }>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!valid) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void (async () => {
        let next: Settled;
        try {
          const out = await api.simulateForecast(scenario);
          next = out.ok ? { scenario, result: out.result, graph: out.graph } : { scenario, error: explainCode(out.code) };
        } catch (error) {
          next = { scenario, error: explainThrown(error) };
        }
        if (!cancelled) {
          setSettled(next);
          if (next.result && next.graph) setLastGood({ result: next.result, graph: next.graph });
        }
      })();
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [scenario, valid, api, attempt]);
  const decided = settled !== undefined && same(settled.scenario, scenario);
  return {
    result: valid ? (decided ? settled?.result : lastGood?.result) : undefined,
    graph: valid ? (decided ? settled?.graph : lastGood?.graph) : undefined,
    pending: valid && !decided,
    error: valid && decided ? settled.error : undefined,
    retry: () => { setSettled(undefined); setAttempt((n) => n + 1); },
  };
}
