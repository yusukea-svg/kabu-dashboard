"use client";

import { useEffect, useState } from "react";
import { fmtDateTime } from "@/lib/format";
import { supabase } from "@/lib/supabase";
import type { JobRun } from "@/lib/types";

const STALE_HOURS = 30; // 日次更新がこれ以上古ければ警告（週明けは土日分を足す。祝日は考慮しない簡易版）

function latest(runs: JobRun[], job: string) {
  const mine = runs.filter((r) => r.job === job);
  return {
    last: mine[0] ?? null,
    lastOk: mine.find((r) => r.status === "ok" || r.status === "partial") ?? null,
  };
}

/** 最終更新時刻と、更新が止まっていないかの表示。 */
export default function LastUpdated() {
  const [runs, setRuns] = useState<JobRun[] | null>(null);

  useEffect(() => {
    supabase!
      .from("job_runs")
      .select("job,started_at,finished_at,status,ok_count,fail_count,message")
      .in("job", ["daily", "intraday"])
      .order("started_at", { ascending: false })
      .limit(30)
      .then(({ data }) => setRuns((data ?? []) as JobRun[]));
  }, []);

  if (!runs) return <div className="updated">&nbsp;</div>;
  const daily = latest(runs, "daily");
  const intraday = latest(runs, "intraday");

  const finished = daily.lastOk?.finished_at ?? null;
  const ageHours = finished ? (Date.now() - new Date(finished).getTime()) / 36e5 : Infinity;
  const day = new Date().toLocaleDateString("en-US", { timeZone: "Asia/Tokyo", weekday: "short" });
  const weekendGrace = day === "Sat" || day === "Sun" || day === "Mon" ? 72 : 0;
  const stale = ageHours > STALE_HOURS + weekendGrace;

  return (
    <div className={`updated ${stale ? "stale" : ""}`}>
      日次更新: {fmtDateTime(finished)}
      {intraday.lastOk && <> ／ 場中更新: {fmtDateTime(intraday.lastOk.finished_at)}</>}
      {stale && <strong> ⚠ 更新が止まっている可能性があります</strong>}
      {daily.last?.status === "failed" && <strong> ⚠ 直近の日次更新が失敗しました</strong>}
      {intraday.last?.status === "failed" && <strong> ⚠ 直近の場中更新が失敗しました</strong>}
    </div>
  );
}
