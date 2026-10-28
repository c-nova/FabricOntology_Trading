import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DEBOUNCE_MS } from '@/hooks/use-simulation';
import type { LoadModelOutput } from '@/lib/types';
import { stubApi } from '@/test/fixtures';

import { Simulator } from './Simulator';

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// 非同期の応答とデバウンスのタイマーを、まとめて進める
const settle = async (ms = DEBOUNCE_MS) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

const heading = () => screen.queryByRole('heading', { level: 1, name: 'What-if シミュレータ' });

describe('Simulator の状態', () => {
  it('読み込み中は、条件を出さず、時間がかかる旨と骨組みを出す', async () => {
    const api = stubApi({ loadModel: () => new Promise<LoadModelOutput>(() => {}) });
    render(<Simulator api={api} />);
    expect(heading()).toBeInTheDocument();
    expect(screen.getByText(/最大 1 分/)).toBeInTheDocument();
    expect(screen.queryByRole('slider')).toBeNull();
    await settle(3000);
    expect(screen.getByText(/3 秒経過/)).toBeInTheDocument();
  });

  it('容量が止まっているときは、行動を示すエラーを出し、読み込み中のまま止めない', async () => {
    const api = stubApi({ loadModel: async () => ({ ok: false, code: 'CAPACITY', message: 'x' }) as LoadModelOutput });
    render(<Simulator api={api} />);
    await settle(0);
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText('Fabric の容量が停止しています')).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: '再試行' })).toBeEnabled();
    expect(screen.queryByRole('slider')).toBeNull();
  });

  it('再試行を押すと、もう一度読み込んで画面が出る', async () => {
    const loadModel = vi
      .fn<() => Promise<LoadModelOutput>>()
      .mockResolvedValueOnce({ ok: false, code: 'UPSTREAM', message: 'x' } as LoadModelOutput)
      .mockImplementation(stubApi().loadModel);
    const api = stubApi({ loadModel });
    render(<Simulator api={api} />);
    await settle(0);
    fireEvent.click(screen.getByRole('button', { name: '再試行' }));
    await settle();
    expect(loadModel).toHaveBeenCalledTimes(2);
    expect(screen.getAllByRole('slider').length).toBeGreaterThan(0);
  });
});

