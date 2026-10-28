// 将来シミュレーション（予測Notebookの保存結果 + Graph経路 + Lakehouse）の、読み取り専用の実環境チェック。
// az でサインイン済みの自分の権限で、Functions と同じコードを実行し、結果を reports/ 用のJSONとして出力する。
// ID・ホスト名・トークンは出力しない（公開リポジトリのため）。
//
//   AZURE_TENANT=<テナントのドメインまたはID> node scripts/live-check-future.mjs > ../reports/whatif_future_live_verification_<日付>.json
import { execFileSync } from 'node:child_process';
import { resolveCoordinates } from '../packages/functions/dist/fabric.js';
import { readBaseData } from '../packages/functions/dist/lakehouse.js';
import { readEvents, readPaths } from '../packages/functions/dist/graph.js';
import { readForecast, forecastBySector } from '../packages/functions/dist/forecast.js';
import { prepare, simulate, simulateFuture, quarterlySectors } from '../packages/functions/dist/engine/index.js';

const tenant = process.env.AZURE_TENANT;
const token = (resource) =>
  execFileSync(
    'az',
    ['account', 'get-access-token', '--resource', resource, ...(tenant ? ['--tenant', tenant] : []), '--query', 'accessToken', '-o', 'tsv'],
    { encoding: 'utf8' },
  ).trim();

const fabric = token('https://api.fabric.microsoft.com');
const sqlToken = token('https://database.windows.net/');
const log = (...a) => console.error(...a);

const coordinates = await resolveCoordinates(fabric);
const base = await readBaseData(sqlToken, coordinates);
const prepared = prepare(base);
const annual = simulate(prepared, {}).base.full;

const forecast = await readForecast(fabric, coordinates.workspaceId);
const bySector = forecastBySector(forecast.byEntity, base.companies);
const quarters = quarterlySectors(prepared);

// 10イベントすべての、Graph経路と Lakehouse の効果の突き合わせ（効果ID・日次指標ID・会社IDまで）
const events = await readEvents(fabric, coordinates);
const perEvent = [];
const pathsByEvent = new Map();
for (const ev of events) {
  const paths = await readPaths(fabric, coordinates, ev.eventId);
  pathsByEvent.set(ev.eventId, paths);
  const sql = new Map(base.effects.filter((e) => e.eventId === ev.eventId).map((e) => [e.effectId, e]));
  const graph = new Map(paths.map((p) => [p.effectId, p]));
  const exact =
    sql.size === graph.size &&
    [...sql].every(([id, e]) => graph.get(id)?.metricId === e.metricId && graph.get(id)?.entityId === e.entityId);
  perEvent.push({ eventId: ev.eventId, graph_paths: paths.length, lakehouse_effects: sql.size, ids_match_exactly: exact });
  log('path check', ev.eventId, paths.length, exact);
}

const run = (eventId, eventDate, scale) => {
  const r = simulateFuture(prepared, forecast.baseline, { eventId, eventDate, scale }, pathsByEvent.get(eventId));
  return {
    event_id: eventId, event_date: eventDate, scale,
    baseline_jpy: r.baselineFull, scenario_jpy: r.scenarioFull, delta_jpy: r.deltaFull,
    included_effects: r.includedEffects, excluded_effects: r.excludedEffects, historical_effects: r.historicalEffects,
  };
};

const fod = pathsByEvent.get('FOD_NEG');
const distinct = (key) => new Set(fod.map((p) => p[key])).size;

const report = {
  version: 1,
  status: 'verified_live_with_limits',
  subject: '予測Notebookの保存結果（AutoML + Graph）を、アプリの将来タブが読み、イベントを仮定した場合を重ねる',
  captured_note: '読み取り専用。Functionsと同じコードを、サインイン済みの権限で実行して記録した',
  identifiers_recorded: false,
  forecast: {
    model: forecast.model,
    as_of: forecast.baseline.asOf,
    period: forecast.baseline.period,
    baseline_jpy: forecast.baseline.amountFull,
    notebook_saved_at_utc: forecast.generatedAt,
    by_sector_jpy: bySector,
    company_forecasts: forecast.byEntity === null ? null : forecast.byEntity.length,
  },
  actual_by_quarter: quarters.map((q) => ({ key: q.key, from: q.from, to: q.to, days: q.days, total_jpy: q.total, by_sector_jpy: q.bySector })),
  annual_actual_ebitda_full_jpy: annual,
  graph_vs_lakehouse_per_event: perEvent,
  fod_neg_graph_entities: {
    effects: distinct('effectId'), activities: distinct('activityId'), contracts: distinct('contractId'),
    evidence: distinct('evidenceId'), metrics: distinct('metricId'), kpis: distinct('kpiId'),
  },
  scenarios: {
    fod_neg_nov15_100: run('FOD_NEG', '2026-11-15', 1),
    fod_neg_dec20_100: run('FOD_NEG', '2026-12-20', 1),
    fod_neg_dec31_100: run('FOD_NEG', '2026-12-31', 1),
    fod_neg_nov15_300: run('FOD_NEG', '2026-11-15', 3),
    fod_neg_nov15_0: run('FOD_NEG', '2026-11-15', 0),
    fod_pos_nov15_100: run('FOD_POS', '2026-11-15', 1),
    cross_neg_nov15_100: run('CROSS_NEG', '2026-11-15', 1),
  },
};
console.log(JSON.stringify(report, null, 2));
