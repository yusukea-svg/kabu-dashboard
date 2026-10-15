import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import AuthGate from "@/components/AuthGate";
import "./globals.css";

export const metadata: Metadata = {
  title: "株ダッシュボード",
  description: "個人用の日本株情報ダッシュボード",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#111418" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <header className="top">
          <Link href="/" className="brand">
            株ダッシュボード
          </Link>
          <nav className="nav">
            <Link href="/">銘柄</Link>
            <Link href="/market/">マーケット</Link>
          </nav>
        </header>
        <main>
          <AuthGate>{children}</AuthGate>
        </main>
        <footer className="disclaimer">
          本サイトは個人の情報整理用であり、投資助言ではありません。表示内容の正確性は保証されません。
          株価は遅延・欠落することがあります。投資判断はご自身の責任で行ってください。
        </footer>
      </body>
    </html>
  );
}
