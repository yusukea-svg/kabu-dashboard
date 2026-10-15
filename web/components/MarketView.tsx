"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { changeClass, fmtDateTime, fmtPct } from "@/lib/format";
import { fetchAll, supabase } from "@/lib/supabase";
import type { Disclosure, JobRun, MacroMeta, MacroPoint, NewsItem } from "@/lib/types";
import Sparkline from "./Sparkline";

const SPARK_DAYS = 90;
const CATEGORY_ORDER = ["株価指数", "為替", "金利", "変動率", "商品"];

function fmtValue(v: number, unit: string | null) {
  const digits = unit === "%" ? 2 : Math.abs(v) >= 1000 ? 0 : 2;
  return v.toLocaleString("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export default function MarketView() {
  const [meta, setMeta] = useState<MacroMeta[] | null>(null);
  const [points, setPoints] = useState<MacroPoint[]>([]);
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [docs, setDocs] = useState<Disclosure[] | null>(null);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [newsSource, setNewsSource] = useState<string>("すべて");
  const [error, setError] = useState("");

  useEffect(() => {
    const sb = supabase!;
    const since = new Date(Date.now() - SPARK_DAYS * 1.5 * 864e5).toISOString().slice(0, 10);
    sb.from("macro_meta").select("*").order("sort_order").then(({ data, error }) =>
      error ? setError(error.message) : setMeta((data ?? []) as MacroMeta[]),
    );
    fetchAll<MacroPoint>((from, to) =>
      sb.from("macro_series").select("series_id,date,value").gte("date", since).order("date").range(from, to) as never,
    ).then(setPoints, (e: Error) => setError(e.message));
    sb.from("news").select("*").order("published_at", { ascending: false, nullsFirst: false }).limit(150)
      .then(({ data }) => setNews((data ?? []) as NewsItem[]));
    const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString();
    sb.from("v_disclosures").select("*").gte("submitted_at", weekAgo).order("submitted_at", { ascending: false }).limit(300)
      .then(({ data }) => setDocs((data ?? []) as Disclosure[]));
    sb.from("job_runs").select("job,started_at,finished_at,status,ok_count,fail_count,message")
      .in("job", ["macro", "news", "edinet"]).in("status", ["ok", "partial"])
      .order("started_at", { ascending: false }).limit(20)
      .then(({ data }) => setRuns((data ?? []) as JobRun[]));
  }, []);

  const bySeries = useMemo(() => {
    const m = new Map<string, MacroPoint[]>();
    for (const p of points) m.set(p.series_id, [...(m.get(p.series_id) ?? []), p]);
    return m;
  }, [points]);

  const updated = (job: string) => fmtDateTime(runs.find((r) => r.job === job)?.finished_at);
  const sources = ["すべて", ...new Set((news ?? []).map((n) => n.source))];
  const shownNews = (news ?? []).filter((n) => newsSource === "すべて" || n.source === newsSource).slice(0, 40);

  const categories = CATEGORY_ORDER.filter((c) => meta?.some((m) => m.category === c));

  return (
    <section>
      {error && <p className="error">読み込みに失敗しました: {error}</p>}

      <h2 className="section-title">マーケット</h2>
      <p className="muted small">更新: {updated("macro")}（日次の終値ベース・遅延あり）</p>
      {!meta && <p className="muted center">読み込み中…</p>}
      {meta && meta.length === 0 && <p className="muted">まだデータがありません（情報取得バッチが未実行）。</p>}
      {categories.map((cat) => (
        <div key={cat}>
          <h3 className="cat">{cat}</h3>
          <div className="cards">
            {meta!.filter((m) => m.category === cat).map((m) => {
              const pts = bySeries.get(m.series_id) ?? [];
              const last = pts[pts.length - 1];
              const prev = pts[pts.length - 2];
              const diff = last && prev ? last.value - prev.value : null;
              const pct = diff != null && prev.value !== 0 ? (diff / prev.value) * 100 : null;
              return (
                <div className="card" key={m.series_id}>
                  <div className="card-label">{m.label}</div>
                  <div className="card-value">
                    {last ? fmtValue(last.value, m.unit) : "—"}
                    <span className="unit">{m.unit === "%" ? "%" : ""}</span>
                  </div>
                  <div className={`small ${changeClass(diff)}`}>
                    {m.unit === "%" && diff != null
                      ? `${diff > 0 ? "+" : ""}${diff.toFixed(2)}pt`
                      : fmtPct(pct)}
                  </div>
                  <Sparkline values={pts.slice(-SPARK_DAYS).map((p) => p.value)} />
                  <div className="muted tiny">{last?.date ?? ""}・{m.source}</div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <h2 className="section-title">ニュース</h2>
      <p className="muted small">更新: {updated("news")}（見出しのみ。記事は各サイトで）</p>
      <div className="chips">
        {sources.map((s) => (
          <button key={s} className={`chip ${newsSource === s ? "on" : ""}`} onClick={() => setNewsSource(s)}>
            {s}
          </button>
        ))}
      </div>
      <ul className="news">
        {shownNews.map((n) => (
          <li key={n.id}>
            <a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a>
            <span className="muted tiny">
              {n.source}・{fmtDateTime(n.published_at ?? n.fetched_at)}
            </span>
          </li>
        ))}
        {news && shownNews.length === 0 && <li className="muted">ニュースはまだありません。</li>}
      </ul>

      <h2 className="section-title">開示（EDINET・直近7日）</h2>
      <p className="muted small">更新: {updated("edinet")}</p>
      <ul className="news">
        {(docs ?? []).map((d) => (
          <li key={d.id}>
            <span>
              <Link href={`/stock/?code=${encodeURIComponent(d.code)}`} className="code-link">
                {d.code} {d.name}
              </Link>{" "}
              <a href={d.url} target="_blank" rel="noopener noreferrer">{d.title}</a>
            </span>
            <span className="muted tiny">{d.doc_type}・{fmtDateTime(d.submitted_at)}</span>
          </li>
        ))}
        {docs && docs.length === 0 && <li className="muted">直近7日の開示はありません（またはEDINET未設定）。</li>}
      </ul>
    </section>
  );
}
