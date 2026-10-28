import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Api } from '@/lib/api';
import { INITIAL_STATE, setFx, type ScenarioState } from '@/lib/scenario';
import type { EventPathsOutput, LoadModelOutput, SimulateOutput } from '@/lib/types';

import { useEventPaths } from './use-event-paths';
import { useModel } from './use-model';
import { DEBOUNCE_MS, useSimulation } from './use-simulation';

// 手で解決できる Promise。応答の順序を、テストが決める。
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const resultOf = (tag: string) => ({ tag }) as unknown as Extract<SimulateOutput, { ok: true }>['result'];
const okSim = (tag: string): SimulateOutput => ({ ok: true, source: 'cache', result: resultOf(tag) }) as SimulateOutput;
const fakeApi = (over: Partial<Api>): Api => ({
  loadModel: vi.fn(),
  simulate: vi.fn(),
  eventPaths: vi.fn(),
  ...over,
});

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('useSimulation', () => {
  it('条件を連続で動かしても、デバウンスの後に 1 回だけ計算する', async () => {
    const simulate = vi.fn(async () => okSim('x'));
    const api = fakeApi({ simulate });
    let state: ScenarioState = INITIAL_STATE;
    const { rerender } = renderHook(({ s }) => useSimulation(s, true, api), { initialProps: { s: state } });

    for (const p of [-5, -6, -7, -8]) {
      state = setFx(state, p);
      rerender({ s: state });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(DEBOUNCE_MS - 50);
      });
    }
    expect(simulate).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(simulate).toHaveBeenCalledTimes(1);
    expect(simulate).toHaveBeenCalledWith(expect.objectContaining({ fx: { currency: 'USD', factor: '0.92' } }));
  });

  it('応答が逆順に返っても、最後の条件の結果だけを採用する', async () => {
    const first = deferred<SimulateOutput>();
    const second = deferred<SimulateOutput>();
    const queue = [first, second];
    const simulate = vi.fn(() => queue.shift()!.promise);
    const api = fakeApi({ simulate });

    const a = setFx(INITIAL_STATE, -5);
    const b = setFx(INITIAL_STATE, -10);
    const { result, rerender } = renderHook(({ s }) => useSimulation(s, true, api), { initialProps: { s: a } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(simulate).toHaveBeenCalledTimes(1);

    rerender({ s: b });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(simulate).toHaveBeenCalledTimes(2);

    // 新しい条件(b)の応答が先に返り、古い条件(a)の応答が後から返る
    await act(async () => {
      second.resolve(okSim('B'));
    });
    await act(async () => {
      first.resolve(okSim('A'));
    });
    expect((result.current.result as unknown as { tag: string }).tag).toBe('B');
    expect(result.current.pending).toBe(false);
  });

  it('計算中は直近の結果を残し、pending を立てる（画面を空にしない）', async () => {
    const first = deferred<SimulateOutput>();
    const second = deferred<SimulateOutput>();
    const queue = [first, second];
    const api = fakeApi({ simulate: vi.fn(() => queue.shift()!.promise) });
    const { result, rerender } = renderHook(({ s }) => useSimulation(s, true, api), { initialProps: { s: INITIAL_STATE } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
      first.resolve(okSim('BASE'));
    });
    expect((result.current.result as unknown as { tag: string }).tag).toBe('BASE');

    rerender({ s: setFx(INITIAL_STATE, 5) });
    expect(result.current.pending).toBe(true);
    expect((result.current.result as unknown as { tag: string }).tag).toBe('BASE');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
      second.resolve(okSim('NEW'));
    });
    expect((result.current.result as unknown as { tag: string }).tag).toBe('NEW');
    expect(result.current.pending).toBe(false);
  });

  it('失敗したら error を出し、次の成功で消す。失敗しても直近の結果は残す', async () => {
    const outs: Array<() => Promise<SimulateOutput>> = [
      async () => okSim('OK1'),
      async () => ({ ok: false, code: 'UPSTREAM', message: 'x' }) as SimulateOutput,
      async () => okSim('OK2'),
    ];
    const api = fakeApi({ simulate: vi.fn(() => outs.shift()!()) });
    const { result, rerender } = renderHook(({ s }) => useSimulation(s, true, api), { initialProps: { s: INITIAL_STATE } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(result.current.error).toBeUndefined();

    rerender({ s: setFx(INITIAL_STATE, 1) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(result.current.error?.title).toContain('取得に失敗');
    expect((result.current.result as unknown as { tag: string }).tag).toBe('OK1');

    rerender({ s: setFx(INITIAL_STATE, 2) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(result.current.error).toBeUndefined();
    expect((result.current.result as unknown as { tag: string }).tag).toBe('OK2');
  });

  it('条件を変えた直後は、前の条件の失敗を出さない（計算中として扱う）', async () => {
    const second = deferred<SimulateOutput>();
    const queue: Array<() => Promise<SimulateOutput>> = [
      async () => ({ ok: false, code: 'UPSTREAM', message: 'x' }) as SimulateOutput,
      () => second.promise,
    ];
    const api = fakeApi({ simulate: vi.fn(() => queue.shift()!()) });
    const { result, rerender } = renderHook(({ s }) => useSimulation(s, true, api), { initialProps: { s: INITIAL_STATE } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(result.current.error).toBeDefined();
    expect(result.current.pending).toBe(false);

    // 条件を変えた直後（新しい条件の結果はまだ無い）
    rerender({ s: setFx(INITIAL_STATE, 3) });
    expect(result.current.error).toBeUndefined();
    expect(result.current.pending).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
      second.resolve(okSim('OK'));
    });
    expect(result.current.error).toBeUndefined();
    expect(result.current.pending).toBe(false);
  });

  it('通信の例外も、画面に出せる形にする', async () => {
    const boom = new Error('POST https://internal.example/secret failed');
    boom.name = 'NetworkError';
    const api = fakeApi({ simulate: vi.fn(async () => Promise.reject(boom)) });
    const { result } = renderHook(() => useSimulation(INITIAL_STATE, true, api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    });
    expect(result.current.error?.title).toContain('接続');
    expect(JSON.stringify(result.current.error)).not.toContain('internal.example');
    expect(result.current.pending).toBe(false);
  });

  it('モデルが読めるまでは、呼ばない', async () => {
    const simulate = vi.fn(async () => okSim('x'));
    const api = fakeApi({ simulate });
    renderHook(() => useSimulation(INITIAL_STATE, false, api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 4);
    });
    expect(simulate).not.toHaveBeenCalled();
  });
});

describe('useModel', () => {
  const okModel = { ok: true, source: 'loaded', model: { tag: 'M' } } as unknown as LoadModelOutput;

  it('読み込み中は経過秒数を進め、成功したら ready にする', async () => {
    const d = deferred<LoadModelOutput>();
    const api = fakeApi({ loadModel: vi.fn(() => d.promise) });
    const { result } = renderHook(() => useModel(api));
    expect(result.current.state).toEqual({ phase: 'loading', elapsedSec: 0 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current.state).toEqual({ phase: 'loading', elapsedSec: 3 });
    await act(async () => {
      d.resolve(okModel);
    });
    expect(result.current.state.phase).toBe('ready');
  });

  it('失敗したら案内を出し、自動では再試行しない。押すと再試行する', async () => {
    const loadModel = vi
      .fn<Api['loadModel']>()
      .mockResolvedValueOnce({ ok: false, code: 'CAPACITY', message: 'x' } as LoadModelOutput)
      .mockResolvedValueOnce(okModel);
    const api = fakeApi({ loadModel });
    const { result } = renderHook(() => useModel(api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('error');
    if (result.current.state.phase === 'error') expect(result.current.state.error.needsOperator).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(loadModel).toHaveBeenCalledTimes(1);

    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(loadModel).toHaveBeenCalledTimes(2);
    expect(result.current.state.phase).toBe('ready');
  });

  it('時間切れの例外は、時間がかかっている旨の案内にする', async () => {
    const e = new Error('x');
    e.name = 'TimeoutError';
    const api = fakeApi({ loadModel: vi.fn(async () => Promise.reject(e)) });
    const { result } = renderHook(() => useModel(api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('error');
    if (result.current.state.phase === 'error') expect(result.current.state.error.title).toContain('時間');
  });
});

describe('useEventPaths', () => {
  const okPaths = (n: number) => ({ ok: true, eventId: 'E', paths: Array.from({ length: n }, (_, i) => ({ effectId: `E${i}` })) }) as unknown as EventPathsOutput;

  it('同じイベントは、2 回目からキャッシュを使う', async () => {
    const eventPaths = vi.fn(async (id: string) => okPaths(id === 'A' ? 2 : 3));
    const api = fakeApi({ eventPaths });
    const { result, rerender } = renderHook(({ id }) => useEventPaths(id, api), { initialProps: { id: 'A' as string | undefined } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('ready');

    rerender({ id: 'B' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    rerender({ id: 'A' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(eventPaths).toHaveBeenCalledTimes(2);
    expect(result.current.state.phase === 'ready' && result.current.state.paths.length).toBe(2);
  });

  it('イベントを切り替えたら、前のイベントの遅れた応答は捨てる', async () => {
    const a = deferred<EventPathsOutput>();
    const b = deferred<EventPathsOutput>();
    const eventPaths = vi.fn((id: string) => (id === 'A' ? a.promise : b.promise));
    const api = fakeApi({ eventPaths });
    const { result, rerender } = renderHook(({ id }) => useEventPaths(id, api), { initialProps: { id: 'A' as string | undefined } });
    rerender({ id: 'B' });
    await act(async () => {
      b.resolve(okPaths(3));
    });
    await act(async () => {
      a.resolve(okPaths(2));
    });
    expect(result.current.state.phase === 'ready' && result.current.state.eventId).toBe('B');
    expect(result.current.state.phase === 'ready' && result.current.state.paths.length).toBe(3);
  });

  it('失敗したら、再試行でもう一度取りに行く（失敗はキャッシュしない）', async () => {
    const eventPaths = vi
      .fn<Api['eventPaths']>()
      .mockResolvedValueOnce({ ok: false, code: 'RATE_LIMIT', message: 'x' } as EventPathsOutput)
      .mockResolvedValueOnce(okPaths(1));
    const api = fakeApi({ eventPaths });
    const { result } = renderHook(() => useEventPaths('A', api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('error');
    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('ready');
    expect(eventPaths).toHaveBeenCalledTimes(2);
  });

  it('イベントが未選択のときは、何も取りに行かない', async () => {
    const eventPaths = vi.fn();
    const api = fakeApi({ eventPaths });
    const { result } = renderHook(() => useEventPaths(undefined, api));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.phase).toBe('idle');
    expect(eventPaths).not.toHaveBeenCalled();
  });
});
