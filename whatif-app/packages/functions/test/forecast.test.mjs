import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { forecastBySector, parseForecastDefinition } from '../dist/forecast.js';

const ENTITIES = [
  { entity_id: 'SUB_ENE_JP_01', amount_oku: 16.761951383520305 },
  { entity_id: 'SUB_ENE_US_01', amount_oku: 17.921712467363083 },
  { entity_id: 'SUB_FIN_JP_01', amount_oku: 10.902378271468242 },
  { entity_id: 'SUB_FIN_US_01', amount_oku: 11.935149516587071 },
  { entity_id: 'SUB_FOD_JP_01', amount_oku: 11.01532577422391 },
  { entity_id: 'SUB_FOD_US_01', amount_oku: 11.806451706488616 },
  { entity_id: 'SUB_MTL_JP_01', amount_oku: 16.836923347368323 },
  { entity_id: 'SUB_MTL_US_01', amount_oku: 17.7154752513 },
];
const TOTAL = ENTITIES.reduce((a, e) => a + e.amount_oku, 0);

const report = {
  results: [{ model: 'AutoML', next_q_forecast_oku: 111.2 },
    { model: 'AutoML + Graph', next_q_forecast_oku: TOTAL, next_q_by_entity_oku: ENTITIES }],
  future_origin: '2026-09-30',
  horizon_days: 92,
  executed_at_utc: '2026-10-28T08:21:36.287799+00:00',
  source: { last_date: '2026-09-30', graph_paths: 1344 },
};

function definition(value) {
  const notebook = { metadata: { trading_forecast: { latest_live_report: value } } };
  return { definition: { parts: [{
    path: 'notebook-content.ipynb', payloadType: 'InlineBase64',
    payload: Buffer.from(JSON.stringify(notebook)).toString('base64'),
  }] } };
}

const withEntities = (next_q_by_entity_oku) => ({
  ...report,
  results: [report.results[0], { ...report.results[1], next_q_by_entity_oku }],
});

describe('saved forecast parsing', () => {
  it('selects the Graph model and converts the forecast quarter and each company to yen', () => {
    const parsed = parseForecastDefinition(definition(report));
    assert.equal(parsed.baseline.asOf, '2026-09-30');
    assert.deepEqual(parsed.baseline.period, { from: '2026-10-01', to: '2026-12-31' });
    assert.match(parsed.baseline.amountFull, /^\d+\.\d{2}$/);
    assert.equal(parsed.generatedAt, report.executed_at_utc);
    assert.equal(parsed.model, 'AutoML + Graph');
    assert.equal(parsed.byEntity.length, 8);
    assert.deepEqual(parsed.byEntity[0], { entityId: 'SUB_ENE_JP_01', amountFull: '1676195138.35' });
  });

  it('keeps the model total as the baseline even without a company breakdown (an older saved run)', () => {
    const old = { ...report, results: [report.results[0], { model: 'AutoML + Graph', next_q_forecast_oku: 114.89536832222751 }] };
    const parsed = parseForecastDefinition(definition(old));
    assert.equal(parsed.baseline.amountFull, '11489536832.22');
    assert.equal(parsed.byEntity, null);
  });

  it('rejects missing or ambiguous models and non-quarter horizons', () => {
    for (const bad of [
      { ...report, results: [] },
      { ...report, results: [report.results[1], report.results[1]] },
      { ...report, future_origin: '2026-02-30' },
      { ...report, horizon_days: 91 },
      { ...report, executed_at_utc: 'invalid' },
      { ...report, source: { last_date: '2026-06-30', graph_paths: 1344 } },
      { ...report, source: { last_date: '2026-09-30', graph_paths: 0 } },
    ]) assert.throws(() => parseForecastDefinition(definition(bad)));
    assert.throws(() => parseForecastDefinition({ definition: { parts: [] } }));
  });

  it('rejects a company breakdown that is present but broken, instead of dropping it', () => {
    for (const bad of [
      [],
      'text',
      [...ENTITIES.slice(1)],
      [...ENTITIES, { entity_id: 'SUB_EXTRA', amount_oku: 1 }],
      [ENTITIES[0], ENTITIES[0], ...ENTITIES.slice(2)],
      [{ ...ENTITIES[0], entity_id: '' }, ...ENTITIES.slice(1)],
      [{ ...ENTITIES[0], amount_oku: Number.NaN }, ...ENTITIES.slice(1)],
      [{ ...ENTITIES[0], amount_oku: '16.7' }, ...ENTITIES.slice(1)],
      [null, ...ENTITIES.slice(1)],
    ]) assert.throws(() => parseForecastDefinition(definition(withEntities(bad))), /company forecast/);
  });
});

describe('forecast by sector', () => {
  const companies = [
    { entityId: 'SUB_ENE_JP_01', sectorCode: 'energy' }, { entityId: 'SUB_ENE_US_01', sectorCode: 'energy' },
    { entityId: 'SUB_FIN_JP_01', sectorCode: 'finance' }, { entityId: 'SUB_FIN_US_01', sectorCode: 'finance' },
    { entityId: 'SUB_FOD_JP_01', sectorCode: 'foods' }, { entityId: 'SUB_FOD_US_01', sectorCode: 'foods' },
    { entityId: 'SUB_MTL_JP_01', sectorCode: 'metals' }, { entityId: 'SUB_MTL_US_01', sectorCode: 'metals' },
  ];

  it('adds company forecasts per sector exactly, with every sector present', () => {
    const { byEntity } = parseForecastDefinition(definition(report));
    const sectors = forecastBySector(byEntity, companies);
    assert.deepEqual(Object.keys(sectors), ['energy', 'finance', 'foods', 'metals']);
    assert.equal(sectors.energy, '3468366385.09');
    const cents = (v) => Math.round(Number(v) * 100);
    assert.equal(Object.values(sectors).reduce((a, v) => a + cents(v), 0), byEntity.reduce((a, e) => a + cents(e.amountFull), 0));
  });

  it('returns null when the saved run has no company breakdown, and refuses an unknown company', () => {
    assert.equal(forecastBySector(null, companies), null);
    assert.throws(() => forecastBySector([{ entityId: 'SUB_UNKNOWN', amountFull: '1.00' }], companies), /unknown company/);
  });
});
