-- フェーズ3：マクロ指標・ニュース・開示
-- Supabase の SQL Editor に貼り付けて実行する（"Run and enable RLS" を選んでよい）。

-- ============================================================
-- マクロ指標（指数・為替・金利など）
-- ============================================================
create table if not exists macro_meta (
  series_id   text primary key,          -- 'yf:^GSPC', 'fred:DGS10'
  label       text not null,             -- 'S&P500'
  category    text not null,             -- '株価指数' / '為替' / '金利' / '商品' / '変動率'
  unit        text,                      -- '円', '%', 'pt'
  source      text not null,             -- 'yfinance' / 'FRED'
  sort_order  int not null default 0,
  updated_at  timestamptz not null default now()
);

create table if not exists macro_series (
  series_id  text not null references macro_meta(series_id) on delete cascade,
  date       date not null,
  value      double precision not null,
  primary key (series_id, date)
);

-- ============================================================
-- ニュース（見出しとリンクのみ。本文は保存しない）
-- ============================================================
create table if not exists news (
  id            text primary key,         -- URL のハッシュ
  source        text not null,            -- 'Yahoo!ニュース 経済' など
  title         text not null,
  url           text not null,
  published_at  timestamptz,
  fetched_at    timestamptz not null default now()
);
create index if not exists news_published_idx on news (published_at desc);

-- ============================================================
-- 開示（EDINET）
-- ============================================================
create table if not exists disclosures (
  id            text primary key,         -- 'edinet:S100XXXX'
  code          text not null references securities(code) on delete cascade,
  source        text not null,            -- 'EDINET'
  doc_type      text,                     -- '有価証券報告書' など
  title         text not null,
  submitted_at  timestamptz,
  url           text not null
);
create index if not exists disclosures_code_idx on disclosures (code, submitted_at desc);
create index if not exists disclosures_submitted_idx on disclosures (submitted_at desc);

create or replace view v_disclosures
with (security_invoker = true) as
select d.*, m.name
from disclosures d
join securities m using (code);

-- ============================================================
-- RLS：許可ユーザーだけ読み取り可
-- ============================================================
do $$
declare t text;
begin
  foreach t in array array['macro_meta','macro_series','news','disclosures'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists "allowed users can read" on %I', t);
    execute format(
      'create policy "allowed users can read" on %I for select to authenticated using (public.is_allowed_user())', t);
  end loop;
end $$;

revoke all on macro_meta, macro_series, news, disclosures, v_disclosures from anon;
