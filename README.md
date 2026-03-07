# X 自動投稿ツール（AI x デザイン）

AI/デザイン領域の最新情報を収集し、
- 投稿案（予測つき）を自動生成
- 条件に合う投稿を引用投稿案として生成
- 運用ルール（品質ゲート）を満たす案のみ採用
- `dry_run` なら実投稿せずログ出力

を行う最小実装です。

## 1. セットアップ

```bash
cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

## 2. 環境変数（.env）

```env
# OpenAI
OPENAI_API_KEY=...

# X API v2 (read)
X_BEARER_TOKEN=...

# X API user context (post)
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...

# Optional: Nano Banana Pro CLI連携（朝枠画像生成）
# 例: nanobanana --prompt "..." --out "..."
NANOBANANA_CMD_TEMPLATE=nanobanana --prompt "{prompt}" --out "{output}"
```

## 3. 実行

```bash
python -m src.x_autopost_tool.main --config config.yaml --slot morning run-once
python -m src.x_autopost_tool.main --config config.yaml --slot noon run-once
python -m src.x_autopost_tool.main --config config.yaml --slot evening run-once
```

`config.yaml` の `posting.dry_run: true` なら投稿せず、生成結果のみ確認できます。

昼枠の投稿直前リフレッシュ（JIT）:
```bash
python -m src.x_autopost_tool.main --config config.yaml --queue-path queue_plan.json refresh-noon-queue
```

## 3.1 運用ルール

`config.yaml` で以下を調整できます。
- `generation.post_style_template`: 投稿の型（事実/示唆/予測/行動）
- `quality_gate.*`: 投稿本文の品質条件
- `quote_rules.*`: 引用候補の除外条件と採用スコア
- `schedule.weekly_themes`: 曜日ごとの投稿テーマ配分
- `schedule.slot_profiles.*`: 朝/昼/夕の文体・文字数・引用可否
- `sources.x_noon_queries`: 昼枠の最新AI引用候補クエリ
- `posting.force_post_if_no_passed`: 品質ゲート未通過時も枠を埋める

詳細は [`OPERATIONS.md`](./OPERATIONS.md) を参照してください。

## 4. cron 例

```bash
0 7 * * * cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool && /usr/bin/env bash -lc 'source .venv/bin/activate && python -m src.x_autopost_tool.main --config config.yaml --slot morning run-once >> logs/runner.log 2>&1'
0 12 * * * cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool && /usr/bin/env bash -lc 'source .venv/bin/activate && python -m src.x_autopost_tool.main --config config.yaml --slot noon run-once >> logs/runner.log 2>&1'
0 18 * * * cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool && /usr/bin/env bash -lc 'source .venv/bin/activate && python -m src.x_autopost_tool.main --config config.yaml --slot evening run-once >> logs/runner.log 2>&1'
# 昼枠は5分ごとにJIT更新（投稿30分前のnoonキューのみ上書き）
*/5 * * * * cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool && /usr/bin/env bash -lc 'source .venv/bin/activate && python -m src.x_autopost_tool.main --config config.yaml --queue-path queue_plan.json refresh-noon-queue >> logs/noon_refresh.log 2>&1'
```

## 5. UIプレビュー

```bash
cd /Users/yuzoazu/Documents/New\ project/x_auto_post_tool
source .venv/bin/activate
python ui/server.py
```

ブラウザで `http://127.0.0.1:8787` を開くと、以下を確認できます。
- API Settings から OpenAI/X のキー保存（`.env` 更新）
- Account Status 内で運用対象Xアカウント（`@handle`）の保存・確認
- X連動チェック（`@username` / フォロワー数）
- 朝/昼/夕の `dry_run` 実行ログ
- Plan Builder（日/週/月 + 毎日投稿ON/OFF）で事前投稿計画を確認
- 左サイドアイコンで各セクションへ移動（🏠ダッシュボード / 🧠投稿生成 / 🗂計画 / ✅キュー / ⚙設定）
- Scheduled Queue で投稿日時と本文を編集し、保存/再読込
- Draft PreviewでX表示モックを確認し、`試験投稿（X）` で実投稿テスト可能
- Draft Preview内の`試験投稿テーマ`から試験投稿文を1本生成可能（OpenAI）
- 生成した投稿文から`Nano Bananaで画像生成`し、画像プレビューと試験投稿添付が可能
- `試験投稿メディア` で画像/動画を1件添付して投稿テスト可能
- `出典URL` + `投稿後に出典URLをリプで付与` で、投稿直後の出典リプ動作をテスト可能
- API Settings内の `Media Automation` で、朝画像生成と昼の出典リプ設定をUI保存可能

運用メモ:
- 昼の最新情報枠は鮮度優先のため、Plan Builderでは「投稿直前生成」のプレースホルダを表示します。
- 昼のJIT枠はキュー保存時に本文空でも保存され、投稿30分前ジョブで自動的に本文が埋まります。
- 投稿文は改行を含む読みやすい段落構成を推奨し、タグは文末2-3個を品質ゲートでチェックします。
- 朝枠は `media.morning_generate_image: true` で画像生成を試行し、生成成功時に画像添付投稿します。
- 昼の引用投稿は、引用元の画像/動画は引用カードで表示されます。`media.noon_reply_source_link: true` なら投稿後にリプで出典URLを付与します。

## 6. Render デプロイ（本番）

このリポジトリには `render.yaml` を同梱しています。

1. GitHubへpush
2. Renderで「Blueprint」デプロイ（`render.yaml` を利用）
3. 環境変数（secret）は Render 管理画面で入力

ポイント:
- Web起動は `gunicorn`（`ui.server:app`）
- 永続データは `XAP_DATA_DIR=/opt/render/project/src/data` に保存
  - `queue_plan.json`
  - `pdf_library/`
  - `tmp_uploads/`
- `config.yaml` はリポジトリ内のため、運用時は値を固定して使う前提です

### Render Cron Job コマンド例

Render上で別途 Cron Job を作成し、以下コマンドを設定します。

```bash
python -m src.x_autopost_tool.main --config config.yaml --slot morning run-once
python -m src.x_autopost_tool.main --config config.yaml --slot noon run-once
python -m src.x_autopost_tool.main --config config.yaml --slot evening run-once
python -m src.x_autopost_tool.main --config config.yaml --queue-path /opt/render/project/src/data/queue_plan.json refresh-noon-queue
```

時刻メモ（JST基準）:
- 07:00 JST => 22:00 UTC（前日）
- 12:00 JST => 03:00 UTC
- 18:00 JST => 09:00 UTC

## 注意
- X APIの権限プランにより、検索や投稿エンドポイントが使えない場合があります。
- 自動投稿は誤情報リスクがあるため、最初は `dry_run` で運用してください。
