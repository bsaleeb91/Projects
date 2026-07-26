import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Server-only Supabase client using the service-role key. This file must never
 * be imported from a `'use client'` component — the service-role key bypasses
 * Row Level Security and the `runs` table has RLS enabled with zero policies,
 * so this is the only key that can write to it, and it must never reach the
 * browser bundle (no `NEXT_PUBLIC_` prefix on either env var).
 *
 * Lazily constructed: creating the client eagerly at module scope throws
 * immediately if the env vars aren't set, which breaks Next's build-time
 * route analysis in any environment without them configured (e.g. CI). It's
 * only ever actually called from the analytics write in a live request.
 */
let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(
      process.env.SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
      { auth: { persistSession: false } },
    );
  }
  return client;
}
