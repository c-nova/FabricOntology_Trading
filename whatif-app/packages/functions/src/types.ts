/**
 * Function schema types for RayfinClient.
 *
 * AUTO-GENERATED — do not edit manually.
 * Re-generated automatically when function source files change.
 *
 * If this file is not updating automatically, run:
 *   rayfin dev functions apply
 *
 * The schema is a closed object type: only the function names listed
 * below are accepted by RayfinClient.functions.<name>.invoke(...).
 * Adding, renaming, or changing the signature of a udf.func() call
 * regenerates this file and surfaces type errors at every consumer.
 *
 * IMPORTANT: This file must NOT import any Node.js packages — it is
 * resolved by the frontend app's TypeScript compiler.
 */

export type AppFunctionsSchema = {
  probe: {
    input: Record<string, never>;
    output: { ok: true; source: 'cache' | 'loaded'; loadMs: number; cacheAgeMs: null | number; counts: { companies: number; ebitdaRows: number; effects: number; events: number }; reconciliation: { ok: boolean; groupMismatches: number; managementMismatches: number; effectMismatches: number }; base: { full: string; management: string }; graph: { events: number; eventIds: string[]; foodLossPathRows: number; foodLossUniqueEffects: number; pathMs: number } } | { ok: false; code: string; message: string };
  };
  simulate: {
    input: { scenario: { fx?: undefined | { currency?: undefined | string; factor: string | number }; events?: undefined | { [k: string]: string | number }; ownership?: undefined | { [k: string]: string | number }; period?: undefined | { from?: undefined | string; to?: undefined | string } } };
    output: { ok: false; code: string; message: string } | { ok: true; source: 'cache' | 'loaded'; result: { period: { from: string; to: string }; applied: { fx: null | { currency: string; factor: string }; events: { [k: string]: string }; ownership: { [k: string]: string } }; base: { full: string; management: string }; scenario: { full: string; management: string }; delta: { full: string; management: string }; steps: { events: { full: string; management: string }; fx: { full: string; management: string }; ownership: { full: string; management: string } }; byEntity: { key: string; label: string; base: { full: string; management: string }; scenario: { full: string; management: string }; delta: { full: string; management: string } }[]; bySector: { key: string; label: string; base: { full: string; management: string }; scenario: { full: string; management: string }; delta: { full: string; management: string } }[]; byMonth: { key: string; label: string; base: { full: string; management: string }; scenario: { full: string; management: string }; delta: { full: string; management: string } }[]; eventImpacts: { eventId: string; scale: string; effects: number; baseFull: string; scenarioFull: string; baseManagement: string; scenarioManagement: string }[]; stats: { rows: number; rowsTouched: number; effects: number } } };
  };
  loadModel: {
    input: Record<string, never>;
    output: { ok: false; code: string; message: string } | { ok: true; source: 'cache' | 'loaded'; model: { events: ({ eventId: string; sector: string; direction: string; severity: number; startDate: string; endDate: string; narrative: string } & { effects: number })[]; companies: { entityId: string; name: string; sector: string; currency: string; ownership: string }[]; period: { from: string; to: string } } };
  };
  eventPaths: {
    input: { eventId: string };
    output: { ok: false; code: string; message: string } | { ok: true; eventId: string; paths: { effectId: string; entityId: string; activityId: string; activityType: string; commodity: string; contractId: string; evidenceId: string; metricId: string; kpiId: string }[] };
  };
  loadForecast: {
    input: Record<string, never>;
    output: { ok: false; code: string; message: string } | { ok: true; forecast: { baseline: { asOf: string; period: { from: string; to: string }; amountFull: string }; generatedAt: string; model: string }; history: { key: string; from: string; to: string; days: number; bySector: { [k: string]: string }; total: string }[]; forecastBySector: null | { [k: string]: string } };
  };
  simulateForecast: {
    input: { scenario: { eventId: string; eventDate: string; scale: number } };
    output: { ok: false; code: string; message: string } | { ok: true; result: { period: { from: string; to: string }; asOf: string; baselineFull: string; scenarioFull: string; deltaFull: string; eventId: string; eventDate: string; scale: string; includedEffects: number; excludedEffects: number; historicalEffects: number; byEntity: { entityId: string; name: string; deltaFull: string }[] }; graph: { effects: number; activities: number; contracts: number; evidence: number; metrics: number; kpis: number } };
  };
};
