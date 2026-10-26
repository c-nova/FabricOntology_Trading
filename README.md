# FabricOntology_Trading

架空の総合商社を題材にした Fabric IQ（Ontology、Data Agent）デモの成果物一式です。金属、エネルギー、食品、金融の4セクターにある日本と米国の8社を、JPYにそろえて比較し、イベントの影響を根拠、契約、KPIまでたどります。

LNG / Power Trading 向けの PoC は [FabricOntology_TradingLNG](https://github.com/c-nova/FabricOntology_TradingLNG) にあります。

## デモの内容

- 8社：4セクター × 日本、米国。所有比率は100%が4社、51%が4社で、国では決めていません。全社を支配子会社として全額連結し、所有比率を掛けた「持分管理寄与」を別の指標として持ちます
- 対象年度は2025-10-01〜2026-09-30。会社、契約、根拠、イベントは架空（合成データ）です。為替だけは、ECBが公開する日次の参考レートを使っています
- イベントは10件（各セクターのプラスとマイナス、横断2件）。影響額は設計上の配賦で、実世界の因果の証明ではありません
- Fabric上の構成：9つのLakehouse（親1、子会社8）、Ontology（17種類の実体、39種類の関係）、Data Agent、食品損失の経路をDAGで示すNotebook

構成の詳細は [`docs/architecture.md`](docs/architecture.md) にあります。

## 説明者ガイド

[`decks/TradingOntology_Demo_Presenter_Guide_JA.pptx`](decks/TradingOntology_Demo_Presenter_Guide_JA.pptx)（43枚、全ページに発表者ノート）

- 経営指標に詳しくない営業向けに、EBITDA、baselineとactual、51%所有、通貨と現金を数値例で説明
- Data Agentに入力する質問Q1〜Q4の全文と、対応する結果。質問は [`prompts/presenter_prompts_ja.txt`](prompts/presenter_prompts_ja.txt) にもあります
- 食品損失のDAG、金額の読み方、想定質問、実演前の確認事項、顧客データへの当てはめ方
- LakehouseとOntologyの構成の解説（9つのLakehouse、17実体と39関係の全体マップ、実体と表の対応、関係の読み方、設計判断）
- Ontologyの新機能の解説（名前空間、ビジネスルール、共有プロパティ、継承、導入の優先順位）と、小さく始める進め方。いずれもPreviewで、このデモでの導入案は未実装です

質問の流れは、Q1（月次のbaselineとactual）、Q2（10イベントの増減）、Q3（食品損失の根拠）、Q4（影響点の特定と対応案）です。

## ディレクトリ

| パス | 内容 |
|---|---|
| `config/` | Fabricへのデプロイ定義、ID、検証用の設定 |
| `data/` | 生成済みデータセットと、ECBの為替の生データ |
| `ddl/` | テーブル定義 |
| `docs/` | 構成、再構築手順 |
| `notebooks/` | データ投入と検証、Step03のNotebook |
| `ontology/`、`ontology_tmdl/` | Ontology定義（現行形式は `ontology_tmdl/`、`ontology/` は旧形式の参考） |
| `prompts/` | Data Agentの指示、質問 |
| `reports/` | 検証結果（クラウド側、Graph、Data Agent） |
| `scripts/` | データ生成、デプロイ補助、検証 |
| `presentation/` | 説明者ガイドの生成と検証 |
| `decks/` | 生成した説明者ガイド |

## 再生成

データの再生成と検証は、`docs/architecture.md` の「Rebuild and verification」を参照してください。

説明者ガイドは、次のコマンドで作り直せます。Fabric APIは呼びません。

```sh
pip install -r requirements.txt
python3 presentation/build_presenter_deck.py
python3 presentation/verify_presenter_deck.py   # LibreOfficeで描画して点検
```

`verify_presenter_deck.py` は、macOSのLibreOffice（`/Applications/LibreOffice.app`）とHomebrewのフォント設定を前提にしています。パスは環境変数 `SOFFICE` と `presentation/fonts.conf` で変更できます。日本語フォントが無い環境では、描画結果の改行位置が実際のPowerPointと異なります。最終確認はPowerPointで行ってください。

## 検証の状況（2026-10-26時点）

- Data Agentは、Fabricで公開済みです。説明者ガイドの質問は、同日に公開済み版で実行しました。Q1、Q3、Q4の結果は元データと照合し、Q2の金額は公開済み版のQA（`reports/da_qa_published.json`）で照合済みです
- Notebookの保存済みDAG（8ノード、7矢印）は、実Graph（GQL）の結果と、Deltaの金額照合に基づきます
- 新機能の解説は、Microsoft Learn（2026-10-26時点）と、このデモのOntologyの実機確認（名前空間は既定値のみ、ルール0件、共有プロパティ0件、継承なし、バージョン0件）に基づきます。導入案（名前空間の分け方、ルール、共有プロパティ、継承）は、説明者の提案で、Fabricには反映していません
- Data Agentのruntimeは Preview、Graphの公開APIは beta です。日本語での利用は動作確認した範囲（best effort）で、公式なサポート保証ではありません

## 注意

- すべて架空のデータです。実在企業の非公開データではありません
- `config/deployment_manifest.json` などに、Fabricのワークスペースとアイテムの識別子が含まれます。認証情報は含みません。公開リポジトリにする場合は、識別子を含めてよいか確認してください
- 全額連結EBITDAも持分管理寄与EBITDAも、連結財務諸表の数値ではなくデモ用の管理値です。CFはEBITDAの80%を起点にした簡易シミュレーションで、正式な営業CFではありません
