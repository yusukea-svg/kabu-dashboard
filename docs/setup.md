# セットアップと動作確認（フェーズ1）

所要時間の目安：30〜45分。すべて無料枠・クレジットカード登録なしで進められます。

## 0. 手元の道具

| 道具 | 用途 | 入れ方 |
|------|------|--------|
| uv | Python と依存関係の管理 | https://docs.astral.sh/uv/ （このMacには `~/.local/bin/uv` に導入済み） |
| Node.js 24 | フロントエンド | https://nodejs.org/ （このMacには `~/.local/node` に導入済み） |
| git | GitHub へのアップロード | macOS の「コマンドライン・デベロッパツール」（`xcode-select --install`）か GitHub Desktop |

ターミナルで使うには `~/.zshrc` に次を1行足して、ターミナルを開き直します。

```bash
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"
```

## 1. Supabase を用意する

1. https://supabase.com で無料アカウントを作り、New project を作成（リージョンは Tokyo 推奨）。
2. **SQL Editor** で `supabase/migrations/0001_init.sql` の中身を貼り付けて Run。
3. 続けて、自分のメールアドレスを閲覧許可リストに入れる（SQL Editor で実行）。
   ```sql
   insert into app_allowed_users (email) values ('自分のメールアドレス');
   ```
4. **Authentication → Users → Add user → Create new user** で同じメールアドレスのユーザーを作成。
5. **Authentication → Sign In / Providers**（旧 Settings）で **Allow new users to sign up をオフ**。
   → 自分以外はログインリンクを要求できなくなります。
6. **Authentication → URL Configuration** の Site URL / Redirect URLs に次を追加。
   - `http://localhost:3000`
   - （デプロイ後）`https://<あなたのVercelのURL>`
7. **Project Settings → API Keys** で次の値を控える。
   - Project URL
   - anon（または publishable）キー → フロント用（公開されても RLS で守られる）
   - service_role（または secret）キー → バッチ用（**絶対に公開しない**）

## 2. 環境変数を置く（コミットされません）

リポジトリ直下に `.env`：

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=（service_role / secret キー）
```

`web/.env.local`：

```
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=（anon / publishable キー）
```

## 3. バッチを動かす

```bash
cd batch
uv sync
uv run pytest -q                              # テスト（14件）
uv run kabu-batch daily --dry-run --limit 40  # 保存せずに取得だけ試す
uv run kabu-batch daily --full --limit 40     # 40銘柄だけ Supabase に保存
uv run kabu-batch daily --full --force        # 全銘柄を保存（約5〜10分）
```

確認ポイント：
- 最後に `[daily] ok: 取得成功 … / ユニバース … / 場中対象 …` と出る
- Supabase の **Table Editor** で `securities`（約3,700行）、`snapshots`、`daily_prices`、`job_runs` に行が入っている

`--full` は初回だけ使います（全期間の日足を書き込み、銘柄一覧も取り直す）。以降は `daily` だけで直近10日分を上書きします。

## 4. 画面を動かす

```bash
cd web
npm install
npm test        # 指標計算が Python 版と一致するかのテスト
npm run dev     # http://localhost:3000
```

確認ポイント：
- ログイン画面 → 自分のメールアドレスを入れる → 届いたリンクを開くと一覧が出る
- 「ユニバース／全銘柄」の切り替え、検索、並べ替え、条件チップ（RSI≤30 など）が効く
- 銘柄をタップするとチャート（ローソク足・移動平均・出来高・RSI、MACD/ボリンジャーは切り替え）が出る
- 画面上部に「日次更新: 日時」、下部に「投資助言ではありません」が出る
- 別のメールアドレスではログインリンクが送れない

## 5. （任意）Vercel に公開する

1. GitHub にリポジトリを作成（Public）して push。
   push 前に `git status` で `.env` や CSV が含まれていないことを確認。
2. https://vercel.com で GitHub 連携 → Import → **Root Directory を `web`** に設定。
3. Environment Variables に `NEXT_PUBLIC_SUPABASE_URL` と `NEXT_PUBLIC_SUPABASE_ANON_KEY` を登録して Deploy。
4. 発行された URL を Supabase の Redirect URLs に追加（手順1-6）。

フェーズ2で GitHub Actions による自動更新（12時・15時・18時）と Discord 通知を追加します。

---

# フェーズ2：自動更新・通知・スマホ表示

## 6. DBにシグナル用テーブルを追加する

Supabase の SQL Editor で `supabase/migrations/0002_signals.sql` を実行（"Run and enable RLS" を選んでよい）。

## 7. Discord の通知先を作る

1. Discord アプリを入れてログインし、左の「＋」→「オリジナルの作成」→「自分と友達のため」で自分専用のサーバーを作る。
2. 通知を流したいチャンネル（例: `#一般`）の ⚙（チャンネルの編集）→ **連携サービス** → **ウェブフック** → **新しいウェブフック**。
3. **ウェブフックURLをコピー**。これは秘密情報（知っている人は誰でも投稿できる）なので、チャットやコードに貼らない。
4. 手元で試す場合は、リポジトリ直下の `.env` に `DISCORD_WEBHOOK_URL=（コピーしたURL）` を追記。
5. スマホの Discord アプリでそのサーバーの通知を「すべてのメッセージ」にしておく。

