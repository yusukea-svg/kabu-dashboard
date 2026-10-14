# 日本株 情報ダッシュボード 設計案 (v0.1 / 2026-10-15)

> 個人の情報整理用ツール。投資助言ではありません。自動売買・銘柄推奨は行いません。

---

## 1. 方針レビュー：懸念点と代替案

### 1-1. 規約面（最重要）

| # | 懸念 | 影響 | 対応案 |
|---|------|------|--------|
| L1 | **公開URLのダッシュボード＝事実上の再配布**。リポジトリにデータを置かなくても、Vercel上で誰でも見られる状態なら Yahoo / JPX / J-Quants のデータを第三者に公開していることになる | 高 | **フロントは必ずログイン必須**にする。Supabase Auth（メールのマジックリンク、サインアップ無効、許可メール1件）＋ 全テーブルRLS。Vercel Hobbyの「パスワード保護」は有料なので使わない |
| L2 | **GitHub Actionsのログ・Artifacts・Cacheは公開リポジトリでは誰でも閲覧可能** | 高 | ログに価格データを出さない（件数・所要時間・エラー種別のみ）。`actions/upload-artifact` と `actions/cache` にデータを載せない |
| L3 | yfinance は Yahoo の非公式クライアント。Yahoo の規約は自動取得・再配布を想定していない（yfinance自体も「個人利用」と明記） | 中 | 個人・非公開・低頻度に限定。取得層を抽象化し、問題が出たら J-Quants（有料Light等）へ差し替え。**ここはグレーである点を許容いただく必要あり** |
| L4 | TDnet には無料の公式APIがない（JPXのTDnet APIは有料）。サイトのスクレイピングは規約上避けるべき | 中 | フェーズ3は **EDINET API（公式・無料・要APIキー）を主**にする。TDnet分は「銘柄コードで検索するリンク」の表示に留める。決算短信の数値が必要になったら J-Quants の財務情報で代替（無料は12週遅延） |
| L5 | ニュースRSSは提供元ごとに「個人利用に限る」等の条件がある | 低〜中 | 見出し＋リンクのみ・本文非保存・ログイン必須で表示。採用するRSSごとに規約を `docs/terms.md` に記録してから追加 |
| L6 | JPXの上場銘柄一覧（data_j.xls）も二次利用は制限あり | 低 | リポジトリにコミットせず、バッチ実行時に取得してDBへ。代替として J-Quants無料の銘柄一覧APIも使える |
| L7 | J-Quants 無料プランは個人利用・再配布不可・12週遅延 | 低 | バックテスト用にローカル/Actionsで取得し、結果（統計値）のみ保存 |

### 1-2. 無料枠での更新頻度

- **GitHub Actions**: 公開リポジトリの標準ランナーは分数無制限。1ジョブ最大6時間。日次＋場中7回/日でも問題なし。
- **cronの遅延・欠落**: 毎時0分台は混雑して数十分遅れたり実行されないことがある。
  - cronは **半端な分（例: :07, :37）** に設定。
  - **日次は2回スケジュール**（18:05 JST が本番、20:35 JST が予備）。処理は冪等（upsert）で、2回目は「当日分が揃っていれば即終了」。
  - 各ジョブは「前回成功以降に欠けた営業日」を自分で補完（キャッチアップ）。
  - 画面に「最終更新時刻」と、一定時間以上古い場合の警告バッジを表示。
- **60日無活動でのスケジュール停止**: 公開リポジトリはコミット等の活動が60日ないと scheduled workflow が全部止まる。keepalive用のscheduled workflowも一緒に止まるため、
  - 日次ジョブ内で「最終コミットから45日以上経過していたら `.github/keepalive` に日付だけを書いてコミット」（データは含まない）。
  - 加えて、DBの `job_runs` が2営業日以上更新されていなければダッシュボードに警告を出す。
- **（任意の代替）時刻精度が欲しい場合**: cron-job.org（無料・カード不要）から GitHub API の `workflow_dispatch` を叩く。最小権限のFine-grained PAT（対象リポジトリの Actions: write のみ）を外部サービスに預けることになる点がトレードオフ。初期はGitHub cronのみで開始し、遅延が気になれば追加を推奨。

### 1-3. データ取得の安定性

