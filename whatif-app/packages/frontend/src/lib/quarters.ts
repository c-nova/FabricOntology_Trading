import { orderedSectors } from './events';
import { toOku } from './chart';
import type { ForecastLoaded, ForecastResult } from './types';

// 四半期グラフの系列を組み立てる。会計年度は、このデモのデータの定義に合わせる
// （2025-10-01〜2026-09-30 が FY26。10〜12月が Q1）。

export interface FiscalQuarter {
  fy: number;
  q: number;
}

/** 日付（YYYY-MM-DD）の会計四半期。10月始まり。例: 2026-10-01 → FY27 Q1 */
export function fiscalQuarter(date: string): FiscalQuarter {
  const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(date);
  const month = m ? Number(m[2]) : 0;
  if (!m || month < 1 || month > 12) throw new Error(`Invalid date: ${date}`);
  const year = Number(m[1]);
  return { fy: month >= 10 ? year + 1 : year, q: Math.floor(((month - 10 + 12) % 12) / 3) + 1 };
}

export const fiscalLabel = (date: string): string => {
  const { fy, q } = fiscalQuarter(date);
  return `FY${String(fy).slice(-2)} Q${q}`;
};

/** 四半期の最初の月（"YYYY-MM"）から、月の範囲。例: "2026-10" → "10〜12月" */
export function monthsLabel(key: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(key);
  const first = m ? Number(m[2]) : 0;
  if (!m || first < 1 || first > 12) throw new Error(`Invalid quarter: ${key}`);
  return `${first}〜${first + 2}月`;
}

/**
 * 横軸の四半期ラベル（2段）。狭い幅では、「FY26 Q1」を「26Q1」、「10〜12月」を「10〜12」に縮めて、隣と重ならないようにする
 * （年度は残す。予測の四半期だけが FY27 で、Q の数字だけだと区別できなくなるため）。
 */
export function axisLabels(q: Pick<ChartQuarter, 'fiscal' | 'months'>, compact: boolean): [string, string] {
  if (!compact) return [q.fiscal, q.months];
  return [q.fiscal.replace(/^FY(\d{2})\s*/, '$1'), q.months.replace(/月$/, '')];
}

function daysInQuarter(key: string): number {
  const [y, m] = key.split('-').map(Number) as [number, number];
  return Math.round((Date.UTC(y, m + 2, 1) - Date.UTC(y, m - 1, 1)) / 86_400_000);
}

export interface SectorValue {
  code: string;
  /** 億円 */
  value: number;
}

export interface ChartQuarter {
  key: string;
  kind: 'actual' | 'forecast';
  fiscal: string;
  months: string;
  /** データがある日数が、四半期の日数に満たない（一部しか入っていない） */
  partial: boolean;
  /** 実績、または基準の予測（億円） */
  total: number;
  /** イベントを仮定した後（億円）。予測の四半期で、計算できたときだけ */
  scenario?: number;
  /** 業種別の内訳。分からないとき（保存された予測に会社別が無い）は null */
  sectors: SectorValue[] | null;
}

function sectorValues(bySector: Readonly<Record<string, string>>): SectorValue[] {
  return orderedSectors(Object.keys(bySector)).map((code) => ({ code, value: toOku(bySector[code]!) }));
}

/**
 * 過去の実績の四半期と、予測の四半期を、1本の系列にする。
 * イベントを仮定した結果は、予測期間が同じときだけ使う（古い結果を別の期間に重ねない）。
 */
export function buildChartQuarters(loaded: ForecastLoaded, scenario?: ForecastResult): ChartQuarter[] {
  const past = [...loaded.history]
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
    .map<ChartQuarter>((q) => ({
      key: q.key,
      kind: 'actual',
      fiscal: fiscalLabel(q.from),
      months: monthsLabel(q.key),
      partial: q.days < daysInQuarter(q.key),
      total: toOku(q.total),
      sectors: sectorValues(q.bySector),
    }));

  const { baseline } = loaded.forecast;
  const fromKey = baseline.period.from.slice(0, 7);
  const usable = scenario !== undefined && scenario.period.from === baseline.period.from && scenario.period.to === baseline.period.to;
  const next: ChartQuarter = {
    key: fromKey,
    kind: 'forecast',
    fiscal: fiscalLabel(baseline.period.from),
    months: monthsLabel(fromKey),
    partial: false,
    total: toOku(baseline.amountFull),
    sectors: loaded.forecastBySector ? sectorValues(loaded.forecastBySector) : null,
    ...(usable ? { scenario: toOku(scenario.scenarioFull) } : {}),
  };
  return [...past, next];
}

/** 描画する業種（積み上げの順）。過去と予測に出てくる業種をまとめる。 */
export function sectorsOf(quarters: readonly ChartQuarter[]): string[] {
  return orderedSectors(quarters.flatMap((q) => q.sectors?.map((s) => s.code) ?? []));
}
