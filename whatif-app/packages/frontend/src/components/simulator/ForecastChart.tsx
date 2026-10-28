import { useEffect, useId, useRef, useState, type RefObject } from 'react';

import { BAR_BAND, LINE_BAND, barDomain, barWidth, isCompact, lineDomain, plotOf, slotCenter, ticksOf, yOf } from '@/lib/chart';
import { formatOkuNumber } from '@/lib/format';
import { axisLabels, sectorsOf, type ChartQuarter } from '@/lib/quarters';
import { cn } from '@/lib/utils';

import { sectorLabel } from './labels';

// 色は global.css のトークン。Tailwind が見つけられるよう、クラス名は文字列のまま書く（組み立てない）。
const SECTOR_FILL: Record<string, string> = {
  metals: 'fill-chart-metals',
  energy: 'fill-chart-energy',
  foods: 'fill-chart-foods',
  finance: 'fill-chart-finance',
};
const SECTOR_BG: Record<string, string> = {
  metals: 'bg-chart-metals',
  energy: 'bg-chart-energy',
  foods: 'bg-chart-foods',
  finance: 'bg-chart-finance',
};
const fillOf = (code: string): string => SECTOR_FILL[code] ?? 'fill-chart-other';
const bgOf = (code: string): string => SECTOR_BG[code] ?? 'bg-chart-other';

const DEFAULT_WIDTH = 720;

// 描く幅は、入れ物の幅に合わせる（文字の大きさを保つため、縮小表示にしない）。
// 測れない環境（テストなど）では、既定の幅で描く。
function useWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

const pathOf = (points: readonly (readonly [number, number])[]): string =>
  points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

const sum = (q: ChartQuarter): number => (q.sectors ? q.sectors.reduce((a, s) => a + s.value, 0) : q.total);

function describe(q: ChartQuarter): string {
  const head = `${q.fiscal}（${q.months}${q.kind === 'forecast' ? '・予測' : ''}${q.partial ? '・一部の日のみ' : ''}）`;
  const parts = [`${q.kind === 'forecast' ? '予測' : '実績'} ${formatOkuNumber(q.total, 2)}億円`];
  if (q.scenario !== undefined) {
    parts.push(`イベント想定後 ${formatOkuNumber(q.scenario, 2)}億円（差 ${formatOkuNumber(q.scenario - q.total, 2, true)}億円）`);
  }
  if (q.sectors) parts.push(`内訳 ${q.sectors.map((s) => `${sectorLabel(s.code)} ${formatOkuNumber(s.value, 2)}`).join('、')}`);
  return `${head}${parts.join('、')}`;
}

function Legend({ sectors, hasScenario }: { sectors: readonly string[]; hasScenario: boolean }) {
  return (
    <ul aria-label="凡例" className="flex flex-wrap items-center gap-x-500 gap-y-200 text-200 text-foreground">
      <li className="flex items-center gap-200">
        <svg aria-hidden width="30" height="12" viewBox="0 0 30 12">
          <line x1="0" x2="30" y1="6" y2="6" strokeWidth="2.25" className="stroke-foreground" />
          <circle cx="15" cy="6" r="3.5" strokeWidth="2" className="fill-card stroke-foreground" />
        </svg>
        <span>線：実績・予測の合計（左軸。破線は予測）</span>
      </li>
      {hasScenario && (
        <li className="flex items-center gap-200">
          <svg aria-hidden width="30" height="12" viewBox="0 0 30 12">
            <line x1="0" x2="30" y1="6" y2="6" strokeWidth="3" className="stroke-brand-foreground" />
            <rect x="11" y="2" width="8" height="8" transform="rotate(45 15 6)" strokeWidth="1.5" className="fill-brand-foreground stroke-card" />
          </svg>
          <span>線：イベント想定後</span>
        </li>
      )}
      <li className="flex flex-wrap items-center gap-x-300 gap-y-100">
        <span>棒：業種別（右軸）</span>
        {sectors.map((code) => (
          <span key={code} className="flex items-center gap-100">
            <span aria-hidden className={cn('inline-block h-200 w-200 rounded-sm opacity-70', bgOf(code))} />
            {sectorLabel(code)}
          </span>
        ))}
      </li>
    </ul>
  );
}

