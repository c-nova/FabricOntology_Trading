// 読み取り専用の実環境チェック。az でサインイン済みの自分の権限で、Functions と同じコード
// （座標の解決・Lakehouse SQL・Graph・エンジン）を実行し、件数・合計・突き合わせだけを表示する。
// ID・ホスト名・トークンは出力しない。
//
//   AZURE_TENANT=<テナントのドメインまたはID> node scripts/live-check.mjs
import { execFileSync } from 'node:child_process';
import { resolveCoordinates } from '../packages/functions/dist/fabric.js';
import { readBaseData, EXPECTED } from '../packages/functions/dist/lakehouse.js';
import { readEvents, readPaths } from '../packages/functions/dist/graph.js';
import { prepare, reconcile, simulate } from '../packages/functions/dist/engine/index.js';

const tenant = process.env.AZURE_TENANT;
const token = (resource) =>
  execFileSync(
    'az',
    ['account', 'get-access-token', '--resource', resource, ...(tenant ? ['--tenant', tenant] : []), '--query', 'accessToken', '-o', 'tsv'],
    { encoding: 'utf8' },
  ).trim();

// docs/architecture.md の記載値と、Step 3 がクラウドで算出した値
const DOCUMENTED = { annualFull: '44757399732.84', annualManagement: '33547898914.09', fodNegFull: '-114461186.25', fodNegManagement: '-87630294.31' };

const results = [];
const check = (name, ok, detail = '') => {
  results.push(ok);
  console.log(`${ok ? 'OK ' : 'NG '} ${name}${detail ? '  ' + detail : ''}`);
};
const timed = async (label, fn) => {
  const t0 = performance.now();
  const value = await fn();
  console.log(`     (${label}: ${(performance.now() - t0).toFixed(0)} ms)`);
  return value;
};

const fabric = token('https://api.fabric.microsoft.com');
const sqlToken = token('https://database.windows.net/');

const coordinates = await timed('座標の解決', () => resolveCoordinates(fabric));
check('座標を名前から解決（ワークスペース・Lakehouse・Ontology・Graph・SQLエンドポイント）', Boolean(coordinates.sqlServer && coordinates.graphId));

const base = await timed('Lakehouse SQL の読み出し', () => readBaseData(sqlToken, coordinates));
check('件数が想定どおり', Object.entries(EXPECTED).every(([k, n]) => (k === 'ebitdaRows' ? base.ebitdaRows : base[k]).length === n),
  `companies ${base.companies.length}, rows ${base.ebitdaRows.length}, effects ${base.effects.length}, events ${base.events.length}`);

const prepared = prepare(base);
const rec = reconcile(prepared);
check('日次・効果が、保存値と同じ式で完全に再現できる', rec.ok, `日次不一致 ${rec.groupMismatches + rec.managementMismatches}, 効果不一致 ${rec.effectFullMismatches + rec.effectManagementMismatches}`);

const baseline = simulate(prepared, {});
check('年間の実績EBITDA（全額連結）が文書の値と一致', baseline.base.full === DOCUMENTED.annualFull, baseline.base.full);
check('年間の実績EBITDA（持分管理）が文書の値と一致', baseline.base.management === DOCUMENTED.annualManagement, baseline.base.management);
const fod = baseline.eventImpacts.find((e) => e.eventId === 'FOD_NEG');
check('食品損失の全体効果がクラウド算出値と一致（全額・持分）', fod.baseFull === DOCUMENTED.fodNegFull && fod.baseManagement === DOCUMENTED.fodNegManagement, `${fod.baseFull} / ${fod.baseManagement}`);

const events = await timed('Graph: イベント一覧', () => readEvents(fabric, coordinates));
const sqlEvents = new Set(base.events.map((e) => e.eventId));
check('Graph のイベント一覧が、SQL と同じ10件', events.length === 10 && events.every((e) => sqlEvents.has(e.eventId)), events.map((e) => e.eventId).join(','));

const paths = await timed('Graph: 食品損失の経路', () => readPaths(fabric, coordinates, 'FOD_NEG'));
const sqlEffects = new Map(base.effects.filter((e) => e.eventId === 'FOD_NEG').map((e) => [e.effectId, e.metricId]));
const graphEffects = new Map(paths.map((p) => [p.effectId, p.metricId]));
check('Graph の経路が84件で、効果ID・日次メトリクスが SQL と完全に一致',
  paths.length === 84 && graphEffects.size === 84 && sqlEffects.size === 84 && [...sqlEffects].every(([id, m]) => graphEffects.get(id) === m),
  `paths ${paths.length}, unique ${graphEffects.size}`);

const sample = simulate(prepared, { events: { FOD_NEG: 0.5 }, fx: { factor: 0.9 } });
check('シナリオ（食品損失50%軽減 + 円高10%）が計算できる', sample.stats.rowsTouched > 0, `差 ${sample.delta.full}`);

console.log(results.every(Boolean) ? '\n結果: すべて確認できました' : '\n結果: 確認できない項目があります');
process.exit(results.every(Boolean) ? 0 : 1);
