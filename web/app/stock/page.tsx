import { Suspense } from "react";
import StockDetail from "@/components/StockDetail";

// 静的エクスポートのため、銘柄は /stock/?code=7203 のようにクエリで渡す
export default function StockPage() {
  return (
    <Suspense fallback={<p className="muted center">読み込み中…</p>}>
      <StockDetail />
    </Suspense>
  );
}
