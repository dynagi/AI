import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

export const supabaseConfigured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);

// Only the public anon key is used in the browser. It can do nothing on its own: Row Level Security limits it
// to reading the signed-in user's own rows, and all writes go through the FastAPI backend.
export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321",
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "missing-anon-key",
      { auth: { persistSession: true, autoRefreshToken: true } },
    );
  }
  return client;
}
