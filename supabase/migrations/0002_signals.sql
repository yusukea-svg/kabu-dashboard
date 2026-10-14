-- フェーズ2：シグナルと場中更新
-- Supabase の SQL Editor に貼り付けて実行する（"Run and enable RLS" を選んでよい）。

-- ============================================================
-- シグナル（同じ銘柄・種類・時間軸・日付は1件だけ = 重複通知しない）
-- ============================================================
create table if not exists signals (
  id          bigint generated always as identity primary key,
  code        text not null references securities(code) on delete cascade,
  kind        text not null,              -- 'golden_cross_25_75' など（config/signals.yaml の id）
  timeframe   text not null check (timeframe in ('daily','intraday')),
  trade_date  date not null,
  detail      jsonb,
  notified_at timestamptz,
  created_at  timestamptz not null default now(),
  unique (code, kind, timeframe, trade_date)
);
create index if not exists signals_date_idx on signals (trade_date desc);

alter table signals enable row level security;
drop policy if exists "allowed users can read" on signals;
create policy "allowed users can read" on signals
  for select to authenticated using (public.is_allowed_user());

create or replace view v_signals
with (security_invoker = true) as
select s.*, m.name
from signals s
join securities m using (code);

revoke all on signals, v_signals from anon;

-- ============================================================
-- 場中の現在値をまとめて更新する（バッチの service キー専用）
-- ============================================================
create or replace function public.update_last_prices(rows jsonb)
returns integer
language sql
security definer
set search_path = public
as $$
  with u as (
    update snapshots s
       set last_price    = (r ->> 'last_price')::real,
           last_price_at = (r ->> 'last_price_at')::timestamptz,
           updated_at    = now()
      from jsonb_array_elements(rows) as r
     where s.code = r ->> 'code'
    returning 1
  )
  select count(*)::int from u;
$$;
revoke execute on function public.update_last_prices(jsonb) from public, anon, authenticated;
grant execute on function public.update_last_prices(jsonb) to service_role;
