import { describe, expect, it } from 'vitest';

import { eventName, eventPeriod, sortEvents, sourceNarrative } from './events';
import type { ModelEvent } from './types';

// 実機の loadModel が返した形（Graph の日付は ISO 日時）
const ev = (eventId: string, sector: string, direction: string, narrative = `SYNTHETIC: ${eventId} narrative`): ModelEvent => ({
  eventId,
  sector,
  direction,
  severity: 5,
  startDate: '2026-02-09T00:00:00Z',
  endDate: '2026-03-01T00:00:00Z',
  narrative,
  effects: 84,
});

describe('sortEvents', () => {
  it('セクター順（金属・エネルギー・食品・金融・全業種）→ 悪材料が先 → ID', () => {
    const sorted = sortEvents([
      ev('CROSS_POS', 'all', 'positive'),
      ev('FOD_POS', 'foods', 'positive'),
      ev('MTL_POS', 'metals', 'positive'),
      ev('FOD_NEG', 'foods', 'negative'),
      ev('ENE_NEG', 'energy', 'negative'),
      ev('FIN_NEG', 'finance', 'negative'),
      ev('MTL_NEG', 'metals', 'negative'),
      ev('CROSS_NEG', 'all', 'negative'),
    ]).map((e) => e.eventId);
    expect(sorted).toEqual(['MTL_NEG', 'MTL_POS', 'ENE_NEG', 'FOD_NEG', 'FOD_POS', 'FIN_NEG', 'CROSS_NEG', 'CROSS_POS']);
  });

  it('入力を書き換えない', () => {
    const input = [ev('B', 'foods', 'negative'), ev('A', 'metals', 'negative')];
    sortEvents(input);
    expect(input.map((e) => e.eventId)).toEqual(['B', 'A']);
  });

  it('未知のセクターは、最後に並べる', () => {
    expect(sortEvents([ev('X', 'unknown', 'negative'), ev('A', 'metals', 'negative')]).map((e) => e.eventId)).toEqual(['A', 'X']);
  });
});

describe('eventName / sourceNarrative / eventPeriod', () => {
  it('既知のイベントは日本語名にする', () => {
    expect(eventName(ev('FOD_NEG', 'foods', 'negative'))).toBe('コールドチェーンの劣化（食品ロス）');
  });
  it('未知のイベントは、元のナラティブ（SYNTHETIC: を除く）をそのまま出す', () => {
    expect(eventName(ev('NEW_EVT', 'foods', 'negative', 'SYNTHETIC: flood at the depot'))).toBe('flood at the depot');
  });
  it('ナラティブも空なら、ID を出す', () => {
    expect(eventName(ev('NEW_EVT', 'foods', 'negative', ''))).toBe('NEW_EVT');
  });
  it('元のナラティブは、先頭の SYNTHETIC: だけを外す', () => {
    expect(sourceNarrative({ narrative: 'SYNTHETIC: cold chain spoilage incident' })).toBe('cold chain spoilage incident');
    expect(sourceNarrative({ narrative: 'plain text' })).toBe('plain text');
  });
  it('期間は、日付だけにして出す', () => {
    expect(eventPeriod(ev('FOD_NEG', 'foods', 'negative'))).toBe('2026-02-09〜2026-03-01');
  });
});
