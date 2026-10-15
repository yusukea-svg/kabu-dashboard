"use client";

import { useEffect, useState } from "react";
import { fmtDateTime } from "@/lib/format";
import { supabase } from "@/lib/supabase";
import type { Disclosure } from "@/lib/types";

/** 銘柄ごとの開示（EDINET）と、適時開示（TDnet）を見るための外部リンク。 */
export default function DisclosureList({ code }: { code: string }) {
  const [docs, setDocs] = useState<Disclosure[] | null>(null);

  useEffect(() => {
    supabase!
      .from("disclosures")
      .select("*")
      .eq("code", code)
      .order("submitted_at", { ascending: false })
      .limit(30)
      .then(({ data }) => setDocs((data ?? []) as Disclosure[]));
  }, [code]);

  const c = encodeURIComponent(code);
  return (
    <section className="signals">
      <h3>開示</h3>
      <ul className="news">
        {(docs ?? []).map((d) => (
          <li key={d.id}>
            <a href={d.url} target="_blank" rel="noopener noreferrer">{d.title}</a>
            <span className="muted tiny">{d.doc_type}・{fmtDateTime(d.submitted_at)}・EDINET</span>
          </li>
        ))}
        {docs && docs.length === 0 && <li className="muted small">EDINETの書類はまだありません。</li>}
      </ul>
      {/* TDnet（決算短信など）は無料APIがなく取得しないので、外部サイトへのリンクだけ置く */}
      <p className="small">
        適時開示（決算短信など）：
        <a href={`https://finance.yahoo.co.jp/quote/${c}.T/disclosure`} target="_blank" rel="noopener noreferrer">
          Yahoo!ファイナンス
        </a>
        {" ／ "}
        <a href={`https://kabutan.jp/disclosures/?code=${c}`} target="_blank" rel="noopener noreferrer">
          株探
        </a>
      </p>
    </section>
  );
}
