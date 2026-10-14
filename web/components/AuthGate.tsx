"use client";

import type { Session } from "@supabase/supabase-js";
import { type ReactNode, useEffect, useState } from "react";
import { isConfigured, supabase } from "@/lib/supabase";

/** ログインしていなければログイン画面を出す。データは RLS で守られているので、ここは表示の切り替えだけ。 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (!isConfigured) {
    return (
      <div className="panel">
        <h2>設定が必要です</h2>
        <p>
          <code>web/.env.local</code> に <code>NEXT_PUBLIC_SUPABASE_URL</code> と{" "}
          <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> を設定してください（docs/setup.md 参照）。
        </p>
      </div>
    );
  }
  if (session === undefined) return <p className="muted center">読み込み中…</p>;
  if (!session) return <Login />;
  return (
    <>
      {children}
      <p className="center">
        <button className="link" onClick={() => supabase!.auth.signOut()}>
          ログアウト（{session.user.email}）
        </button>
      </p>
    </>
  );
}

function Login() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    const { error } = await supabase!.auth.signInWithOtp({
      email,
      // 新規登録はさせない（Supabase で事前に作成したユーザーのみ）
      options: { shouldCreateUser: false, emailRedirectTo: window.location.origin + window.location.pathname },
    });
    if (error) {
      setError(error.message);
      setState("error");
    } else {
      setState("sent");
    }
  }

  return (
    <form className="panel login" onSubmit={submit}>
      <h2>ログイン</h2>
      <p className="muted">メールアドレスを入力すると、ログイン用のリンクがメールで届きます。</p>
      <input
        type="email"
        required
        autoComplete="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <button type="submit" disabled={state === "sending"}>
        {state === "sending" ? "送信中…" : "ログインリンクを送る"}
      </button>
      {state === "sent" && <p className="ok">メールを送りました。届いたリンクを開いてください。</p>}
      {state === "error" && <p className="error">送信できませんでした: {error}</p>}
    </form>
  );
}
