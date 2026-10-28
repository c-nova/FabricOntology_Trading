// 人が目で確かめるための照合表。厳密に一致すべき項目が1つでもずれたら、終了コード 1。
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Decimal } from '../src/decimal.js';
import { prepare, reconcile, simulate } from '../src/index.js';
import { loadLocalDataset } from '../src/local-loader.js';

const D = (x: string | number) => new Decimal(x);
const yen = (s: string) => D(s).toNumber().toLocaleString('ja-JP', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

interface Check {
  name: string;
  expected: string;
  actual: string;
  // 厳密に一致すべきものは tolerance を付けない。付けた項目は「丸めの粒度の差」として許容
  tolerance?: string;
  note?: string;
}

const t0 = performance.now();
const ds = loadLocalDataset();
const p = prepare(ds.base);
const loadMs = performance.now() - t0;
const rec = reconcile(p);

const checks: Check[] = [];
const base = simulate(p);
checks.push({ name: '年間の実績EBITDA（全額連結）', expected: '44757399732.84', actual: base.base.full, note: 'docs/architecture.md' });
checks.push({ name: '年間の実績EBITDA（持分管理）', expected: '33547898914.09', actual: base.base.management, note: 'docs/architecture.md' });

const fod = base.eventImpacts.find((e) => e.eventId === 'FOD_NEG')!;
const audit = existsSync(resolve(process.cwd(), '..', 'reports', 'step3_live_audit.json'))
  ? (JSON.parse(readFileSync(resolve(process.cwd(), '..', 'reports', 'step3_live_audit.json'), 'utf8')) as Record<string, unknown>)
  : null;
const cloud = (k: string, fallback: string): string => {
  const v = audit?.[k];
  return typeof v === 'string' || typeof v === 'number' ? String(v) : fallback;
};
checks.push({ name: '食品損失の全体効果（全額連結・84件）', expected: cloud('exact_full_event_jpy', '-114461186.25'), actual: fod.baseFull, note: 'Step 3 がクラウドで算出' });
checks.push({ name: '食品損失の全体効果（持分管理・84件）', expected: cloud('exact_management_event_jpy', '-87630294.31'), actual: fod.baseManagement, note: 'Step 3 がクラウドで算出' });

const none = Object.fromEntries(p.events.map((e) => [e.eventId, 0]));
const noEvents = simulate(p, { events: none });
const baselineFull = ds.reference.baselineRows.reduce((a, r) => a.plus(r.amountGroup), D(0)).toFixed(2);
const baselineMgmt = ds.reference.baselineRows.reduce((a, r) => a.plus(r.managementJpy), D(0)).toFixed(2);
checks.push({ name: '全イベントを消した合計（全額連結）', expected: baselineFull, actual: noEvents.scenario.full, note: 'ベースライン表の合計' });
checks.push({ name: '全イベントを消した合計（持分管理）', expected: baselineMgmt, actual: noEvents.scenario.management, note: 'ベースライン表の合計' });

const fodOut = simulate(p, { events: { FOD_NEG: 0 } });
checks.push({
  name: '食品損失を消した差（全額連結）',
  expected: D(fod.baseFull).neg().toFixed(2),
  actual: fodOut.delta.full,
  tolerance: '0.05',
  note: '効果の合計との差は、行ごとの丸めの粒度',
});
const fodHalf = simulate(p, { events: { FOD_NEG: 0.5 } });
checks.push({ name: '食品損失を50%軽減した差（全額連結）', expected: '57230593.13', actual: fodHalf.delta.full, note: '効果の合計の半分' });

const yenUp = simulate(p, { fx: { factor: 0.9 } });
const yenDown = simulate(p, { fx: { factor: 1.1 } });
checks.push({ name: '円高10%の差（全額連結）', expected: '-2328820955.84', actual: yenUp.delta.full, tolerance: '1', note: '以前の試算（合計に10%を掛けた近似）' });
checks.push({ name: '円高10%の差（持分管理）', expected: '-1409756134.73', actual: yenUp.delta.management, tolerance: '1', note: '以前の試算（合計に10%を掛けた近似）' });
checks.push({ name: '円安10%の差（全額連結）', expected: '2328820955.84', actual: yenDown.delta.full, tolerance: '1', note: '以前の試算（合計に10%を掛けた近似）' });

const ownUp = simulate(p, { ownership: { SUB_FOD_JP_01: 1 } });
const sub = ownUp.byEntity.find((e) => e.key === 'SUB_FOD_JP_01')!;
checks.push({ name: '持分51%→100%の差（SUB_FOD_JP_01・持分管理）', expected: D(sub.base.full).minus(sub.base.management).toFixed(2), actual: ownUp.delta.management, note: '全額 − 持分管理' });

console.log(`\nデータ: ${ds.base.ebitdaRows.length} 行 / 効果 ${ds.base.effects.length} 件 / イベント ${ds.base.events.length} 件（読み込み+準備 ${loadMs.toFixed(0)} ms）`);
console.log(`保存値との再現: 日次の不一致 ${rec.groupMismatches + rec.managementMismatches}、効果の不一致 ${rec.effectFullMismatches + rec.effectManagementMismatches}、構造の問題 ${rec.structuralIssues.length} → ${rec.ok ? 'OK' : 'NG'}\n`);

let failed = rec.ok ? 0 : 1;
for (const c of checks) {
  const diff = D(c.actual).minus(c.expected);
  const exact = diff.isZero();
  const within = c.tolerance !== undefined && diff.abs().lte(c.tolerance);
  const verdict = exact ? '一致' : within ? `差 ${diff.toFixed(2)}（許容 ±${c.tolerance}）` : '不一致';
  if (!exact && !within) failed += 1;
  console.log(`${exact || within ? 'OK' : 'NG'}  ${c.name}`);
  console.log(`      期待 ${yen(c.expected).padStart(22)}   実測 ${yen(c.actual).padStart(22)}   ${verdict}   [${c.note ?? ''}]`);
}

// 画面操作を想定した計算時間（スライダーを動かすたびに再計算する）
const runs = 50;
const t1 = performance.now();
for (let i = 0; i < runs; i++) simulate(p, { events: { FOD_NEG: i / runs }, fx: { factor: 0.9 + (i % 20) / 100 } });
console.log(`\n計算時間: 1回あたり ${((performance.now() - t1) / runs).toFixed(1)} ms（${runs} 回の平均、2,920行・1,344効果）`);

console.log(failed === 0 ? '\n結果: すべて照合できました' : `\n結果: ${failed} 件が照合できません`);
process.exit(failed === 0 ? 0 : 1);
