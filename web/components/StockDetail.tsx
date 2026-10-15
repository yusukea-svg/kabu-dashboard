"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { changeClass, fmtDateTime, fmtNum, fmtPct, fmtPrice, fmtShares, fmtYen } from "@/lib/format";
import { supabase } from "@/lib/supabase";
import type { DailyBar, Snapshot } from "@/lib/types";
import DisclosureList from "./DisclosureList";
import SignalList from "./SignalList";
import StockChart, { type Overlays } from "./StockChart";

const OVERLAY_LABELS: [keyof Overlays, string][] = [
  ["sma", "移動平均"],
  ["bb", "ボリンジャー"],
  ["volume", "出来高"],
  ["rsi", "RSI"],
  ["macd", "MACD"],
];

export default function StockDetail() {
  const code = useSearchParams().get("code") ?? "";
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [bars, setBars] = useState<DailyBar[] | null>(null);
  const [error, setError] = useState("");
  const [overlays, setOverlays] = useState<Overlays>({ sma: true, bb: false, volume: true, rsi: true, macd: false });

  useEffect(() => {
    if (!code) return;
    supabase!
      .from("v_snapshots")
      .select("*")
      .eq("code", code)
      .maybeSingle()
      .then(({ data, error }) => (error ? setError(error.message) : setSnap(data as Snapshot | null)));
    supabase!
      .from("daily_prices")
      .select("date,open,high,low,close,volume")
      .eq("code", code)
      .order("date", { ascending: true })
      .limit(1000)
      .then(({ data, error }) => (error ? setError(error.message) : setBars((data ?? []) as DailyBar[])));
  }, [code]);

  if (!code) return <p>銘柄コードが指定されていません。</p>;

  return (
    <section>
      <p>
        <Link href="/">← 一覧へ</Link>
      </p>
      <h2 className="title">
        <span className="code">{code}</span> {snap?.name ?? ""}
      </h2>
      {snap && (
        <>
          <div className="quote">
            <span className="big">{fmtPrice(snap.last_price ?? snap.close)}</span>
            <span className={`pct ${changeClass(snap.change_pct)}`}>{fmtPct(snap.change_pct)}</span>
            <span className="muted small">
              {snap.last_price_at ? `場中 ${fmtDateTime(snap.last_price_at)}（約20分遅延）` : `${snap.as_of} 終値`}
            </span>
          </div>
          <p className="muted small">
            {snap.market} / {snap.sector33}
            {snap.in_universe ? " / ユニバース" : ""}
            {snap.intraday_rank ? ` / 場中更新対象 #${snap.intraday_rank}` : ""}
          </p>
        </>
      )}

      <div className="chips">
        {OVERLAY_LABELS.map(([k, label]) => (
          <button
            key={k}
            className={`chip ${overlays[k] ? "on" : ""}`}
            onClick={() => setOverlays((o) => ({ ...o, [k]: !o[k] }))}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="error">読み込みに失敗しました: {error}</p>}
      {!bars && !error && <p className="muted center">読み込み中…</p>}
      {bars && bars.length === 0 && <p className="muted">日足データがありません。</p>}
      {bars && bars.length > 0 && <StockChart bars={bars} overlays={overlays} />}

      {snap && (
        <dl className="stats">
          <dt>出来高</dt><dd>{fmtShares(snap.volume)}</dd>
          <dt>20日平均出来高</dt><dd>{fmtShares(snap.avg_volume20)}</dd>
          <dt>20日平均売買代金</dt><dd>{fmtYen(snap.avg_value20)}円</dd>
          <dt>SMA 5 / 25</dt><dd>{fmtPrice(snap.sma5)} / {fmtPrice(snap.sma25)}</dd>
          <dt>SMA 75 / 200</dt><dd>{fmtPrice(snap.sma75)} / {fmtPrice(snap.sma200)}</dd>
          <dt>RSI(14)</dt><dd>{fmtNum(snap.rsi14)}</dd>
          <dt>MACD / シグナル</dt><dd>{fmtNum(snap.macd, 2)} / {fmtNum(snap.macd_signal, 2)}</dd>
          <dt>BB 上限 / 下限</dt><dd>{fmtPrice(snap.bb_upper)} / {fmtPrice(snap.bb_lower)}</dd>
          <dt>データ更新</dt><dd>{fmtDateTime(snap.updated_at)}</dd>
        </dl>
      )}

      <SignalList code={code} />
      <DisclosureList code={code} />
    </section>
  );
}
