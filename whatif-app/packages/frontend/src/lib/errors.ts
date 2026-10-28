// サーバーの失敗コードを、取るべき行動が分かる文言にする。内部の詳細（ID・トークン・サーバーの本文）は出さない。

export interface Explained {
  title: string;
  action: string;
  /** 人が何かを直さないと復旧しない（再試行しても無駄）。 */
  needsOperator: boolean;
}

const BY_CODE: Record<string, Explained> = {
  CAPACITY: {
    title: 'Fabric の容量が停止しています',
    action: 'ワークスペースの Fabric 容量を再開してから、再試行してください。再開には 1 分ほどかかります。',
    needsOperator: true,
  },
  AUTH: {
    title: 'アプリの ID に、読み取りの権限がありません',
    action: 'アプリの所有者が、ワークスペースと Lakehouse を読めるか確認してください。',
    needsOperator: true,
  },
  NOT_FOUND: {
    title: '必要な項目が見つかりません',
    action: 'ワークスペースに、Lakehouse、Ontology、グラフが存在するか確認してください。',
    needsOperator: true,
  },
  AMBIGUOUS: {
    title: '同じ名前の項目が複数あります',
    action: 'ワークスペース内の項目名の重複を解消してください。',
    needsOperator: true,
  },
  RATE_LIMIT: {
    title: 'アクセスが集中しています',
    action: 'しばらくしてから、再試行してください。',
    needsOperator: false,
  },
  UPSTREAM: {
    title: 'データの取得に失敗しました',
    action: 'Lakehouse またはグラフが一時的に応答していない可能性があります。再試行してください。',
    needsOperator: false,
  },
  UNKNOWN_EVENT: {
    title: '選んだイベントが見つかりません',
    action: '画面を再読み込みしてください。',
    needsOperator: false,
  },
  UNEXPECTED: {
    title: '予期しないエラーが起きました',
    action: '再試行してください。続く場合は、管理者に連絡してください。',
    needsOperator: false,
  },
};

const FALLBACK: Explained = {
  title: '処理に失敗しました',
  action: '再試行してください。続く場合は、管理者に連絡してください。',
  needsOperator: false,
};

export function explainCode(code: string): Explained {
  return BY_CODE[code] ?? FALLBACK;
}

/**
 * ネットワークの切断・時間切れなど、サーバーが応答を返せなかった失敗。
 * メッセージの本文は使わない（URL や内部の識別子が含まれ得る）。名前だけで判断する。
 */
export function explainThrown(error: unknown): Explained {
  const name = error instanceof Error ? error.name : '';
  if (/timeout|abort/i.test(name)) {
    return {
      title: '応答に時間がかかりすぎています',
      action: 'グラフの初回の読み込みは最大 1 分ほどかかります。少し待って、再試行してください。',
      needsOperator: false,
    };
  }
  if (/network/i.test(name)) {
    return {
      title: 'サーバーに接続できません',
      action: 'ネットワークの接続を確認して、再試行してください。',
      needsOperator: false,
    };
  }
  if (/auth|unauthor|forbidden/i.test(name)) {
    return {
      title: 'サインインの有効期限が切れた可能性があります',
      action: 'ページを再読み込みして、もう一度サインインしてください。',
      needsOperator: false,
    };
  }
  return FALLBACK;
}
