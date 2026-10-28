import { getRayfinClient } from '@/lib/rayfin-client';

import type { EventPathsOutput, ForecastModelOutput, ForecastScenario, ForecastSimulationOutput, LoadModelOutput, ScenarioInput, SimulateOutput } from './types';

// Functions の呼び出し口。フックはここだけを使う（テストでは、この 3 つを差し替える）。
// サーバーが返した「期待される失敗」（ok: false）は値として返し、通信の失敗は例外のまま投げる。

// Graph の初回は最大約 1 分かかる（放置後）。余裕を持って 180 秒。ホストの上限は 250 秒。
const LOAD_TIMEOUT_MS = 180_000;
const SIMULATE_TIMEOUT_MS = 60_000;
const PATHS_TIMEOUT_MS = 120_000;

// フックは api の参照が変わると再取得する。固定の参照を渡すこと（既定は下の定数。テストではレンダーの外で作る）。
export interface Api {
  loadModel: () => Promise<LoadModelOutput>;
  simulate: (scenario: ScenarioInput) => Promise<SimulateOutput>;
  eventPaths: (eventId: string) => Promise<EventPathsOutput>;
  loadForecast: () => Promise<ForecastModelOutput>;
  simulateForecast: (scenario: ForecastScenario) => Promise<ForecastSimulationOutput>;
}

export const api: Api = {
  async loadModel() {
    const client = await getRayfinClient();
    return client.functions.loadModel.invoke(undefined, { timeoutMs: LOAD_TIMEOUT_MS });
  },
  async simulate(scenario) {
    const client = await getRayfinClient();
    return client.functions.simulate.invoke({ scenario }, { timeoutMs: SIMULATE_TIMEOUT_MS });
  },
  async eventPaths(eventId) {
    const client = await getRayfinClient();
    return client.functions.eventPaths.invoke({ eventId }, { timeoutMs: PATHS_TIMEOUT_MS });
  },
  async loadForecast() {
    const client = await getRayfinClient();
    return client.functions.loadForecast.invoke(undefined, { timeoutMs: LOAD_TIMEOUT_MS });
  },
  async simulateForecast(scenario) {
    const client = await getRayfinClient();
    return client.functions.simulateForecast.invoke({ scenario }, { timeoutMs: LOAD_TIMEOUT_MS });
  },
};
