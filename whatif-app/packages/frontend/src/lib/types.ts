import type { AppFunctionsSchema } from '@rayfin-app/functions/types';

// Functions の生成型（手で書かない）から導く。関数のシグネチャが変われば、ここで型エラーになる。
type Fn = AppFunctionsSchema;

export type ScenarioInput = Fn['simulate']['input']['scenario'];
export type SimulateOutput = Fn['simulate']['output'];
export type LoadModelOutput = Fn['loadModel']['output'];
export type EventPathsOutput = Fn['eventPaths']['output'];

export type Success<T extends { ok: boolean }> = Extract<T, { ok: true }>;
export type Failure = { ok: false; code: string; message: string };

export type SimulationResult = Success<SimulateOutput>['result'];
export type Model = Success<LoadModelOutput>['model'];
export type ModelEvent = Model['events'][number];
export type ModelCompany = Model['companies'][number];
export type GraphPath = Success<EventPathsOutput>['paths'][number];
export type EventImpact = SimulationResult['eventImpacts'][number];
export type Breakdown = SimulationResult['byEntity'][number];
export type Totals = SimulationResult['base'];

export type Metric = 'full' | 'management';
