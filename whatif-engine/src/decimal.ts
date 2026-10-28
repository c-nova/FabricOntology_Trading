import { Decimal as DecimalBase } from 'decimal.js';

// 生成側の money() と同じ規則: 小数2桁、0.5 は切り上げ（0 から遠い方向）
export const Decimal = DecimalBase.clone({ precision: 40, rounding: DecimalBase.ROUND_HALF_UP });
export type Decimal = InstanceType<typeof Decimal>;

export const ZERO = new Decimal(0);
export const ONE = new Decimal(1);

export function money(value: DecimalBase.Value): Decimal {
  return new Decimal(value).toDecimalPlaces(2, DecimalBase.ROUND_HALF_UP);
}

export function fixed2(value: Decimal): string {
  return value.toFixed(2, DecimalBase.ROUND_HALF_UP);
}
