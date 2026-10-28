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

[`decks/TradingOntology_Demo_Presenter_Guide_JA.pptx`](decks/TradingOntology_Demo_Presenter_Guide_JA.pptx)（61枚、7章構成。各章の最初に章扉があり、全ページに発表者ノート）

| 章 | 内容 | 使う場面 |
|---|---|---|
| 1 全体像と準備 | 10分の進行、想定企業と場面、デモ環境の構成、8社を同じ尺度で比べる前提、実演前の確認事項（環境、製品の状態、日本語の扱い） | 実演の前 |
| 2 営業向け基礎 | EBITDA、baselineとactual、51%所有、通貨と現金を数値例で説明 | 経営指標になじみのない相手に説明する前 |
| 3 実演 | 4つの入力（Q1〜Q4）の全文と結果、Notebookの図、4つの金額の区別、締め、任意の業務アプリ（Fabric Apps）の実演 | ライブの10分（Step04と業務アプリは時間があるとき） |
| 4 想定質問と答え方 | 短い回答集、SQLとOntologyの違い、全社波及の扱い（同時に全社へ及ぶ形と、連鎖する形の区別）、カジュアルな質問への対応、業務アプリの想定質問 | 質疑のとき |
| 5 お客様データへの当てはめ | イベントの集め方、台帳の列の例、小さく始める進め方 | お客様と次の一歩を話すとき |
| 6 構成の解説 | Lakehouse、ゼロコピーと実体化、Ontologyの全体マップ（既存データと要整備データ）、実体と表の対応、関係、設計の理由、GraphとDeltaの役割分担 | 技術の質問が出たとき |
| 7 Ontologyの新機能 | 名前空間、ビジネスルール、共有プロパティ、継承、導入の順番（いずれもPreviewで、このデモでは未実装） | 今後の拡張を聞かれたとき |

質問は [`prompts/presenter_prompts_ja.txt`](prompts/presenter_prompts_ja.txt) にもあります。質問の流れは、Q1（月次のbaselineとactual）、Q2（10イベントの増減）、Q3（食品損失の根拠）、Q4（影響点の特定と対応案）です。章立ては `presentation/build_presenter_deck.py` の `CHAPTERS` で定義しており、章扉とページ番号はそこから生成します。

## What-ifアプリ（Fabric Apps）

為替とイベントの影響を変えたときの、全社EBITDAの差額と内訳を出す画面です。Fabric Apps（Rayfin、Preview）で動きます。

- 金額：LakehouseからSQLで読んだ行を、`whatif-engine` と同じ計算（Decimal、行ごとに小数2桁へ丸め）で出します。Ontologyのグラフは、計算の入力にしていません
- Ontology：グラフ（GQL Query API、beta）に問い合わせて、イベント一覧と、イベントから全社KPIまでの経路を取得します。経路の影響額の件数は、Lakehouseの件数と照合して表示します
- 確認：2026-10-28に、デプロイ済みのアプリで確認しました。確認できた範囲と未確認の範囲は、`reports/whatif_app_live_verification_2026-10-28.json` にあります
- 接続設定（`.env`、`local.settings.json`、`.deployments.json`）はGit管理外です。`whatif-app/rayfin/rayfin.yml` の公開先ホストは、`__APP_HOST__` に置き換えてあります。デプロイの前に、`restore` で実際の値に戻してください（戻さないと、公開先でのサインインが通らない場合があります）。`rayfin/.project.json`（スキャフォールドの匿名の識別子）も、Git管理外です

## ディレクトリ

| パス | 内容 |
|---|---|
| `config/` | Fabricへのデプロイ定義、検証用の設定（識別子はプレースホルダー。「環境ID（識別子）の扱い」を参照） |
| `data/` | 生成済みデータセットと、ECBの為替の生データ |
| `ddl/` | テーブル定義 |
| `docs/` | 構成、再構築手順 |
| `notebooks/` | データ投入と検証、Step03のNotebook |
| `ontology/`、`ontology_tmdl/` | Ontology定義（現行形式は `ontology_tmdl/`、`ontology/` は旧形式の参考） |
| `prompts/` | Data Agentの指示、質問 |
| `reports/` | 検証結果（クラウド側、Graph、Data Agent） |
| `scripts/` | データ生成、デプロイ補助、検証、環境IDの置き換え（`environment_ids.py`） |
| `presentation/` | 説明者ガイドの生成と検証 |
| `whatif-app/` | What-ifシミュレータ（Fabric Apps、Rayfin）。画面は `packages/frontend`、Functionsは `packages/functions` |
| `whatif-engine/` | シナリオを金額にする計算（Decimal）とテスト。アプリのFunctionsには、`whatif-app/scripts/sync-engine.mjs` で取り込みます |
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

## 環境ID（識別子）の扱い

公開リポジトリのため、デモ環境のFabricの識別子は、`__WORKSPACE_ID__` のようなプレースホルダーに置き換えています。対象は、ワークスペース、キャパシティ、各アイテム（Lakehouse、Notebook、Ontology、Graph、Data Agent）、ジョブ、SQLエンドポイントのIDとホスト名、Data Agentの会話などのIDです。What-ifアプリの公開先ホスト名、アイテムID、テナントID、公開キーも含みます。認証情報は含みません。

