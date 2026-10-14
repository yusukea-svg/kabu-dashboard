"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtPrice } from "@/lib/format";
import { supabase } from "@/lib/supabase";
import type { Signal } from "@/lib/types";

const DAYS = 7;

/** 直近のシグナル（日付ごと・種類ごと）。code を渡すとその銘柄だけ。 */
export default function SignalList({ code }: { code?: string }) {
  const [rows, setRows] = useState<Signal[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const since = new Date(Date.now() - (code ? 90 : DAYS) * 864e5).toISOString().slice(0, 10);
    let q = supabase!
      .from("v_signals")
      .select("id,code,name,kind,timeframe,trade_date,detail,notified_at")
      .gte("trade_date", since)
      .order("trade_date", { ascending: false })
      .order("code")
      .limit(1000);
    if (code) q = q.eq("code", code);
    q.then(({ data }) => setRows((data ?? []) as Signal[]));
  }, [code]);

  if (!rows) return null;
  if (rows.length === 0) {
    return code ? null : <p className="muted small">直近{DAYS}日のシグナルはありません。</p>;
  }

  // 同じ日・銘柄・種類で日次と場中の両方がある場合は日次（確定値）を優先して1つにまとめる
  const seen = new Map<string, Signal>();
  for (const r of rows) {
    const key = `${r.trade_date}|${r.code}|${r.kind}`;
    const prev = seen.get(key);
    if (!prev || (prev.timeframe === "intraday" && r.timeframe === "daily")) seen.set(key, r);
  }
  const items = [...seen.values()];
  const byDate = new Map<string, Signal[]>();
  for (const r of items) byDate.set(r.trade_date, [...(byDate.get(r.trade_date) ?? []), r]);
  const dates = [...byDate.keys()];
  const shownDates = code || open ? dates : dates.slice(0, 1);

  return (
    <section className="signals">
      <h3>{code ? "この銘柄のシグナル（90日）" : "シグナル"}</h3>
      {shownDates.map((d) => (
        <div key={d}>
          <p className="muted small">{d}</p>
          <ul>
            {byDate.get(d)!.map((r) => (
              <li key={r.id}>
                <span className={`tag ${r.timeframe}`}>{r.timeframe === "daily" ? "確定" : "場中"}</span>
                <span className="label">{r.detail?.label ?? r.kind}</span>
                {!code && (
                  <Link href={`/stock/?code=${encodeURIComponent(r.code)}`}>
                    {r.code} {r.name}
                  </Link>
                )}
                <span className="price">{fmtPrice(r.detail?.close)}</span>
                {r.notified_at && <span title="Discordに通知済み">🔔</span>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {!code && dates.length > 1 && (
        <button className="link" onClick={() => setOpen((o) => !o)}>
          {open ? "閉じる" : `過去${DAYS}日分を表示`}
        </button>
      )}
    </section>
  );
}
