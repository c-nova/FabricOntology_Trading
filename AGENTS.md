# AGENTS.md

AIエージェント向けの指示です。このリポジトリは**公開**です。作業の前に、このファイルと [`README.md`](README.md) を読んでください。`whatif-app/` を触るときは、`whatif-app/AGENTS.md`（Rayfinのスキャフォールドが生成した指示）も読みます。

## 公開リポジトリとしての約束

- **実際の識別子をコミットしない。** ワークスペース、キャパシティ、各アイテム、ジョブ、SQLエンドポイント、Data Agentの会話、What-ifアプリのホスト名・アイテムID・テナントID・公開キーは、`__WORKSPACE_ID__`、`__APP_HOST__` のようなプレースホルダーにしてあります。実際の値は、Git管理外の `config/environment_ids.local.json` にあります。認証情報は、リポジトリにありません。
- **Fabricに接続する前、アプリを `rayfin up` でデプロイする前に、`python3 scripts/environment_ids.py restore` を実行する。** `whatif-app/rayfin/rayfin.yml` の公開先ホスト（`__APP_HOST__`）が残ったままデプロイすると、公開先でのサインインが通らない場合があります。
- **コミットの前に、`python3 scripts/environment_ids.py redact`、続けて `python3 scripts/environment_ids.py check` を実行し、`ok: no environment identifiers found` を確認する。** `restore` したままのファイルは、コミットしない。`git add -A` や `git commit -a` の前は、特に注意する。
- 次のファイルには、実際の値が入っています（Git管理外）。コミットせず、内容を資料、ログ、回答に貼らない：`config/environment_ids.local.json`、`whatif-app/rayfin/.env`、`whatif-app/rayfin/.deployments.json`、`whatif-app/packages/frontend/.env.local`、`whatif-app/packages/functions/local.settings.json`。`whatif-app/rayfin/.project.json`（スキャフォールドの匿名の識別子）も、Git管理外にしています。
- `git push` は、ユーザーの明示の指示があるときだけ行う。履歴の書き換えと強制pushはしない（決定済み）。大きなpushがHTTP 400になるときは、`git -c http.postBuffer=157286400 push` にする。
- Fabricへの書き込み（デプロイ、削除、容量の停止など）は、ユーザーが対象のワークスペースを確認してから行う。

## 資料（`decks/`）は、ビルダーから作り直す

pptxを直接編集しない。`presentation/` のビルダーを直して、作り直します。

| 資料 | 作り直し | 点検 |
|---|---|---|
| 説明者ガイド | `python3 presentation/build_presenter_deck.py` | `python3 presentation/verify_presenter_deck.py` |
| 顧客向け | 下の注を参照 | `python3 presentation/verify_customer_deck.py` |

- 顧客向けのビルダーは、`finalize()` を定義しますが、末尾では呼びません。`/usr/bin/python3 -c "import runpy; runpy.run_path('presentation/build_customer_deck.py')['finalize']()"` で実行します。`python-pptx`、`Pillow`、`budoux` が要ります（macOSの `/usr/bin/python3` で確認）。
- 作り直しと点検は、`&&` でつなぐ。`verify` は、いまあるpptxを描画するので、ビルドが失敗しても通ってしまいます。
- 点検は、LibreOfficeで描画します（画像は `presentation/qa/`、Git管理外）。フォントが代替なので、改行位置はPowerPointと違います。最終確認は、PowerPointで。
- 資料の数字は、`data/` と `reports/` から計算し、ビルダーの `assert` で照合しています。数字を手で書かない。

## 資料と画面に書いてよいこと

- 各ページに、伝えたいことと、存在理由がある。章立てと章扉を保つ。
- デモが示していないこと（規模、性能、コスト、権限、Graphの網羅性）は、断定しない。「Microsoft Learnの記載」「デモで未検証」「仮の目安」を書き分ける。
- Ontologyの役割は、次のとおり。Ontologyは、金額を計算しない。Data Agentは、Ontologyの定義と関係を参照し、答えはLakehouseの表へのSQLで求める。What-ifアプリは、LakehouseからSQLで読んだ行を、アプリのコードで計算する。グラフ（GQL Query API、beta）が返すのは、イベント一覧と経路で、計算には使わない。
- 用語は、資料とアプリでそろえる：影響額、取引活動、日次指標、全社KPI、契約、イベント。画面の「実績」は、資料の「実績」（イベントの影響を反映した値）で、「基準値」（影響を加える前の想定値）とは別です。
- Fabric Apps、Ontology、Data AgentはPreviewで、グラフのクエリ用APIはbetaです。

## What-ifアプリ

- 計算の元は `whatif-engine/src` です。`whatif-app/packages/functions/src/engine/` は生成されたコピーなので、直接編集しません。`whatif-app/` で `node scripts/sync-engine.mjs` を実行してコピーし、`--check` を付けて差分を調べます。
- 検証：`whatif-engine/` で `npm test`、`npm run verify`。`whatif-app/` で `npm test`、`npm run lint`、`npm run typecheck`。
- 実機の確認は、`whatif-app/scripts/live-check.mjs` です（読み取りのみ。`az` でサインイン済みで、`AZURE_TENANT` が必要）。結果は、`reports/whatif_app_live_verification_2026-10-28.json` にあります。資料の数字の出どころで、確認できた範囲と、未確認の範囲（`not_verified`）を含みます。
- 画面だけを変えたときの再デプロイは、`whatif-app/` で `npx rayfin up --workspace Trading --exclude-services functions --json --yes` です（`restore` のあと、ユーザーの確認のあとで）。
