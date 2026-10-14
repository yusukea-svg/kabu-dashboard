const jst = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export const fmtDateTime = (iso: string | null | undefined) => (iso ? jst.format(new Date(iso)) : "—");

export function fmtPrice(v: number | null | undefined) {
  if (v == null) return "—";
  return v.toLocaleString("ja-JP", { maximumFractionDigits: v < 1000 ? 1 : 0 });
}

export function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 1) {
  return v == null ? "—" : v.toFixed(digits);
}

/** 円を「億」「万」で短く表示 */
export function fmtYen(v: number | null | undefined) {
  if (v == null) return "—";
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}億`;
  if (v >= 1e4) return `${Math.round(v / 1e4).toLocaleString("ja-JP")}万`;
  return Math.round(v).toLocaleString("ja-JP");
}

export function fmtShares(v: number | null | undefined) {
  if (v == null) return "—";
  if (v >= 1e4) return `${Math.round(v / 1e4).toLocaleString("ja-JP")}万株`;
  return `${Math.round(v).toLocaleString("ja-JP")}株`;
}

export const changeClass = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
