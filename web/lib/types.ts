export type Snapshot = {
  code: string;
  name: string;
  market: string | null;
  sector33: string | null;
  as_of: string;
  close: number | null;
  change_pct: number | null;
  volume: number | null;
  avg_volume20: number | null;
  avg_value20: number | null;
  sma5: number | null;
  sma25: number | null;
  sma75: number | null;
  sma200: number | null;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  in_universe: boolean;
  intraday_rank: number | null;
  last_price: number | null;
  last_price_at: string | null;
  updated_at: string;
};

export type DailyBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type JobRun = {
  job: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "partial" | "failed" | "skipped";
  ok_count: number | null;
  fail_count: number | null;
  message: string | null;
};

export type Signal = {
  id: number;
  code: string;
  name: string;
  kind: string;
  timeframe: "daily" | "intraday";
  trade_date: string;
  detail: { label?: string; close?: number; [k: string]: unknown } | null;
  notified_at: string | null;
};
