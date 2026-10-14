import type { NextConfig } from "next";

// 静的エクスポート：Vercel でも GitHub Pages でも配信でき、Capacitor でそのまま包める。
// データはブラウザから Supabase を直接読む（RLS で自分だけに制限）。
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
