import { formatDate } from './format';
import type { ModelEvent } from './types';

// イベントの表示。ID・向き・重要度・期間は、サーバー（オントロジーのグラフ）の値のまま使う。

const SECTOR_ORDER = ['metals', 'energy', 'foods', 'finance', 'all'] as const;

// 元データのナラティブ（英語）の和訳。未知のイベントは、元のナラティブか ID をそのまま出す。
const JAPANESE_NAME: Record<string, string> = {
  MTL_NEG: '製錬所の操業停止',
  MTL_POS: '再生合金のプレミアム契約',
  CROSS_NEG: '港湾と資金繰りの混乱',
  CROSS_POS: '物流と資金管理の回復',
  ENE_NEG: 'LNG ターミナルの保守遅延',
  ENE_POS: '貯蔵・出荷の最適化',
  FOD_NEG: 'コールドチェーンの劣化（食品ロス）',
  FOD_POS: '穀物の収量と調達の改善',
  FIN_NEG: '取引先対応コストの急増',
  FIN_POS: 'ヘッジ執行手数料の増加',
};

const sectorRank = (sector: string): number => {
  const i = (SECTOR_ORDER as readonly string[]).indexOf(sector);
  return i === -1 ? SECTOR_ORDER.length : i;
};

const directionRank = (direction: string): number => (direction === 'negative' ? 0 : direction === 'positive' ? 1 : 2);

const compare = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** 業種コードを、画面の並び（金属・エネルギー・食品・金融・全業種・その他）にそろえる。 */
export function orderedSectors(codes: Iterable<string>): string[] {
  return [...new Set(codes)].sort((a, b) => sectorRank(a) - sectorRank(b) || compare(a, b));
}

/** セクター順（金属・エネルギー・食品・金融・全業種）→ 悪材料が先 → ID。 */
export function sortEvents(events: readonly ModelEvent[]): ModelEvent[] {
  return [...events].sort(
    (a, b) => sectorRank(a.sector) - sectorRank(b.sector) || directionRank(a.direction) - directionRank(b.direction) || compare(a.eventId, b.eventId),
  );
}

const SOURCE_PREFIX = /^SYNTHETIC:\s*/i;

/** 元データのナラティブ（英語）。先頭の「SYNTHETIC:」だけ外す。 */
export function sourceNarrative(event: Pick<ModelEvent, 'narrative'>): string {
  return event.narrative.replace(SOURCE_PREFIX, '').trim();
}

export function eventName(event: Pick<ModelEvent, 'eventId' | 'narrative'>): string {
  return JAPANESE_NAME[event.eventId] ?? (sourceNarrative(event) || event.eventId);
}

/** 例: 2026-02-09〜2026-03-01 */
export function eventPeriod(event: Pick<ModelEvent, 'startDate' | 'endDate'>): string {
  return `${formatDate(event.startDate)}〜${formatDate(event.endDate)}`;
}
