"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { changeClass, fmtNum, fmtPct, fmtPrice, fmtYen } from "@/lib/format";
import { fetchAll, supabase } from "@/lib/supabase";
import type { Snapshot } from "@/lib/types";

const COLUMNS =
  "code,name,market,sector33,as_of,close,change_pct,volume,avg_volume20,avg_value20," +
  "sma5,sma25,sma75,sma200,rsi14,macd,macd_signal,macd_hist,bb_upper,bb_lower," +
  "in_universe,intraday_rank,last_price,last_price_at,updated_at";

type SortKey = "avg_value20" | "change_pct" | "rsi14" | "close" | "code";
const SORTS: { key: SortKey; label: string; desc: boolean }[] = [
  { key: "avg_value20", label: "売買代金(20日平均)", desc: true },
  { key: "change_pct", label: "前日比 上昇", desc: true },
  { key: "change_pct", label: "前日比 下落", desc: false },
  { key: "rsi14", label: "RSI 低い順", desc: false },
  { key: "rsi14", label: "RSI 高い順", desc: true },
  { key: "close", label: "株価 安い順", desc: false },
  { key: "code", label: "コード順", desc: false },
];

type Filter = "rsi_low" | "rsi_high" | "above_sma25" | "trend_up" | "bb_low" | "intraday";
const FILTERS: { key: Filter; label: string; test: (s: Snapshot) => boolean }[] = [
  { key: "rsi_low", label: "RSI≤30", test: (s) => s.rsi14 != null && s.rsi14 <= 30 },
  { key: "rsi_high", label: "RSI≥70", test: (s) => s.rsi14 != null && s.rsi14 >= 70 },
  { key: "above_sma25", label: "25日線より上", test: (s) => s.close != null && s.sma25 != null && s.close > s.sma25 },
  {
    key: "trend_up",
    label: "5>25>75日線",
    test: (s) => s.sma5 != null && s.sma25 != null && s.sma75 != null && s.sma5 > s.sma25 && s.sma25 > s.sma75,
  },
  { key: "bb_low", label: "BB下限割れ", test: (s) => s.close != null && s.bb_lower != null && s.close < s.bb_lower },
  { key: "intraday", label: "場中更新対象", test: (s) => s.intraday_rank != null },
];

const PAGE = 100;

export default function StockList() {
  const [scope, setScope] = useState<"universe" | "all">("universe");
  const [rows, setRows] = useState<Snapshot[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [sortIdx, setSortIdx] = useState(0);
  const [filters, setFilters] = useState<Set<Filter>>(new Set());
  const [shown, setShown] = useState(PAGE);

  useEffect(() => {
    setRows(null);
    setError("");
    fetchAll<Snapshot>((from, to) => {
      let q = supabase!.from("v_snapshots").select(COLUMNS).order("code").range(from, to);
      if (scope === "universe") q = q.eq("in_universe", true);
      return q as unknown as PromiseLike<{ data: Snapshot[] | null; error: { message: string } | null }>;
    })
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [scope]);

  const visible = useMemo(() => {
    if (!rows) return [];
    const q = query.trim().toLowerCase();
    const sort = SORTS[sortIdx];
    const active = FILTERS.filter((f) => filters.has(f.key));
    return rows
      .filter((s) => !q || s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
      .filter((s) => active.every((f) => f.test(s)))
      .sort((a, b) => {
        const av = a[sort.key];
        const bv = b[sort.key];
        if (av == null) return 1;
        if (bv == null) return -1;
        const c = av < bv ? -1 : av > bv ? 1 : 0;
        return sort.desc ? -c : c;
      });
  }, [rows, query, sortIdx, filters]);

  useEffect(() => setShown(PAGE), [query, sortIdx, filters, scope]);

  const toggle = (f: Filter) =>
    setFilters((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });

  return (
    <section>
      <div className="controls">
        <div className="seg" role="group" aria-label="対象">
          <button className={scope === "universe" ? "on" : ""} onClick={() => setScope("universe")}>
            ユニバース
          </button>
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>
            全銘柄
          </button>
        </div>
        <input
          type="search"
          placeholder="コード・銘柄名で検索"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={sortIdx} onChange={(e) => setSortIdx(Number(e.target.value))} aria-label="並べ替え">
          {SORTS.map((s, i) => (
            <option key={i} value={i}>
              {s.label}
            </option>
          ))}
        </select>
        <div className="chips">
          {FILTERS.map((f) => (
            <button key={f.key} className={`chip ${filters.has(f.key) ? "on" : ""}`} onClick={() => toggle(f.key)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error">読み込みに失敗しました: {error}</p>}
      {!rows && !error && <p className="muted center">読み込み中…</p>}
      {rows && (
        <p className="muted small">
          {visible.length.toLocaleString()} 件 / {rows.length.toLocaleString()} 件
          {rows[0] && `（${rows[0].as_of} 時点）`}
        </p>
      )}

      <ul className="stocks">
        {visible.slice(0, shown).map((s) => (
          <li key={s.code}>
            <Link href={`/stock/?code=${encodeURIComponent(s.code)}`}>
              <div className="row1">
                <span className="code">{s.code}</span>
                <span className="name">{s.name}</span>
                <span className="price">{fmtPrice(s.last_price ?? s.close)}</span>
              </div>
              <div className="row2">
                <span className="muted">{s.sector33 ?? ""}</span>
                <span>RSI {fmtNum(s.rsi14)}</span>
                <span className="muted">代金 {fmtYen(s.avg_value20)}</span>
                <span className={`pct ${changeClass(s.change_pct)}`}>{fmtPct(s.change_pct)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {visible.length > shown && (
        <p className="center">
          <button onClick={() => setShown((n) => n + PAGE)}>さらに表示</button>
        </p>
      )}
    </section>
  );
}
