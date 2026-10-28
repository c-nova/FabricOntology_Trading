import type { EventImpact, GraphPath, ModelEvent } from './types';

// Ontology のグラフが返した経路の集計。
// 経路: RiskEvent -[EventHasEffect]-> FinancialEffect -[EffectOnActivity]-> Activity -[ActivityUnderContract]-> Contract
//       FinancialEffect -[EffectRealizedInMetric]-> FinancialMetric -[MetricRollsUpToGroupKPI]-> GroupKPI

export interface ChainNode {
  type: 'RiskEvent' | 'FinancialEffect' | 'Activity' | 'Contract' | 'FinancialMetric' | 'GroupKPI';
  label: string;
  count: number;
  /** 前のノードとの関係名（グラフの関係の名前） */
  via?: string;
  /** 関係の起点が、1 つ上の行ではないときの、起点のノード名 */
  from?: string;
}

const distinct = (values: readonly string[]): number => new Set(values).size;

export function buildChain(paths: readonly GraphPath[]): ChainNode[] {
  return [
    { type: 'RiskEvent', label: 'イベント', count: paths.length > 0 ? 1 : 0 },
    { type: 'FinancialEffect', label: '影響額', count: distinct(paths.map((p) => p.effectId)), via: 'EventHasEffect' },
    { type: 'Activity', label: '取引活動', count: distinct(paths.map((p) => p.activityId)), via: 'EffectOnActivity' },
    { type: 'Contract', label: '契約', count: distinct(paths.map((p) => p.contractId)), via: 'ActivityUnderContract' },
    { type: 'FinancialMetric', label: '日次指標', count: distinct(paths.map((p) => p.metricId)), via: 'EffectRealizedInMetric', from: '影響額' },
    { type: 'GroupKPI', label: '全社KPI', count: distinct(paths.map((p) => p.kpiId)), via: 'MetricRollsUpToGroupKPI' },
  ];
}

export interface Consistency {
  /** グラフの経路が指す効果の数 */
  graphEffects: number;
  /** Lakehouse の効果の数（loadModel のイベントごとの件数） */
  lakehouseEffects: number;
  match: boolean;
}

/** Ontology のグラフと Lakehouse が、同じ効果を指しているか（件数の一致）。 */
export function checkConsistency(paths: readonly GraphPath[], event: Pick<ModelEvent, 'effects'>): Consistency {
  const graphEffects = distinct(paths.map((p) => p.effectId));
  return { graphEffects, lakehouseEffects: event.effects, match: graphEffects === event.effects };
}

export interface EntityGroup {
  entityId: string;
  effects: number;
  activityTypes: string[];
  commodities: string[];
}

export function groupByEntity(paths: readonly GraphPath[]): EntityGroup[] {
  const map = new Map<string, { effects: Set<string>; types: Set<string>; commodities: Set<string> }>();
  for (const p of paths) {
    const g = map.get(p.entityId) ?? { effects: new Set(), types: new Set(), commodities: new Set() };
    g.effects.add(p.effectId);
    g.types.add(p.activityType);
    g.commodities.add(p.commodity);
    map.set(p.entityId, g);
  }
  return [...map.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([entityId, g]) => ({ entityId, effects: g.effects.size, activityTypes: [...g.types].sort(), commodities: [...g.commodities].sort() }));
}

/** 既定で経路を見せるイベント: 基準の影響額（絶対値）が最大のもの。 */
export function defaultPathEvent(impacts: readonly EventImpact[]): string | undefined {
  let best: { id: string; size: number } | undefined;
  for (const i of impacts) {
    const size = Math.abs(Number(i.baseFull));
    if (!Number.isFinite(size)) continue;
    if (!best || size > best.size) best = { id: i.eventId, size };
  }
  return best?.id;
}