- **yfinance のレート制限**: 2024年以降 `Too Many Requests` が頻発しており、GitHub Actions（クラウドIP）からは自宅回線より制限されやすい。
  - 全約3,900銘柄の日次取得は **100〜200銘柄ずつのチャンク＋待機＋指数バックオフ**で行い、失敗分は2回目のスケジュールで再取得。
  - 初回の2年分バックフィルは1回で終わらせず、数日に分けて実行（`workflow_dispatch`で手動）。
  - **場中のN件はローカルではなくActions上で実測する必要がある**（IPが違うと結果が変わる）。`bench` ワークフローで N=100/300/500 を複数日・複数時間帯に試行し、成功率・所要時間・429発生数を記録して報告する。
- **場中データ**: 1時間足（interval=60m）か、当日の日足（期中は暫定のOHLC）を取る2案。当日日足の方が1リクエストあたりの情報が少なく軽いので、まず日足方式→必要なら60m足。
- **分割・併合**: yfinanceは調整済み価格を返すため、分割があると過去値が変わる。前日比で不自然な乖離（例: ±40%超と出来高急変）を検知したら、その銘柄の履歴を再取得して置き換える。
- **pandas-ta**: 新しめのバージョンは Python / NumPy の要求が厳しく、依存トラブルが起きやすい。今回の指標（SMA/EMA/RSI/MACD/BB）は単純なので **pandasで自前実装（数十行）し、テストで pandas-ta と値一致を確認**する案を推奨。
- **祝日判定**: `jpholiday` ＋ 年末年始（12/31〜1/3）を休場扱い。取引時間は 9:00〜11:30 / 12:30〜15:30（2024年11月から大引け15:30）。

### 1-4. DB: Supabase vs 静的JSON/SQLite

| 観点 | Supabase無料 | 静的JSON/SQLite配布 |
|------|-------------|---------------------|
| 非公開化 | Auth＋RLSで簡単 | 公開リポジトリ/公開URLに置けない。非公開の置き場所（R2等）はカード登録が必要なことが多い |
| 容量 | DB 500MB / Storage 1GB | 制限は置き場所次第 |
| 停止 | 7日無アクセスで一時停止 → **日次バッチが書き込むので実質発生しない** | なし |
| 場中更新 | 行単位upsertで軽い | 毎回ファイル全体を再生成 |

→ **Supabaseを推奨**。L1（非公開化）を無料で満たせるのが決め手。

### 1-5. 通知: Discord Webhook を推奨

- LINE Notify は2025年3月に終了済み。LINE Messaging API の無料枠は月200通程度で、場中シグナルだと超える可能性がある。
- Discord Webhook は無料・通数をほぼ気にしなくてよい・スマホアプリでプッシュ通知が届く・実装が数行。Webhook URLはSecretsに保存。

### 1-6. 銘柄ユニバースの初期値（提案）

| 項目 | ユーザー案 | 提案値 | 理由 |
|------|-----------|--------|------|
| 株価 | 100〜5,000円 | 同じ | 5,000円で1単元50万円 |
| 20日平均出来高 | 1万株以上 | **3万株以上** | 1万株だと板が薄く、1時間足が欠けやすい |
| 20日平均売買代金 | なし | **3,000万円以上**（追加） | 株価が低い銘柄で出来高だけ大きいものを除く。実データで分布を見て再調整 |
| 場中対象 | 上位N | 売買代金20日平均の上位N（Nは実測） | — |

すべて `config/universe.yaml` で変更可能にします。

---

## 2. フォルダ構成

```
kabu-dashboard/                 # 新規の公開リポジトリ
├─ .github/workflows/
│  ├─ daily.yml                 # 日次（18:05 本番 / 20:35 予備）+ keepalive
│  ├─ intraday.yml              # 場中（12:05, 15:05 JST）
│  ├─ bench.yml                 # N実測用（手動実行）
│  └─ ci.yml                    # lint / test
├─ batch/                       # Python
│  ├─ pyproject.toml
│  ├─ src/kabu_batch/
│  │  ├─ config.py              # YAML読込・環境変数
│  │  ├─ market_calendar.py     # 営業日・取引時間判定
│  │  ├─ providers/             # ★差し替え可能な取得層
│  │  │  ├─ base.py             # PriceProvider / ListingProvider 等のProtocol
│  │  │  ├─ yfinance_provider.py
│  │  │  ├─ jquants_provider.py # バックテスト用（将来は有料プランに差し替え）
│  │  │  ├─ jpx_listing.py
│  │  │  ├─ edinet.py / fred.py / rss.py
│  │  ├─ indicators.py          # SMA/EMA/RSI/MACD/BB
│  │  ├─ universe.py            # 絞り込み・順位付け
│  │  ├─ signals.py             # GC/DC, RSI閾値 など
│  │  ├─ storage/               # base.py, supabase_store.py, sqlite_store.py(開発用)
│  │  ├─ notify/discord.py
│  │  └─ jobs/                  # daily.py, intraday.py, macro.py, disclosures.py, bench.py
│  └─ tests/
├─ config/
│  ├─ universe.yaml / signals.yaml / sources.yaml
├─ supabase/migrations/0001_init.sql
├─ web/                         # Next.js（静的エクスポート）+ PWA
│  ├─ app/  (一覧, 銘柄詳細, マクロ, 開示, 設定)
│  ├─ lib/  (supabaseクライアント, 指標計算TS版)
│  └─ public/manifest.webmanifest, アイコン
├─ docs/  DESIGN.md, terms.md（データ提供元ごとの規約メモ）, runbook.md
├─ .env.example                 # キー名のみ。値は書かない
└─ .gitignore                   # .env*, *.sqlite, data/, *.parquet, *.csv, .venv, node_modules 等
```

