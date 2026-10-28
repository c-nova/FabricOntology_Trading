import {
  prepare,
  reconcile,
  type BaseData,
  type Prepared,
  type Reconciliation,
} from './engine/index.js';
import { resolveCoordinates, type Coordinates } from './fabric.js';
import { readBaseData } from './lakehouse.js';

// 読み込み結果の保持。Functions のインスタンスが再利用されるあいだだけ効く（保証はない）。
// 効かなくても正しく動く（遅くなるだけ）。効いたかどうかは、結果の source で呼び出し側に分かる。

export interface Loaded {
  coordinates: Coordinates;
  base: BaseData;
  prepared: Prepared;
  reconciliation: Reconciliation;
  loadedAt: number;
  loadMs: number;
}

const TTL_MS = 10 * 60 * 1000;
let cache: Loaded | undefined;
let inflight: Promise<Loaded> | undefined;

export type Source = 'cache' | 'loaded';

export function cacheAgeMs(now = Date.now()): number | undefined {
  return cache ? now - cache.loadedAt : undefined;
}

// 同時に複数の呼び出しが来ても、読み込みは1回にまとめる（Graph・SQL への負荷と 429 を避ける）
export async function load(tokens: { fabric: string; sql: string }, { force = false } = {}): Promise<{ data: Loaded; source: Source }> {
  const now = Date.now();
  if (!force && cache && now - cache.loadedAt < TTL_MS) return { data: cache, source: 'cache' };
  if (!inflight) {
    inflight = (async () => {
      const t0 = Date.now();
      const coordinates = await resolveCoordinates(tokens.fabric);
      const base = await readBaseData(tokens.sql, coordinates);
      const prepared = prepare(base);
      const reconciliation = reconcile(prepared);
      cache = { coordinates, base, prepared, reconciliation, loadedAt: Date.now(), loadMs: Date.now() - t0 };
      return cache;
    })().finally(() => {
      inflight = undefined;
    });
  }
  return { data: await inflight, source: 'loaded' };
}
