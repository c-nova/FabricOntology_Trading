// 表示用の書式。サーバーが返す金額は 10 進の文字列で、桁を変えないために文字列のまま扱う。
// 「億円」などの簡易表示だけ、表示専用で Number を使う（精度が要る計算には使わない）。

const NUMERIC = /^-?\d+(\.\d+)?$/;

export function isNumeric(value: string): boolean {
  return NUMERIC.test(value);
}

function groupInteger(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function groupFixed(n: number, digits: number): string {
  const [intPart = '0', frac] = n.toFixed(digits).split('.');
  return frac === undefined ? groupInteger(intPart) : `${groupInteger(intPart)}.${frac}`;
}

/** 符号付きの 10 進文字列を、桁区切り＋小数 2 桁にする。例: "-114461186.25000000" → "-114,461,186.25" */
export function formatYen(value: string): string {
  if (!isNumeric(value)) return '—';
  const negative = value.startsWith('-');
  const [intPart = '0', frac = ''] = (negative ? value.slice(1) : value).split('.');
  const cents = (frac + '00').slice(0, 2);
  const body = `${groupInteger(intPart.replace(/^0+(?=\d)/, ''))}.${cents}`;
  return negative && /[1-9]/.test(intPart + cents) ? `−${body}` : body;
}

/** 差の表示。0 以外は必ず符号を付ける（色だけに頼らない）。 */
export function formatSignedYen(value: string): string {
  if (!isNumeric(value)) return '—';
  const text = formatYen(value);
  if (/^[−]?0\.00$/.test(text)) return '0.00';
  return text.startsWith('−') ? text : `+${text}`;
}

/** 2 つの 10 進文字列の差（scenario − base）。表示用の簡易計算で、精度が要る計算には使わない。 */
export function subtract(scenario: string, base: string): string {
  if (!isNumeric(scenario) || !isNumeric(base)) return 'NaN';
  return String(Number(scenario) - Number(base));
}

/** 百万円の表示（表用）。単位は列見出しに出す。例: "-114461186.25" → "−114.5"。表示専用で Number を使う。 */
export function formatMillion(value: string, digits = 1): string {
  if (!isNumeric(value)) return '—';
  const n = Number(value);
  const text = groupFixed(Math.abs(n) / 1e6, digits);
  return n < 0 && /[1-9]/.test(text) ? `−${text}` : text;
}

/** 差の百万円表示。0 以外は符号を付ける。 */
export function formatSignedMillion(value: string, digits = 1): string {
  if (!isNumeric(value)) return '—';
  const text = formatMillion(value, digits);
  if (/^0(\.0+)?$/.test(text)) return text;
  return text.startsWith('−') ? text : `+${text}`;
}

/** 億円の簡易表示。例: "-2274575575.77" → "−22.7億円"。1 万円未満は「円」で出す。 */
export function formatOku(value: string, digits = 1): string {
  if (!isNumeric(value)) return '—';
  const n = Number(value);
  const abs = Math.abs(n);
  const sign = n < 0 ? '−' : '';
  if (abs >= 1e8) return `${sign}${groupFixed(abs / 1e8, digits)}億円`;
  if (abs >= 1e4) return `${sign}${groupFixed(abs / 1e4, 0)}万円`;
  return `${sign}${groupFixed(abs, 0)}円`;
}

export function formatSignedOku(value: string, digits = 1): string {
  if (!isNumeric(value)) return '—';
  const n = Number(value);
  if (n === 0) return '0円';
  const text = formatOku(value, digits);
  return n > 0 ? `+${text}` : text;
}

/** 基準に対する割合。基準が 0 のときは出さない。例: "−5.1%" */
export function formatPercent(delta: string, base: string, digits = 1): string {
  if (!isNumeric(delta) || !isNumeric(base)) return '—';
  const b = Number(base);
  if (b === 0) return '—';
  const p = (Number(delta) / Math.abs(b)) * 100;
  const rounded = p.toFixed(digits);
  if (Number(rounded) === 0) return `${(0).toFixed(digits)}%`;
  return p > 0 ? `+${rounded}%` : `−${Math.abs(p).toFixed(digits)}%`;
}

/** 持分比率。例: "0.51000000" → "51%"、"1.00000000" → "100%" */
export function formatRatio(value: string): string {
  if (!isNumeric(value)) return '—';
  const pct = Number(value) * 100;
  return `${Number.isInteger(pct) ? pct.toFixed(0) : pct.toFixed(1)}%`;
}

/** 日付だけにする。Graph は日付を ISO 日時（"2026-05-11T00:00:00Z"）で返す。Lakehouse は "2026-05-11"。 */
export function formatDate(value: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  return m ? m[1]! : '—';
}

/** 倍率の表示。例: "0.5" → "50%" */
export function formatScale(percent: number): string {
  return `${percent}%`;
}