- フロントは `output: 'export'` の静的サイトにし、ブラウザから Supabase を直接読む（RLSで保護）。Vercelのサーバー機能をほぼ使わないので枠を消費しにくく、**Capacitorでそのまま包める**。
- データを置くディレクトリ（`data/` 等）は丸ごと `.gitignore`。CIで「CSV/Parquet/SQLiteがコミットされていないか」をチェック。

---

## 3. DBスキーマ（Supabase / Postgres）

```sql
-- 銘柄マスタ（JPX一覧）
create table securities (
  code        text primary key,          -- '7203'
  name        text not null,
  market      text,                      -- プライム/スタンダード/グロース
  sector33    text,
  sector17    text,
  scale       text,                      -- TOPIX規模区分
  is_active   boolean default true,
  updated_at  timestamptz default now()
);

-- 日足（全銘柄・約300営業日保持。価格はreal=4byteで容量節約）
create table daily_prices (
  code    text  not null references securities(code),
  date    date  not null,
  open    real, high real, low real, close real,
  volume  bigint,
  source  smallint not null default 1,   -- 1=yfinance, 2=jquants ...
  primary key (code, date)
);

-- 場中（対象N銘柄・直近5営業日のみ保持）
create table intraday_prices (
  code  text not null,
  ts    timestamptz not null,
  open real, high real, low real, close real, volume bigint,
  primary key (code, ts)
);

-- 一覧表示用の最新スナップショット（1銘柄1行。一覧はこれだけ読めばよい）
create table snapshots (
  code           text primary key references securities(code),
  as_of          date not null,
  close          real, change_pct real, volume bigint,
  avg_volume20   real, avg_value20 real,
  sma5 real, sma25 real, sma75 real, sma200 real,
  ema12 real, ema26 real,
  rsi14 real, macd real, macd_signal real, macd_hist real,
  bb_upper real, bb_mid real, bb_lower real,
  in_universe    boolean not null default false,
  intraday_rank  int,                     -- nullなら場中対象外
  last_price     real,                    -- 場中更新値
  last_price_at  timestamptz,
  updated_at     timestamptz default now()
);

-- シグナル（重複通知防止のunique）
create table signals (
  id          bigint generated always as identity primary key,
  code        text not null,
  kind        text not null,              -- 'golden_cross_25_75', 'rsi_below_30' ...
  timeframe   text not null,              -- 'daily' | 'intraday'
  trade_date  date not null,
  detail      jsonb,
  notified_at timestamptz,
  created_at  timestamptz default now(),
  unique (code, kind, timeframe, trade_date)
);

-- フェーズ3
create table macro_series (series_id text, date date, value double precision, primary key (series_id, date));
create table macro_meta   (series_id text primary key, label text, source text, unit text, updated_at timestamptz);
create table disclosures  (id text primary key, code text, source text, doc_type text, title text, submitted_at timestamptz, url text);
create table news         (id text primary key, source text, title text, url text, published_at timestamptz);

-- フェーズ4
create table backtest_runs (id bigint generated always as identity primary key, strategy text, params jsonb,
                            period_from date, period_to date, stats jsonb, created_at timestamptz default now());

-- 実行履歴（画面の「最終更新時刻」の元）
create table job_runs (
  id          bigint generated always as identity primary key,
  job         text not null,              -- 'daily' | 'intraday' | 'macro' ...
  started_at  timestamptz not null,
  finished_at timestamptz,
  status      text not null,              -- 'ok' | 'partial' | 'failed' | 'skipped'
  ok_count int, fail_count int,
  message     text
);
```

