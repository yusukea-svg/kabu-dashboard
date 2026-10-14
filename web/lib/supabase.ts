import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isConfigured = Boolean(url && key);

// anon / publishable キーはブラウザに出る前提の公開用キー。データは RLS で保護している。
export const supabase: SupabaseClient | null = isConfigured
  ? createClient(url!, key!, { auth: { persistSession: true, detectSessionInUrl: true } })
  : null;

/** PostgREST の1回あたりの上限（既定1000行）を超える件数をページングで取得する。 */
export async function fetchAll<T>(
  build: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
  pageSize = 1000,
): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; ; from += pageSize) {
    const { data, error } = await build(from, from + pageSize - 1);
    if (error) throw new Error(error.message);
    out.push(...(data ?? []));
    if (!data || data.length < pageSize) return out;
  }
}
