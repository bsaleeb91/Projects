-- Analytics table for the Career Roadmap Tool. Run once against your
-- Supabase project (SQL Editor). Deliberately the only table this app has —
-- it never stores raw resumes, job descriptions, or generated roadmaps.

create table public.runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  email text,
  role_categories text[] not null,
  summary_findings jsonb not null,
  prompt_version text not null
);

-- RLS enabled with zero policies: even a leaked anon key can't read or write
-- this table. All access is server-side only, via the service role key.
alter table public.runs enable row level security;