- 実際の値は、Git管理外の `config/environment_ids.local.json` に置きます（`.gitignore` 済み。項目の一覧と形式は `config/environment_ids.example.json`）
- Fabricに接続するスクリプトやNotebookを使う前に、`python3 scripts/environment_ids.py restore` で実際の値に戻します
- コミットの前に、`python3 scripts/environment_ids.py redact` でプレースホルダーに戻し、`python3 scripts/environment_ids.py check` で残りがないことを確認します。`check` は対応表がなくても、ランダムなGUIDと、SQLエンドポイントおよびFabric Appsのホスト名を探します
- プレースホルダーのままでは、Fabricに接続するスクリプトやNotebookは動きません。`decks/` の説明者ガイドにあるFabricへのリンクも、プレースホルダーのままです。実際のリンクが要るときは、`restore` のあとに `python3 presentation/build_presenter_deck.py` で作り直してください

## 検証の状況（2026-10-27時点）

- Data Agentは、Fabricで公開済みです。説明者ガイドの質問は、同日に公開済み版で実行しました。Q1、Q3、Q4の結果は元データと照合し、Q2の金額は公開済み版のQA（`reports/da_qa_published.json`）で照合済みです。後述の指示文の更新（5回目の公開）のあとにも、Q1〜Q4を公開済み版で1回ずつ実行し、数値が変わらないことを確認しています
- Notebookの保存済みDAG（8ノード、7矢印）は、実Graph（GQL）の結果と、Deltaの金額照合に基づきます
- カジュアルな質問への対応：公開済みDAに短い質問を10個入れたところ、OK 6、一部 2、NG 2でした（`reports/da_casual_baseline_2026-10-26.json`）。用語と既定値を足した指示文（[`prompts/da_instructions_ja.txt`](prompts/da_instructions_ja.txt)）を公開した結果、10問すべてと追加の質問がOKになり、Q1〜Q4の数値は変わりませんでした。公開後の確認で、期間の値が1日分になる、金額の桁の誤り、前の質問の引き継ぎなどの失敗が見つかったため、同日に計5回公開し直しています。経過と限界は `reports/da_casual_after_2026-10-26.json` にあります。LLMのため文面は実行ごとに変わり、確認した回数も少ないので、毎回同じ答えとは限りません。変えたのはエージェントの指示だけで、データ、Ontology、Lakehouse、データソースの設定は変えていません。DAの指示文の先頭行は、ここでは匿名化しています
- 全社に及ぶ出来事（横断の2件）の確認：公開済みDAに、業種別、会社別、年間EBITDA比、連鎖、円高の試算などを、のべ8回聞きました（`reports/da_group_wide_2026-10-27.json`、読み取りのみ）。表の金額は、元データの集計と小数第2位まで一致しました。表のまわりの文章には誤りが出ることがあり、連鎖と円高の質問は、断り付きで答えたり、答えが分かれたりしました。DAがOntologyの経路探索を試した6回は、すべて「経路なし」で、答えはLakehouseのSQLで求めています。確認の詳細と限界は、報告書にあります。`scripts/verify_live_reports.py` に、金額の照合を追加しました
- DAの経路探索の修正：上の8回では、DAがOntologyの経路探索を試した6回すべてで「経路なし」が返りました。原因は、Ontologyの42のリレーションシップが、すべて無効（`isActive: false`）になっていたことです。有効にして、公開APIが消す接続情報（20表×8項目）を再適用し、Graphを更新しました。同じ8問を公開済みDAで聞き直すと、経路探索を試した6回すべてで経路が見つかり、金額は変わりませんでした。実演の質問Q1〜Q4と対応案の質問も、修正後に1回ずつ聞き直し、元データと一致しました（`reports/da_traversal_fix_2026-10-27.json`）。DAの設定は変えていません。DAがGraphをたどるのではなく、答えは今もLakehouseの表へのSQLで求めています
- 新機能の解説は、Microsoft Learn（2026-10-26時点）と、このデモのOntologyの実機確認（名前空間は既定値のみ、ルール0件、共有プロパティ0件、継承なし、バージョン0件）に基づきます。導入案（名前空間の分け方、ルール、共有プロパティ、継承）は、説明者の提案で、Fabricには反映していません
- Data Agentのruntimeは Preview、Graphの公開APIは beta です。日本語での利用は動作確認した範囲（best effort）で、公式なサポート保証ではありません

## 注意

- すべて架空のデータです。実在企業の非公開データではありません
- Fabricのワークスペースやアイテムの識別子は、プレースホルダーに置き換えてあります（「環境ID（識別子）の扱い」を参照）。認証情報は含みません
- 全額連結EBITDAも持分管理寄与EBITDAも、連結財務諸表の数値ではなくデモ用の管理値です。CFはEBITDAの80%を起点にした簡易シミュレーションで、正式な営業CFではありません
