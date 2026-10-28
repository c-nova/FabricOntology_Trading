import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FORECAST_GRAPH, FORECAST_LOADED, FORECAST_RESULT, MODEL, stubApi } from '@/test/fixtures';

import { FuturePanel } from './FuturePanel';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function settle() {
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
}

const svg = () => screen.getByRole('img', { name: /四半期の EBITDA/ });

describe('FuturePanel', () => {
  it('実績から予測への線と、業種別の積み上げ棒を出し、イベントを仮定した線を重ねる', async () => {
    const simulateForecast = vi.fn(async () => ({ ok: true as const, result: FORECAST_RESULT, graph: FORECAST_GRAPH }));
    render(<FuturePanel api={stubApi({ simulateForecast })} events={MODEL.events} />);
    await settle();
    expect(simulateForecast).toHaveBeenCalledWith({ eventId: 'FOD_NEG', eventDate: '2026-11-15', scale: 1 });
    expect(screen.getByText('基準予測')).toBeInTheDocument();
    // 結果のタイルと、グラフの凡例・表見出しの両方に出る
    expect(screen.getAllByText('イベント想定後').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('予測との差')).toBeInTheDocument();
    const chart = svg();
    expect(chart.querySelector('[data-series="baseline"]')).not.toBeNull();
    expect(chart.querySelector('[data-series="scenario"]')).not.toBeNull();
    expect(chart.querySelectorAll('[data-bar]')).toHaveLength(5 * 4);
    expect(screen.getByText(/二重計上の可能性/)).toBeInTheDocument();
    expect(screen.getByText(/期間内 84 件/)).toBeInTheDocument();
    expect(screen.getByText('参照した過去のOntology経路')).toBeInTheDocument();
  });

  it('差が1億円未満でも、タイルは万円にせず億円で出す（グラフ・表と単位をそろえる）', async () => {
    const small = { ...FORECAST_RESULT, scenarioFull: '11396487651.87', deltaFull: '-93049180.35' };
    const simulateForecast = vi.fn(async () => ({ ok: true as const, result: small, graph: FORECAST_GRAPH }));
    render(<FuturePanel api={stubApi({ simulateForecast })} events={MODEL.events} />);
    await settle();
    expect(screen.getByText('−0.93億円')).toBeInTheDocument();
    expect(screen.getByText('113.96億円')).toBeInTheDocument();
    expect(screen.queryByText(/万円/)).toBeNull();
  });

  it('計算の結果を待つ間も、予測までの線と棒は先に出る（イベントの線だけが後から重なる）', async () => {
    const simulateForecast = vi.fn(() => new Promise<never>(() => {}));
    render(<FuturePanel api={stubApi({ simulateForecast })} events={MODEL.events} />);
    await act(async () => { await Promise.resolve(); });
    const chart = svg();
    expect(chart.querySelector('[data-series="baseline"]')).not.toBeNull();
    expect(chart.querySelector('[data-series="scenario"]')).toBeNull();
    expect(chart.querySelectorAll('[data-bar]')).toHaveLength(5 * 4);
  });

  it('不正な発生日は送らず、有効な日付に直すと再計算する', async () => {
    const simulateForecast = vi.fn(async () => ({ ok: true as const, result: FORECAST_RESULT, graph: FORECAST_GRAPH }));
    render(<FuturePanel api={stubApi({ simulateForecast })} events={MODEL.events} />);
    await settle();
    fireEvent.change(screen.getByLabelText('仮の発生日'), { target: { value: '2027-01-01' } });
    await settle();
    expect(screen.getByRole('alert')).toHaveTextContent('予測期間内の日付');
    expect(simulateForecast).toHaveBeenCalledTimes(1);
    expect(svg().querySelector('[data-series="scenario"]')).toBeNull();
    fireEvent.change(screen.getByLabelText('仮の発生日'), { target: { value: '2026-12-31' } });
    await settle();
    expect(simulateForecast).toHaveBeenLastCalledWith({ eventId: 'FOD_NEG', eventDate: '2026-12-31', scale: 1 });
  });

  it('保存された予測を読めないときは、行動を示すエラーと再試行を出す', async () => {
    const api = stubApi({ loadForecast: async () => ({ ok: false, code: 'NOT_FOUND', message: 'missing' }) });
    render(<FuturePanel api={api} events={MODEL.events} />);
    await settle();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('必要な項目が見つかりません');
    expect(within(alert).getByRole('button', { name: '再試行' })).toBeInTheDocument();
  });

  it('予測の業種別が無い保存結果では、その旨を注記し、予測の棒は内訳なしで出す', async () => {
    const api = stubApi({ loadForecast: async () => ({ ...FORECAST_LOADED, forecastBySector: null }) });
    render(<FuturePanel api={api} events={MODEL.events} />);
    await settle();
    expect(screen.getByText(/会社別の値が無いため/)).toBeInTheDocument();
    const chart = svg();
    expect(chart.querySelectorAll('[data-bar="unknown"]')).toHaveLength(1);
    expect(chart.querySelectorAll('[data-bar]:not([data-bar="unknown"])')).toHaveLength(4 * 4);
  });
});