describe('Simulator の操作', () => {
  // モデルの読み込み（即時）の後に、条件の計算（デバウンス）が始まる。両方を進める。
  async function ready() {
    const api = stubApi();
    render(<Simulator api={api} />);
    await settle(0);
    await settle();
    return api;
  }

  it('準備ができると、為替とイベントごとのスライダー、結果、経路が出る', async () => {
    const api = await ready();
    // 為替 1 + イベント 3
    expect(within(screen.getByRole('complementary', { name: '条件' })).getAllByRole('slider')).toHaveLength(4);
    expect(screen.getByRole('region', { name: '全額連結' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '持分管理' })).toBeInTheDocument();
    expect(api.calls.eventPaths).toEqual(['MTL_NEG']); // 基準の影響額の絶対値が最大のイベント
    expect(screen.getByText(/影響額の件数が一致しています（84 件）/)).toBeInTheDocument();
  });

  it('実績のままのときは、差が 0 で「変化なし」と出る', async () => {
    await ready();
    const full = screen.getByRole('region', { name: '全額連結' });
    expect(within(full).getByText('0円')).toBeInTheDocument();
    expect(within(full).getByText('変化なし')).toBeInTheDocument();
  });

  it('将来の予測に切り替えても、過去の条件は保持する', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '円高 10%' }));
    await settle();
    fireEvent.click(screen.getByRole('radio', { name: '将来の予測' }));
    await settle();
    await settle();
    expect(screen.getByRole('img', { name: /四半期の EBITDA/ })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: '追加する影響の大きさ' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: '過去の実績' }));
    expect(screen.getByText('円高 10%', { selector: 'output' })).toBeInTheDocument();
  });

  it('ワンタッチ「円高 10%」で、為替が −10% になり、結果が減少と符号つきで出る', async () => {
    const api = await ready();
    fireEvent.click(screen.getByRole('button', { name: '円高 10%' }));
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({ fx: { currency: 'USD', factor: '0.90' } });
    const full = screen.getByRole('region', { name: '全額連結' });
    expect(within(full).getByText('減少')).toBeInTheDocument();
    expect(within(full).getByText('−22.7億円')).toBeInTheDocument();
    expect(within(full).getByText(/−2,274,575,575\.77 円/)).toBeInTheDocument();
  });

  it('ワンタッチ「円安 10%」で、増加と + 符号つきで出る（増えたときも、色だけに頼らない）', async () => {
    const api = await ready();
    fireEvent.click(screen.getByRole('button', { name: '円安 10%' }));
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({ fx: { currency: 'USD', factor: '1.10' } });
    const full = screen.getByRole('region', { name: '全額連結' });
    expect(within(full).getByText('増加')).toBeInTheDocument();
    expect(within(full).getByText('+12.4億円')).toBeInTheDocument();
    expect(within(full).getByText(/\+1,242,600,267\.16 円/)).toBeInTheDocument();
  });

  it('再描画の前に 2 つのワンタッチを続けて押しても、両方の条件が残る（後の操作が前の操作を消さない）', async () => {
    const api = await ready();
    // act の中で 2 回続けて押す。間に再描画が入らないので、古い状態を見て上書きすると、片方が消える。
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: '食品損失を 50% 軽減' }));
      fireEvent.click(screen.getByRole('button', { name: '円高 10%' }));
    });
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({ fx: { currency: 'USD', factor: '0.90' }, events: { FOD_NEG: '0.50' } });
    expect(screen.getByRole('slider', { name: /コールドチェーンの劣化/ })).toHaveValue('50');
    expect(screen.getByRole('slider', { name: '為替（USD / 円）' })).toHaveValue('-10');
  });

  it('スライダーを動かすと、その値がシナリオとして送られる（デバウンスの後に 1 回）', async () => {
    const api = await ready();
    const before = api.calls.simulate.length;
    const fx = screen.getByRole('slider', { name: '為替（USD / 円）' });
    fireEvent.change(fx, { target: { value: '-7' } });
    fireEvent.change(fx, { target: { value: '-8' } });
    await settle();
    expect(api.calls.simulate.length).toBe(before + 1);
    expect(api.calls.simulate.at(-1)).toEqual({ fx: { currency: 'USD', factor: '0.92' } });
  });

  it('イベントのスライダーは、倍率として送られる。100% に戻すと送られなくなる', async () => {
    const api = await ready();
    const slider = screen.getByRole('slider', { name: /コールドチェーンの劣化/ });
    fireEvent.change(slider, { target: { value: '50' } });
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({ events: { FOD_NEG: '0.50' } });
    fireEvent.change(slider, { target: { value: '100' } });
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({});
  });

  it('スライダーは、読み上げ用の値の説明を持つ', async () => {
    await ready();
    const fx = screen.getByRole('slider', { name: '為替（USD / 円）' });
    expect(fx).toHaveAttribute('aria-valuetext', '実績のまま');
    fireEvent.change(fx, { target: { value: '10' } });
    expect(fx).toHaveAttribute('aria-valuetext', '円安 10%');
  });

  it('「実績に戻す」は、変更があるときだけ押せて、押すと全部戻る', async () => {
    const api = await ready();
    const reset = screen.getByRole('button', { name: '実績に戻す' });
    expect(reset).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '食品損失を 50% 軽減' }));
    await settle();
    expect(screen.getByRole('button', { name: '実績に戻す' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '実績に戻す' }));
    await settle();
    expect(api.calls.simulate.at(-1)).toEqual({});
    expect(screen.getByRole('button', { name: '実績に戻す' })).toBeDisabled();
  });

  it('指標を切り替えると、選んだ指標の内訳に変わる（両方の結果は常に出ている）', async () => {
    await ready();
    expect(screen.getByRole('radio', { name: '全額連結' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: '持分管理' }));
    expect(screen.getByRole('radio', { name: '持分管理' })).toBeChecked();
    expect(screen.getByRole('region', { name: '全額連結' })).toBeInTheDocument();
  });

  it('計算が失敗したら、直近の結果を残したまま、エラーを出す', async () => {
    const api = stubApi();
    let fail = false;
    const base = api.simulate;
    api.simulate = async (s) => (fail ? ({ ok: false, code: 'UPSTREAM', message: 'x' } as const) : base(s));
    render(<Simulator api={api} />);
    await settle(0);
    await settle();
    fail = true;
    fireEvent.click(screen.getByRole('button', { name: '円高 10%' }));
    await settle();
    expect(screen.getByRole('alert')).toHaveTextContent('データの取得に失敗しました');
    expect(screen.getByRole('region', { name: '全額連結' })).toBeInTheDocument();
  });

  it('経路の取得が失敗しても、他の画面は使えて、再試行できる', async () => {
    const api = stubApi({ eventPaths: async () => ({ ok: false, code: 'RATE_LIMIT', message: 'x' }) });
    render(<Simulator api={api} />);
    await settle(0);
    await settle();
    expect(screen.getAllByRole('slider').length).toBeGreaterThan(0);
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText('アクセスが集中しています')).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: '再試行' })).toBeEnabled();
  });

  it('グラフと Lakehouse の件数が違えば、不一致として隠さずに出す', async () => {
    const api = stubApi();
    const base = api.eventPaths;
    api.eventPaths = async (id) => {
      const out = await base(id);
      return out.ok ? { ...out, paths: out.paths.slice(0, 80) } : out;
    };
    render(<Simulator api={api} />);
    await settle(0);
    await settle();
    expect(screen.getByText(/一致していません/)).toBeInTheDocument();
  });

  it('イベントを選び直すと、そのイベントの経路を取りに行く（取得済みは再取得しない）', async () => {
    const api = await ready();
    const select = screen.getByLabelText('イベントを選ぶ');
    fireEvent.change(select, { target: { value: 'FOD_NEG' } });
    await settle(0);
    fireEvent.change(select, { target: { value: 'MTL_NEG' } });
    await settle(0);
    expect(api.calls.eventPaths).toEqual(['MTL_NEG', 'FOD_NEG']);
  });

  it('この画面が証明しないこと（架空データ・因果ではない等）を、常に出す', async () => {
    await ready();
    expect(screen.getByText('架空のデータです')).toBeInTheDocument();
    expect(screen.getByText(/因果関係を証明するものではなく/)).toBeInTheDocument();
    expect(screen.getByText(/ヘッジ、価格への転嫁、取引量の変化は反映していません/)).toBeInTheDocument();
  });
});