- **RLS**: 全テーブルで有効化。`select` は `auth.jwt()->>'email' = 許可メール` のみ許可。書き込みはバッチ（service_roleキー＝GitHub Secrets）だけ。
- 指標の時系列はDBに持たず、**チャートはブラウザで日足から計算**（TS実装。Python版とテストで一致を確認）。DBは最新値だけ（snapshots）。

---

## 4. バッチの流れ

### 日次（`daily.yml`、平日18:05 JST、予備20:35 JST）
1. 営業日判定 → 休場なら `skipped` を記録して終了
2. 当日分が既に揃っていれば終了（2回目の実行用）
3. 銘柄一覧の更新（7日以上古ければJPXから再取得）
4. 全銘柄の日足取得（直近5日分、チャンク＋バックオフ。失敗銘柄は記録）
5. `daily_prices` にupsert、分割検知→該当銘柄の履歴を再取得
6. 指標計算 → `snapshots` 更新
7. ユニバース絞り込み → `in_universe` / `intraday_rank` 更新
8. シグナル判定 → `signals` に挿入（重複はunique制約で無視）→ 新規分をDiscord通知
9. 古い `intraday_prices` / 300営業日超の `daily_prices` を削除
10. `job_runs` に結果記録。失敗率が閾値超ならDiscordに警告
11. keepalive（最終コミットから45日以上なら日付だけコミット）

### 場中（`intraday.yml`、平日 12:05・15:05 JST）
1. 営業日・取引時間判定
2. `intraday_rank` 上位N銘柄を取得 → `intraday_prices` / `snapshots.last_price` 更新
3. 場中シグナル（例: RSI閾値を当日暫定値で判定）→ 通知
4. `job_runs` 記録
- `concurrency` で同時実行を防止。遅れて取引時間外に起動したら何もしない。

### cron（UTCで記述）
```
daily:    5 9 * * 1-5    /  35 11 * * 1-5   # 18:05 / 20:35 JST
intraday: 5 3,6 * * 1-5                    # 12:05 / 15:05 JST
```

---

## 5. 無料枠の使用量見積もり

| サービス | 上限（無料） | 見積もり | 余裕 |
|----------|-------------|---------|------|
| Supabase DB | 500MB | 日足 3,900銘柄×300日≒117万行×約110B（索引込）≒ **約130MB**。他テーブル合計 数十MB → **合計 約150〜200MB** | ○ |
| Supabase 転送量 | 5GB/月 | 一覧 約1MB/回（絞り込みでさらに減）、チャート 約15KB/回。1日50回見ても 約1.5GB/月 | ○ |
| Supabase 一時停止 | 7日無アクセス | 日次バッチが毎営業日書き込むので発生しない（GW・年末年始も7日未満）。念のため休場日も軽いpingを入れる | ○ |
| GitHub Actions | 公開リポジトリは無制限 | 日次 15〜30分×2、場中 3〜5分×8/日 | ○ |
| Vercel Hobby | 帯域100GB/月 等 | 静的サイトのみ。数百MB/月 | ○ |
| Discord Webhook | レート制限のみ | 1日数〜数十通 | ○ |
| EDINET / FRED | APIキー（無料） | 1日数十リクエスト | ○ |

全期間のバックテスト用データ（J-Quants 2年分）はDBに入れず、実行時取得＋結果だけ保存するので容量に影響しません。

---

## 6. 未確定事項（ユーザー確認待ち）

- 既存シミュレーターは無し → 新規構築（決定）
- 規約L3（yfinance）→ 許容（決定）
- 更新時刻 → 12時・15時・18時（決定）
3. ユニバース初期値（出来高3万株・売買代金3,000万円の追加）
4. ログイン方式（Supabaseマジックリンク）、通知（Discord）でよいか

---

## 7. 実装時の変更点（2026-10-15）

- 更新時刻は 12:05 / 15:05（場中）・18:05（日次）・20:35（日次の予備）に変更。
- 場中は1時間足ではなく「当日の暫定日足」を取得する方式にした。`intraday_prices` テーブルは作らず、
  `snapshots.last_price` / `last_price_at` だけを更新する（容量節約・処理が単純）。18時の日次で確定値に置き換える。
- JPXの銘柄一覧は `.xlsx` に変わっていたため、掲載ページからリンクを探して取得する方式にした。
- 実測（ローカル回線）：全3,702銘柄の日足取得は約4〜5分・失敗0件。初期条件でユニバースは1,756銘柄。
- シグナルは `config/signals.yaml` で定義。記録はユニバース全体、通知は既定で場中更新の対象（上位N件）だけ。