## 8. GitHub にリポジトリを作って push する

1. git を入れる：ターミナルで `xcode-select --install`（または GitHub Desktop）。
2. https://github.com/new で **Public** のリポジトリ（例: `kabu-dashboard`）を作成。README などは追加しない。
3. push 前に、秘密情報やデータが入らないことを確認：
   ```bash
   git status --ignored
   ```
   `.env` と `web/.env.local` が「Ignored files」側に出ていればOK。
4. 画面に出る手順（`git init` → `git add .` → `git commit` → `git remote add` → `git push`）で push。

## 9. GitHub Secrets を登録する

リポジトリの **Settings → Secrets and variables → Actions**。

| 種類 | 名前 | 値 |
|------|------|----|
| Secret | `SUPABASE_URL` | Supabase の Project URL |
| Secret | `SUPABASE_SERVICE_KEY` | secret キー（`sb_secret_...`） |
| Secret | `DISCORD_WEBHOOK_URL` | 手順7のURL |
| Variable | `DASHBOARD_URL` | （手順10の後）Vercel のURL。通知にリンクが付く |

## 10. Vercel に公開してスマホで見る

1. https://vercel.com に GitHub でログイン → **Add New → Project** → リポジトリを Import。
2. **Root Directory** を `web` に変更。
3. **Environment Variables** に `NEXT_PUBLIC_SUPABASE_URL` と `NEXT_PUBLIC_SUPABASE_ANON_KEY`（publishable キー）を登録して **Deploy**。
4. 発行されたURL（`https://xxxx.vercel.app`）を、
   - Supabase の **Authentication → URL Configuration → Redirect URLs** に `https://xxxx.vercel.app/**` として追加
   - GitHub の Variable `DASHBOARD_URL` に登録
5. スマホのブラウザでURLを開いてログイン（ログインリンクのメールはスマホで開く）。
   Safari の共有ボタン →「ホーム画面に追加」でアプリのように使える。

## 11. 動作確認

GitHub の **Actions** タブで、各ワークフローを **Run workflow** から手動実行できる。

| ワークフロー | 確認すること |
|---|---|
| `ci` | push すると自動で走る。緑になればテスト・ビルドOK |
| `daily`（force にチェック） | 成功し、ダッシュボードの「日次更新」時刻が更新される。シグナルがあれば Discord に届く |
| `intraday`（force にチェック） | 場中（9:00〜15:30）に実行すると「場中更新」時刻と現在値が更新される |
| `bench` | Discord に「取得件数の実測」の表が届く。数日・複数の時間帯で試す |

以降は平日 12:05 / 15:05（場中）と 18:05（日次、予備 20:35）に自動で動く。
GitHub の cron は数分〜数十分遅れることがある。

---

# フェーズ3：マクロ指標・ニュース・開示

## 12. DBにテーブルを追加する

Supabase の SQL Editor で `supabase/migrations/0003_market_info.sql` を実行。

## 13. APIキーを取る（どちらも無料・未設定ならその部分だけスキップされる）

| キー | 用途 | 取り方 |
|------|------|--------|
| `FRED_API_KEY` | 米国金利（10年・2年・FF金利） | https://fredaccount.stlouisfed.org でアカウント作成 → **API Keys** → **Request API Key**（用途は「personal dashboard」など） |
| `EDINET_API_KEY` | 有価証券報告書・臨時報告書などの一覧 | https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1 でアカウント作成（電話番号の認証あり）→ 表示される **APIキー** |

取ったキーはリポジトリ直下の `.env` に `FRED_API_KEY=...` / `EDINET_API_KEY=...` として追記し、
GitHub の Secrets にも同じ名前で登録する（`.env` から登録する手順はこちらで実行可能）。

## 14. 動作確認

- 手元：`cd batch && uv run kabu-batch info`（初回の EDINET は過去120日分を読むので2〜3分）
- GitHub：Actions → **info** → Run workflow
- 画面：上部の **マーケット** に指数・為替・金利のカード、ニュース、直近7日の開示。
  銘柄ページの下に「開示」と、適時開示（決算短信など）を見るための外部リンク。

以降は平日 7:35 / 12:35 / 18:35、土日 9:35 JST に自動更新。

# 決算発表予定の週次通知

毎週月曜 7:05 JST（実際は30分ほど遅れる）に、今週と来週に決算発表する銘柄を日付別に Discord へ送る。
データは JPX「決算発表予定日」の Excel（期末・四半期末の月ごとの一覧）。追加のキーや DB の変更は不要。

- 対象銘柄と1日あたりの件数は `config/sources.yaml` の `earnings`（`scope` / `max_per_day`）で変える。
- 手元：`cd batch && uv run kabu-batch earnings --force`（`--no-notify` で送らずに件数だけ確認）
- GitHub：Actions → **earnings** → Run workflow（force にチェックすると同じ日でももう一度送る）