function DataTable({ quarters, sectors }: { quarters: readonly ChartQuarter[]; sectors: readonly string[] }) {
  const cell = 'px-300 py-200 text-right font-numeric tabular-nums';
  return (
    <details className="border-t border-border pt-300">
      <summary className="cursor-pointer text-300 font-semibold text-foreground">数値を表で見る</summary>
      <div className="mt-200 overflow-x-auto">
        <table className="w-full min-w-table border-collapse text-200">
          <caption className="sr-only">四半期ごとの EBITDA（全額連結、億円）</caption>
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th scope="col" className="px-300 py-200 text-left font-semibold">四半期</th>
              <th scope="col" className="px-300 py-200 text-right font-semibold">実績・予測</th>
              <th scope="col" className="px-300 py-200 text-right font-semibold">イベント想定後</th>
              <th scope="col" className="px-300 py-200 text-right font-semibold">差</th>
              {sectors.map((code) => (
                <th key={code} scope="col" className="px-300 py-200 text-right font-semibold">{sectorLabel(code)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {quarters.map((q) => (
              <tr key={q.key} className="border-b border-border last:border-b-0">
                <th scope="row" className="px-300 py-200 text-left font-medium text-foreground">
                  {q.fiscal}
                  <span className="block font-normal text-muted-foreground">
                    {q.months}
                    {q.kind === 'forecast' && '・予測'}
                    {q.partial && '・一部の日のみ'}
                  </span>
                </th>
                <td className={cn(cell, 'text-foreground')}>{formatOkuNumber(q.total, 2)}</td>
                <td className={cn(cell, 'text-foreground')}>{q.scenario === undefined ? '—' : formatOkuNumber(q.scenario, 2)}</td>
                <td className={cn(cell, q.scenario === undefined ? 'text-muted-foreground' : q.scenario < q.total ? 'text-destructive' : 'text-brand-foreground')}>
                  {q.scenario === undefined ? '—' : formatOkuNumber(q.scenario - q.total, 2, true)}
                </td>
                {sectors.map((code) => {
                  const value = q.sectors?.find((s) => s.code === code)?.value;
                  return (
                    <td key={code} className={cn(cell, 'text-muted-foreground')}>
                      {value === undefined ? '—' : formatOkuNumber(value, 2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/**
 * 四半期の EBITDA。手前に折れ線（実績→予測の合計と、イベントを仮定した後）、
 * 裏に業種別の積み上げ棒を置く。線は左軸（0から始めず、差が見える幅）、棒は右軸（0から）。
 */
export function ForecastChart({ quarters, pending }: { quarters: readonly ChartQuarter[]; pending: boolean }) {
  const [ref, width] = useWidth();
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const n = quarters.length;
  if (n === 0) return null;

  const plot = plotOf(width);
  const compact = isCompact(plot.width);
  const sectors = sectorsOf(quarters);
  const line = lineDomain(quarters.flatMap((q) => (q.scenario === undefined ? [q.total] : [q.total, q.scenario])));
  const bar = barDomain(Math.max(...quarters.map(sum)));
  const yl = (v: number) => yOf(v, line, LINE_BAND, plot);
  const yb = (v: number) => yOf(v, bar, BAR_BAND, plot);
  const xs = quarters.map((_, i) => slotCenter(i, n, plot));
  const slot = plot.w / n;
  const bw = barWidth(n, plot);
  const hatch = `${uid}-hatch`;

  const points = quarters.map((q, i) => [xs[i]!, yl(q.total)] as const);
  const actualPoints = points.filter((_, i) => quarters[i]!.kind === 'actual');
  // 左軸（線）の目盛りは、棒の高さの範囲を避ける。棒の中に左軸の数字があると、棒の高さを左軸で読み違えるため
  const highestBar = Math.min(...quarters.map((q) => yb(sum(q))));
  const lineTicks = ticksOf(line).filter((t) => yl(t) < highestBar - 14);
  const fi = quarters.findIndex((q) => q.kind === 'forecast');
  const last = actualPoints.at(-1);
  const forecastPoint = fi >= 0 ? points[fi] : undefined;
  const forecast = fi >= 0 ? quarters[fi] : undefined;
  const scenario = forecast?.scenario;
  const scenarioY = scenario === undefined ? undefined : yl(scenario);
  const scenarioIsHigher = scenario !== undefined && forecast !== undefined && scenario > forecast.total;
  const delta = scenario !== undefined && forecast !== undefined ? scenario - forecast.total : 0;
  const deltaLabel = formatOkuNumber(delta, 2, true);

  const summary =
    `${quarters.map((q) => `${q.fiscal} ${formatOkuNumber(q.total, 1)}`).join('、')}（億円）。` +
    (scenario !== undefined ? `予測期間にイベントを仮定すると ${formatOkuNumber(scenario, 1)} 億円。` : '');

  return (
    <div className={cn('space-y-300', pending && 'opacity-60')} aria-busy={pending}>
      <Legend sectors={sectors} hasScenario={scenario !== undefined} />
      {/* SVGは絶対配置にして、入れ物の幅の決定に関わらせない（中身の幅で入れ物が広がると、縮む側を測れなくなる） */}
      <div ref={ref} className="relative w-full min-w-0 overflow-hidden" style={{ aspectRatio: `${plot.width} / ${plot.height}` }}>
        <svg
          role="img"
          aria-labelledby={`${uid}-title ${uid}-desc`}
          viewBox={`0 0 ${plot.width} ${plot.height}`}
          preserveAspectRatio="xMidYMid meet"
          className="absolute inset-0 block h-full w-full"
        >
          <title id={`${uid}-title`}>四半期の EBITDA（線：合計、棒：業種別）</title>
          <desc id={`${uid}-desc`}>{summary}数値は下の表にあります。</desc>
          <defs>
            <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" strokeWidth="2.4" className="stroke-card" />
            </pattern>
          </defs>

          {fi >= 0 && (
            <g aria-hidden>
              <rect x={xs[fi]! - slot / 2} y={plot.y0} width={slot} height={plot.h} className="fill-muted" opacity={0.55} />
              <line x1={xs[fi]! - slot / 2} x2={xs[fi]! - slot / 2} y1={plot.y0} y2={plot.y1} strokeDasharray="3 4" className="stroke-input" />
              <text x={xs[fi]!} y={plot.y0 - 8} textAnchor="middle" className="fill-muted-foreground text-200">予測期間</text>
            </g>
          )}

          <g aria-hidden>
            {lineTicks.map((t) => (
              <g key={`l${t}`}>
                <line x1={plot.x0} x2={plot.x1} y1={yl(t)} y2={yl(t)} className="stroke-border" />
                <text x={plot.x0 - 8} y={yl(t) + 4} textAnchor="end" className="fill-muted-foreground font-numeric text-200 tabular-nums">{t}</text>
              </g>
            ))}
            <text x={plot.x0 - 8} y={yl(line.hi) - 14} textAnchor="end" className="fill-muted-foreground text-200">億円</text>
            <line x1={plot.x0} x2={plot.x1} y1={yb(0)} y2={yb(0)} className="stroke-input" />
            {ticksOf(bar).map((t) => (
              <g key={`b${t}`}>
                <line x1={plot.x1} x2={plot.x1 + 4} y1={yb(t)} y2={yb(t)} className="stroke-input" />
                <text x={plot.x1 + 8} y={yb(t) + 4} className="fill-muted-foreground font-numeric text-200 tabular-nums">{t}</text>
              </g>
            ))}
            <text x={plot.x1 + 8} y={yb(bar.hi) - 12} className="fill-muted-foreground text-200">億円</text>
          </g>

          {quarters.map((q, i) => {
            const isForecast = q.kind === 'forecast';
            let acc = 0;
            const x = xs[i]! - bw / 2;
            return (
              <g key={q.key} data-quarter={q.key} data-kind={q.kind}>
                <title>{describe(q)}</title>
                <rect x={xs[i]! - slot / 2} y={plot.y0} width={slot} height={plot.h} fill="transparent" />
                {q.sectors ? (
                  q.sectors.map((s) => {
                    const top = yb(acc + s.value);
                    const bottom = yb(acc);
                    acc += s.value;
                    return (
                      <rect
                        key={s.code}
                        data-bar={s.code}
                        x={x}
                        y={top}
                        width={bw}
                        height={Math.max(0, bottom - top)}
                        strokeWidth={1}
                        opacity={isForecast ? 0.5 : 0.62}
                        className={cn(fillOf(s.code), 'stroke-card')}
                      />
                    );
                  })
                ) : (
                  <rect data-bar="unknown" x={x} y={yb(q.total)} width={bw} height={Math.max(0, yb(0) - yb(q.total))} opacity={0.35} className="fill-muted-foreground" />
                )}
                {isForecast && (
                  <rect x={x} y={yb(sum(q))} width={bw} height={Math.max(0, yb(0) - yb(sum(q)))} fill={`url(#${hatch})`} strokeDasharray="4 3" strokeWidth={1.25} className="stroke-muted-foreground" />
                )}
              </g>
            );
          })}

          <g data-series="baseline">
            <path d={pathOf(actualPoints)} fill="none" strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" className="stroke-foreground" />
            {last && forecastPoint && (
              <path d={pathOf([last, forecastPoint])} data-segment="forecast" fill="none" strokeWidth={2.25} strokeDasharray="6 5" strokeLinecap="round" className="stroke-foreground" />
            )}
            {points.map(([x, y], i) => (
              <circle key={quarters[i]!.key} data-point="baseline" cx={x} cy={y} r={quarters[i]!.kind === 'forecast' ? 4.5 : 4} strokeWidth={2} className="fill-card stroke-foreground" />
            ))}
          </g>

          {scenario !== undefined && scenarioY !== undefined && forecastPoint && (
            <g data-series="scenario">
              {last && <path d={pathOf([last, [forecastPoint[0], scenarioY]])} fill="none" strokeWidth={3} strokeLinecap="round" className="stroke-brand-foreground" />}
              <rect
                data-point="scenario"
                x={forecastPoint[0] - 5}
                y={scenarioY - 5}
                width={10}
                height={10}
                transform={`rotate(45 ${forecastPoint[0]} ${scenarioY})`}
                strokeWidth={1.5}
                className="fill-brand-foreground stroke-card"
              />
              {Math.abs(scenarioY - forecastPoint[1]) > 1.5 && (
                <g data-bracket aria-hidden>
                  <path
                    d={`M${forecastPoint[0] + 12},${forecastPoint[1]} h4 V${scenarioY} h-4`}
                    fill="none"
                    strokeWidth={1.5}
                    className={delta < 0 ? 'stroke-destructive' : 'stroke-brand-foreground'}
                  />
                  {/* 右の余白に収まるときだけ、差の数値を出す（差は、上のタイルと表でも読める） */}
                  {forecastPoint[0] + 22 + deltaLabel.length * 7.5 <= plot.width - 4 && (
                    <text
                      x={forecastPoint[0] + 22}
                      y={(forecastPoint[1] + scenarioY) / 2 + 4}
                      paintOrder="stroke"
                      strokeWidth={4}
                      strokeLinejoin="round"
                      className={cn('stroke-card font-numeric text-200 font-semibold tabular-nums', delta < 0 ? 'fill-destructive' : 'fill-brand-foreground')}
                    >
                      {deltaLabel}
                    </text>
                  )}
                </g>
              )}
            </g>
          )}

          <g aria-hidden data-labels>
            {points.map(([x, y], i) => {
              const below = i === fi && scenarioIsHigher;
              return (
                <text
                  key={quarters[i]!.key}
                  x={x}
                  y={below ? y + 22 : y - 11}
                  textAnchor="middle"
                  paintOrder="stroke"
                  strokeWidth={4}
                  strokeLinejoin="round"
                  className="fill-foreground stroke-card font-numeric text-200 font-semibold tabular-nums"
                >
                  {formatOkuNumber(quarters[i]!.total, 1)}
                </text>
              );
            })}
            {scenario !== undefined && scenarioY !== undefined && forecastPoint && (
              <text
                x={forecastPoint[0]}
                y={scenarioIsHigher ? scenarioY - 11 : scenarioY + 22}
                textAnchor="middle"
                paintOrder="stroke"
                strokeWidth={4}
                strokeLinejoin="round"
                className="fill-brand-foreground stroke-card font-numeric text-200 font-semibold tabular-nums"
              >
                {formatOkuNumber(scenario, 1)}
              </text>
            )}
            {quarters.map((q, i) => {
              const [top, bottom] = axisLabels(q, compact);
              return (
                <g key={q.key}>
                  <text x={xs[i]!} y={plot.y1 + 20} textAnchor="middle" className="fill-foreground text-200 font-semibold">{top}</text>
                  <text x={xs[i]!} y={plot.y1 + 36} textAnchor="middle" className="fill-muted-foreground text-200">{bottom}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p className="text-200 text-muted-foreground">
        線の軸（左）は 0 からではなく、{line.lo}〜{line.hi} 億円を拡大して表示しています（棒の中には目盛りを出していません）。棒の軸（右）は 0 から始まる、別の目盛りです。
      </p>
      <DataTable quarters={quarters} sectors={sectors} />
    </div>
  );
}
