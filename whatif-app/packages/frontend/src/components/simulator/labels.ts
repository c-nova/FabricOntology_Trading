import type { Metric } from '@/lib/types';

// 画面に出す名前。データから導けない情報は足さず、ID・コードはサーバーの値をそのまま使う。

export const METRICS: readonly { id: Metric; label: string; hint: string }[] = [
  { id: 'full', label: '全額連結', hint: '子会社の EBITDA を 100% 合算した値' },
  { id: 'management', label: '持分管理', hint: '子会社の EBITDA に持分比率を掛けて合算した管理上の値（会計上の持分法とは別）' },
];

export const SECTOR_LABEL: Record<string, string> = {
  metals: '金属',
  energy: 'エネルギー',
  foods: '食品',
  finance: '金融',
  all: '全業種',
};

export const sectorLabel = (code: string): string => SECTOR_LABEL[code] ?? code;

export const DIRECTION_LABEL: Record<string, string> = {
  negative: '悪材料',
  positive: '好材料',
};

export const directionLabel = (direction: string): string => DIRECTION_LABEL[direction] ?? direction;

export const ACTIVITY_LABEL: Record<string, string> = {
  external_sale: '外部販売',
};

export const activityLabel = (type: string): string => ACTIVITY_LABEL[type] ?? type;
