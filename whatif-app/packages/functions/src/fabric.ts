// 実行時に Fabric REST で解決する座標。ID やホスト名はソースに持たない（公開リポジトリのため）。
// 持つのは、デモ上の表示名だけ。

export const NAMES = {
  workspace: 'Trading',
  lakehouse: 'LH_Group_SAP',
  ontology: 'TradingOntology_Multisector',
} as const;

const FABRIC_API = 'https://api.fabric.microsoft.com/v1';

export class FabricError extends Error {
  constructor(
    readonly code: 'AUTH' | 'NOT_FOUND' | 'CAPACITY' | 'RATE_LIMIT' | 'UPSTREAM' | 'AMBIGUOUS',
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'FabricError';
  }
}

// 本文はそのまま返さない（内部の ID やトークンが混ざり得るため、コードだけ拾う）
function classify(status: number, body: string): FabricError {
  const code = /"errorCode"\s*:\s*"([^"]+)"/.exec(body)?.[1];
  if (code === 'CapacityNotActive') {
    return new FabricError('CAPACITY', 'Fabric capacity is not active (paused). Resume it and retry.', status);
  }
  if (status === 401 || status === 403) {
    return new FabricError('AUTH', `Fabric API denied access (${status}${code ? ' ' + code : ''}). The app identity needs access to the workspace.`, status);
  }
  if (status === 404) return new FabricError('NOT_FOUND', `Fabric API returned 404${code ? ' ' + code : ''}.`, status);
  if (status === 429) return new FabricError('RATE_LIMIT', 'Fabric API rate limit exceeded.', status);
  return new FabricError('UPSTREAM', `Fabric API returned ${status}${code ? ' ' + code : ''}.`, status);
}

export interface FabricCall {
  path: string;
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
}

export async function fabricFetch<T>(token: string, call: FabricCall): Promise<T> {
  const url = call.path.startsWith(FABRIC_API) ? call.path : `${FABRIC_API}/${call.path}`;
  if (!url.startsWith(FABRIC_API)) throw new FabricError('UPSTREAM', 'Unexpected API host');
  const res = await fetch(url, {
    method: call.method ?? 'GET',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: call.body === undefined ? undefined : JSON.stringify(call.body),
    signal: call.signal,
  });
  const text = await res.text();
  if (!res.ok) throw classify(res.status, text);
  return (text ? JSON.parse(text) : {}) as T;
}

interface Item {
  id: string;
  displayName: string;
  type?: string;
}

async function listAll(token: string, path: string): Promise<Item[]> {
  const out: Item[] = [];
  let next: string | undefined;
  for (let i = 0; i < 20; i += 1) {
    const sep = path.includes('?') ? '&' : '?';
    const page = await fabricFetch<{ value: Item[]; continuationToken?: string }>(token, {
      path: next ? `${path}${sep}continuationToken=${encodeURIComponent(next)}` : path,
    });
    out.push(...page.value);
    next = page.continuationToken;
    if (!next) return out;
  }
  throw new FabricError('UPSTREAM', 'Pagination exceeded its limit');
}

function exactlyOne(items: Item[], name: string, what: string): Item {
  const hits = items.filter((i) => i.displayName === name);
  if (hits.length === 0) throw new FabricError('NOT_FOUND', `${what} "${name}" was not found`);
  if (hits.length > 1) throw new FabricError('AMBIGUOUS', `${what} "${name}" matched ${hits.length} items`);
  return hits[0]!;
}

export interface Coordinates {
  workspaceId: string;
  lakehouseId: string;
  // SQL 分析エンドポイントの database には、GUID ではなく Lakehouse の表示名を渡す（実環境で確認済み。GUID は
  // 「database not found」で ELOGIN になる。公式ガイドの GUID 指定とは異なる）
  lakehouseName: string;
  sqlServer: string;
  graphId: string;
}

// 名前から座標を解決する。権限のないものは、見つからない/拒否として明示的に失敗する
export async function resolveCoordinates(token: string): Promise<Coordinates> {
  const workspaces = await listAll(token, 'workspaces');
  const workspace = exactlyOne(workspaces, NAMES.workspace, 'Workspace');

  const items = await listAll(token, `workspaces/${workspace.id}/items`);
  const lakehouse = exactlyOne(items.filter((i) => i.type === 'Lakehouse'), NAMES.lakehouse, 'Lakehouse');
  const ontology = exactlyOne(items.filter((i) => i.type === 'Ontology'), NAMES.ontology, 'Ontology');

  const graphs = await listAll(token, `workspaces/${workspace.id}/graphModels`);
  const graph = exactlyOne(graphs, `${NAMES.ontology}_graph_${ontology.id.replace(/-/g, '')}`, 'Graph model');

  const detail = await fabricFetch<{
    properties?: { sqlEndpointProperties?: { connectionString?: string; provisioningStatus?: string } };
  }>(token, { path: `workspaces/${workspace.id}/lakehouses/${lakehouse.id}` });
  const sql = detail.properties?.sqlEndpointProperties;
  if (!sql?.connectionString || sql.provisioningStatus !== 'Success') {
    throw new FabricError('UPSTREAM', 'The Lakehouse SQL analytics endpoint is not ready');
  }

  return {
    workspaceId: workspace.id,
    lakehouseId: lakehouse.id,
    lakehouseName: lakehouse.displayName,
    sqlServer: sql.connectionString,
    graphId: graph.id,
  };
}
