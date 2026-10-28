import { describe, expect, it } from 'vitest';

import {
  formatDate,
  formatMillion,
  formatOku,
  formatPercent,
  formatRatio,
  formatSignedMillion,
  formatSignedOku,
  formatSignedYen,
  formatYen,
  formatYenAsOku,
  formatOkuNumber,
  subtract,
} from './format';

// 値は、デプロイ先の Functions が実際に返した文字列（実機で確認済み）に合わせている。
describe('formatYen', () => {
  it('桁区切りを付け、サーバーの桁を変えない（8 桁の小数は 2 桁に切る）', () => {
    expect(formatYen('44757399732.84')).toBe('44,757,399,732.84');
    expect(formatYen('-114461186.25000000')).toBe('−114,461,186.25');
    expect(formatYen('1.00000000')).toBe('1.00');
  });

  it('13 桁の金額でも、浮動小数点を通さず、1 銭まで一致する', () => {
    expect(formatYen('33547898914.09')).toBe('33,547,898,914.09');
    expect(formatYen('-2274575575.77')).toBe('−2,274,575,575.77');
  });

  it('0 や微小値で「−0.00」を出さない', () => {
    expect(formatYen('0.00')).toBe('0.00');
    expect(formatYen('-0.00')).toBe('0.00');
    expect(formatYen('-0.004')).toBe('0.00');
    expect(formatYen('0.4')).toBe('0.40');
  });

  it('数値でない入力は、嘘の値を出さず「—」にする', () => {
    expect(formatYen('')).toBe('—');
    expect(formatYen('abc')).toBe('—');
    expect(formatYen('1e9')).toBe('—');
  });
});

describe('formatSignedYen', () => {
  it('0 以外は符号を付け、0 は符号なし', () => {
    expect(formatSignedYen('57230593.13')).toBe('+57,230,593.13');
    expect(formatSignedYen('-2331806168.90')).toBe('−2,331,806,168.90');
    expect(formatSignedYen('0.00')).toBe('0.00');
    expect(formatSignedYen('-0.00')).toBe('0.00');
  });
});

describe('formatOku', () => {
  it('億円・万円・円に切り替える', () => {
    expect(formatOku('44757399732.84')).toBe('447.6億円');
    expect(formatOku('-2274575575.77')).toBe('−22.7億円');
    expect(formatOku('-9500000')).toBe('−950万円');
    expect(formatOku('1234')).toBe('1,234円');
    expect(formatOku('44757399732.84')).toBe('447.6億円');
    expect(formatOku('1234567890123')).toBe('12,345.7億円');
  });

  it('符号付きは、0 以外に + を付ける', () => {
    expect(formatSignedOku('57230593.13')).toBe('+5,723万円');
    expect(formatSignedOku('2328820955.71')).toBe('+23.3億円');
    expect(formatSignedOku('0')).toBe('0円');
  });
});

describe('formatYenAsOku', () => {
  it('1億円未満でも万円にせず、常に億円で出す（同じ画面のグラフ・表と単位をそろえる）', () => {
    expect(formatYenAsOku('-93050000.00')).toBe('−0.93億円');
    expect(formatYenAsOku('-93050000.00', 2, true)).toBe('−0.93億円');
    expect(formatYenAsOku('93050000.00', 2, true)).toBe('+0.93億円');
    expect(formatYenAsOku('11489536832.22')).toBe('114.90億円');
    expect(formatYenAsOku('11375075645.97')).toBe('113.75億円');
  });

  it('0 や微小な値で「−0.00」を出さず、数値でないものは出さない', () => {
    expect(formatYenAsOku('0.00', 2, true)).toBe('0.00億円');
    expect(formatYenAsOku('-100.00', 2, true)).toBe('0.00億円');
    expect(formatYenAsOku('abc')).toBe('—');
    expect(formatYenAsOku('')).toBe('—');
  });
});

describe('formatOkuNumber', () => {
  it('億円の数値だけを出す。負は「−」、正の符号は求められたときだけ付ける', () => {
    expect(formatOkuNumber(115.6138958, 1)).toBe('115.6');
    expect(formatOkuNumber(-1.1446, 2)).toBe('−1.14');
    expect(formatOkuNumber(1.1446, 2, true)).toBe('+1.14');
    expect(formatOkuNumber(1.1446, 2)).toBe('1.14');
  });

  it('0 に丸まる値は、符号を付けない', () => {
    expect(formatOkuNumber(-0.0004, 2)).toBe('0.00');
    expect(formatOkuNumber(0.0004, 2, true)).toBe('0.00');
    expect(formatOkuNumber(Number.NaN)).toBe('—');
    expect(formatOkuNumber(Number.POSITIVE_INFINITY)).toBe('—');
  });
});

describe('formatPercent', () => {
  it('基準に対する割合を、符号付きで出す', () => {
    expect(formatPercent('-2274575575.77', '44757399732.84')).toBe('−5.1%');
    expect(formatPercent('57230593.13', '44757399732.84')).toBe('+0.1%');
  });

  it('丸めて 0 になるときは符号を付けない', () => {
    expect(formatPercent('1000', '44757399732.84')).toBe('0.0%');
  });

  it('基準が 0 や不正なときは出さない', () => {
    expect(formatPercent('10', '0')).toBe('—');
    expect(formatPercent('x', '10')).toBe('—');
  });
});

describe('formatRatio / formatDate', () => {
  it('持分は百分率にする', () => {
    expect(formatRatio('0.51000000')).toBe('51%');
    expect(formatRatio('1.00000000')).toBe('100%');
    expect(formatRatio('0.755')).toBe('75.5%');
  });

  it('Graph の ISO 日時も、Lakehouse の日付も、日付だけにする（1 日ずれない）', () => {
    expect(formatDate('2026-05-11T00:00:00Z')).toBe('2026-05-11');
    expect(formatDate('2025-11-12')).toBe('2025-11-12');
    expect(formatDate('not a date')).toBe('—');
  });
});

describe('formatMillion / formatSignedMillion', () => {
  it('百万円にして、桁区切りと小数 1 桁にする', () => {
    expect(formatMillion('44757399732.84')).toBe('44,757.4');
    expect(formatMillion('-114461186.25')).toBe('−114.5');
    expect(formatMillion('0')).toBe('0.0');
  });
  it('丸めて 0 になる負の値は、符号を付けない（−0.0 を出さない）', () => {
    expect(formatMillion('-20000')).toBe('0.0');
    expect(formatSignedMillion('-20000')).toBe('0.0');
    expect(formatSignedMillion('20000')).toBe('0.0');
  });
  it('差は、0 でなければ必ず符号を付ける', () => {
    expect(formatSignedMillion('57230593.13')).toBe('+57.2');
    expect(formatSignedMillion('-2274575575.77')).toBe('−2,274.6');
  });
  it('数値でないものは、ダッシュにする', () => {
    expect(formatMillion('abc')).toBe('—');
    expect(formatSignedMillion('')).toBe('—');
  });
});

describe('subtract', () => {
  it('シナリオ − 基準 を返す', () => {
    expect(Number(subtract('-87630294.31', '-114461186.25'))).toBeCloseTo(26830891.94, 2);
    expect(subtract('5', '5')).toBe('0');
  });
  it('数値でなければ NaN（表示側でダッシュになる）', () => {
    expect(formatSignedMillion(subtract('abc', '1'))).toBe('—');
  });
});
