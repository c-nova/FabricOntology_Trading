import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { buildChartQuarters } from '@/lib/quarters';
import { FORECAST_LOADED, FORECAST_RESULT } from '@/test/fixtures';

import { ForecastChart } from './ForecastChart';

afterEach(cleanup);

const withScenario = () => buildChartQuarters(FORECAST_LOADED, FORECAST_RESULT);
const baselineOnly = () => buildChartQuarters(FORECAST_LOADED);
const svgOf = () => screen.getByRole('img', { name: /四半期の EBITDA/ });
const num = (el: Element | null, attr: string) => Number(el?.getAttribute(attr));

describe('ForecastChart', () => {
  it('5つの四半期に、実績の点4つと予測の点1つ、業種4色の積み上げ棒を描く', () => {
    const { container } = render(<ForecastChart quarters={withScenario()} pending={false} />);
    const svg = svgOf();
    expect(svg.querySelectorAll('[data-point="baseline"]')).toHaveLength(5);
    expect(svg.querySelectorAll('[data-point="scenario"]')).toHaveLength(1);
    expect(svg.querySelectorAll('[data-quarter]')).toHaveLength(5);
    for (const code of ['metals', 'energy', 'foods', 'finance']) {
      expect(svg.querySelectorAll(`[data-bar="${code}"]`)).toHaveLength(5);
    }
    expect(svg.querySelector('[data-segment="forecast"]')).not.toBeNull();
    expect(container.querySelector('[aria-busy="false"]')).not.toBeNull();
  });

  it('値が大きい四半期の点ほど上に来る。イベントで下がる想定は、基準の点より下に来る', () => {
    render(<ForecastChart quarters={withScenario()} pending={false} />);
    const points = [...svgOf().querySelectorAll('[data-point="baseline"]')].map((p) => num(p, 'cy'));
    // FY26 Q1(115.9) < FY26 Q2(103.6) の位置関係: 値が大きいほど cy は小さい
    expect(points[0]!).toBeLessThan(points[1]!);
    expect(points[3]!).toBeLessThan(points[1]!);
    const scenario = svgOf().querySelector('[data-point="scenario"]')!;
    const transform = scenario.getAttribute('transform')!;
    const scenarioY = Number(/rotate\(45 [\d.]+ ([\d.]+)\)/.exec(transform)![1]);
    expect(scenarioY).toBeGreaterThan(points[4]!);
  });

  it('積み上げ棒は、下から金属・エネルギー・食品・金融の順で、合計の高さに一致する', () => {
    render(<ForecastChart quarters={baselineOnly()} pending={false} />);
    const quarter = svgOf().querySelector('[data-quarter="2026-07"]')!;
    const bars = [...quarter.querySelectorAll('[data-bar]')];
    expect(bars.map((b) => b.getAttribute('data-bar'))).toEqual(['metals', 'energy', 'foods', 'finance']);
    const bottoms = bars.map((b) => num(b, 'y') + num(b, 'height'));
    const tops = bars.map((b) => num(b, 'y'));
    for (let i = 1; i < bars.length; i += 1) expect(bottoms[i]!).toBeCloseTo(tops[i - 1]!, 6);
  });

  it('イベントを仮定していないときは、イベントの線・凡例・差の括弧を出さない', () => {
    render(<ForecastChart quarters={baselineOnly()} pending={false} />);
    const svg = svgOf();
    expect(svg.querySelector('[data-series="scenario"]')).toBeNull();
    expect(svg.querySelector('[data-bracket]')).toBeNull();
    expect(screen.queryByText('線：イベント想定後')).toBeNull();
  });

  it('基準とイベント想定後の差を、符号つきで線の脇に出す', () => {
    render(<ForecastChart quarters={withScenario()} pending={false} />);
    const bracket = svgOf().querySelector('[data-bracket]')!;
    expect(bracket).not.toBeNull();
    expect(bracket.textContent).toBe('−1.14');
  });

  it('凡例に、線・棒の意味と、左軸・右軸を示す', () => {
    render(<ForecastChart quarters={withScenario()} pending={false} />);
    const legend = screen.getByRole('list', { name: '凡例' });
    expect(within(legend).getByText(/実績・予測の合計（左軸/)).toBeInTheDocument();
    expect(within(legend).getByText('線：イベント想定後')).toBeInTheDocument();
    expect(within(legend).getByText(/業種別（右軸）/)).toBeInTheDocument();
    for (const name of ['金属', 'エネルギー', '食品', '金融']) expect(within(legend).getByText(name)).toBeInTheDocument();
    expect(screen.getByText(/線の軸（左）は 0 からではなく、100〜120 億円/)).toBeInTheDocument();
  });

  it('軸ラベルは、折れ線と棒で別々に出す。左軸の目盛りは、棒の高さの範囲を避ける', () => {
    render(<ForecastChart quarters={withScenario()} pending={false} />);
    const labels = [...svgOf().querySelectorAll('text')].map((t) => t.textContent);
    for (const left of ['105', '110', '115', '120']) expect(labels).toContain(left);
    // 100 は、棒の高さの範囲に入るため、左軸には出さない（右軸の「100」は別に出る）
    expect(labels.filter((t) => t === '100')).toHaveLength(1);
    for (const right of ['0', '50', '100', '150']) expect(labels).toContain(right);
    expect(screen.getByText(/線の軸（左）は 0 からではなく、100〜120 億円/)).toBeInTheDocument();
  });

  it('数値表に、全四半期の合計・想定後・差・業種別が億円で並ぶ', () => {
    render(<ForecastChart quarters={withScenario()} pending={false} />);
    const table = screen.getByRole('table', { name: /四半期ごとの EBITDA/ });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(1 + 5);
    const last = within(rows[5]!).getAllByRole('cell').map((c) => c.textContent);
    // 実績・予測 / イベント想定後 / 差 / 金属 / エネルギー / 食品 / 金融（億円）
    expect(last).toEqual(['114.90', '113.75', '−1.14', '34.55', '34.68', '22.82', '22.84']);
    expect(within(rows[5]!).getByRole('rowheader')).toHaveTextContent('FY27 Q1');
    expect(within(rows[5]!).getByRole('rowheader')).toHaveTextContent('予測');
    const first = within(rows[1]!).getAllByRole('cell').map((c) => c.textContent);
    expect(first.slice(0, 3)).toEqual(['115.93', '—', '—']);
  });

  it('計算中は薄く表示し、読み上げにも計算中と伝える', () => {
    const { container } = render(<ForecastChart quarters={withScenario()} pending />);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('四半期が無いときは、何も描かない', () => {
    const { container } = render(<ForecastChart quarters={[]} pending={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('数値が全て同じで差が無くても、線を描ける（軸が潰れない）', () => {
    const flat = baselineOnly().map((q) => ({ ...q, total: 100, sectors: null }));
    render(<ForecastChart quarters={flat} pending={false} />);
    const ys = [...svgOf().querySelectorAll('[data-point="baseline"]')].map((p) => num(p, 'cy'));
    expect(new Set(ys).size).toBe(1);
    expect(Number.isFinite(ys[0])).toBe(true);
  });
});
