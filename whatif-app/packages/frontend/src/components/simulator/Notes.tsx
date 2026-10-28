import { SectionLabel } from './primitives';

// この画面が何を証明し、何を証明しないか。断定しすぎないために、常に出す。
const NOTES: readonly { title: string; body: string }[] = [
  {
    title: '架空のデータです',
    body: 'すべて架空の総合商社のデモデータです。実在の企業・数値とは関係ありません。',
  },
  {
    title: '結果は「設計した仕組み」の試算です',
    body: 'イベントの影響を倍率で増減し、為替を円換算に掛け直しています。因果関係を証明するものではなく、実際の損益を予測するものでもありません。',
  },
  {
    title: '為替は円換算だけを動かします',
    body: 'USD 建て子会社の円換算レートだけを変えます。為替ヘッジ、価格への転嫁、取引量の変化は反映していません。',
  },
  {
    title: '持分管理 EBITDA は管理上の値です',
    body: '子会社の EBITDA に持分比率を掛けた管理上の値で、会計上の持分法や連結の数値とは別です。',
  },
  {
    title: '端数の扱い',
    body: '日次の行ごとに小数 2 桁へ丸めて合計しているため、手計算の比例計算とは 1 円未満ずれることがあります。',
  },
  {
    title: 'Ontology は構造を、Lakehouse は金額を担当します',
    body: '右の経路はオントロジーのグラフから取得した構造（つながり）です。金額の計算は Lakehouse の値で行い、両者の影響額の件数が一致するかを確認して表示しています。グラフの問い合わせはプレビュー機能（beta）を使っています。',
  },
];

export function Notes() {
  return (
    <section aria-labelledby="notes-label" className="space-y-300 border-t border-border pt-500">
      <SectionLabel id="notes-label">この画面の読み方</SectionLabel>
      <dl className="grid gap-x-600 gap-y-400 md:grid-cols-2 xl:grid-cols-3">
        {NOTES.map((n) => (
          <div key={n.title} className="space-y-100">
            <dt className="text-300 font-semibold text-foreground">{n.title}</dt>
            <dd className="text-300 text-muted-foreground">{n.body}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
