-- 日本株 情報ダッシュボード 初期スキーマ（フェーズ1）
-- Supabase の SQL Editor に貼り付けて実行する。

-- ============================================================
-- 閲覧を許可するユーザー（自分のメールアドレスだけを入れる）
-- ============================================================
create table if not exists app_allowed_users (
  email text primary key
);
alter table app_allowed_users enable row level security;
-- ポリシーを作らない = API からは読み書き不可（SQL Editor / service キーのみ）

create or replace function public.is_allowed_user()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from app_allowed_users
    where lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;
revoke all on function public.is_allowed_user() from public;
grant execute on function public.is_allowed_user() to authenticated;

-- ============================================================
-- 銘柄マスタ
-- ============================================================
create table if not exists securities (
  code        text primary key,           -- '7203', '130A'
  name        text not null,
  market      text,
  sector33    text,
  sector17    text,
  scale       text,
  is_active   boolean not null default true,
  updated_at  timestamptz not null default now()
);

-- ============================================================
-- 日足（調整済み。保持は約300営業日）
-- ============================================================
create table if not exists daily_prices (
  code    text not null references securities(code) on delete cascade,
  date    date not null,
  open    real,
  high    real,
  low     real,
  close   real,
  volume  bigint,
  source  smallint not null default 1,    -- 1=yfinance, 2=jquants
  primary key (code, date)
);
create index if not exists daily_prices_date_idx on daily_prices (date);

-- ============================================================
-- 最新スナップショット（一覧表示用・1銘柄1行）
-- ============================================================
create table if not exists snapshots (
  code           text primary key references securities(code) on delete cascade,
  as_of          date not null,
  close          real,
  change_pct     real,
  volume         bigint,
  avg_volume20   real,
  avg_value20    real,
  sma5 real, sma25 real, sma75 real, sma200 real,
  ema12 real, ema26 real,
  rsi14 real,
  macd real, macd_signal real, macd_hist real,
  bb_upper real, bb_mid real, bb_lower real,
  in_universe    boolean not null default false,
  intraday_rank  int,                     -- null = 場中更新の対象外
  last_price     real,                    -- 場中更新値（フェーズ2）
  last_price_at  timestamptz,
  updated_at     timestamptz not null default now()
);
create index if not exists snapshots_universe_idx on snapshots (in_universe, avg_value20 desc);

-- ============================================================
-- バッチ実行履歴（画面の「最終更新時刻」の元）
-- ============================================================
create table if not exists job_runs (
  id           bigint generated always as identity primary key,
  job          text not null,
  started_at   timestamptz not null,
  finished_at  timestamptz,
  status       text not null check (status in ('running','ok','partial','failed','skipped')),
  ok_count     int,
  fail_count   int,
  message      text
);
create index if not exists job_runs_job_idx on job_runs (job, started_at desc);

-- ============================================================
-- 一覧用ビュー（呼び出したユーザーの権限で RLS を評価）
-- ============================================================
create or replace view v_snapshots
with (security_invoker = true) as
select s.*, m.name, m.market, m.sector33
from snapshots s
join securities m using (code);

-- ============================================================
-- RLS：許可ユーザーだけ読み取り可。書き込みは service キー（RLSを無視）のみ
-- ============================================================
do $$
declare t text;
begin
  foreach t in array array['securities','daily_prices','snapshots','job_runs'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists "allowed users can read" on %I', t);
    execute format(
      'create policy "allowed users can read" on %I for select to authenticated using (public.is_allowed_user())', t);
  end loop;
end $$;

-- 匿名ユーザーには何も見せない
revoke all on securities, daily_prices, snapshots, job_runs, v_snapshots from anon;
