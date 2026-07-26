# Career Roadmap Tool ("Bishoy's Framework")

A validation MVP: upload a resume and three target job descriptions, answer five
questions, get back a written career roadmap. See the product spec in the repo
history for full method/tone/output requirements.

## Setup

```bash
npm install
cp .env.example .env.local   # fill in the values below
npm run dev
```

### Environment variables

| Variable | Where it's used | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | `app/api/generate-roadmap/route.ts` | Server-only |
| `SUPABASE_URL` | `lib/supabase.ts` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `lib/supabase.ts` | **Service role key**, not the anon key — required because the `runs` table has RLS enabled with zero policies (see `supabase/schema.sql`). Never expose this to the client; it's read only in server-side files. |

### Supabase setup

Create a Supabase project, then run `supabase/schema.sql` in the SQL Editor
to create the single `runs` analytics table. This app writes exactly three
things per completed run: normalized role categories (one per job
description), a short non-identifying summary of the roadmap's findings, and
the prompt version — never the raw resume, job description text, or the full
generated roadmap. See `lib/analytics.ts` for how that boundary is enforced.

## Prompt versioning

`lib/prompts/roadmap-system.ts` exports `PROMPT_VERSION`. Bump it on any
material change to the method, tone rules, or output structure — it's logged
with every analytics row, so a roadmap that comes out great or terrible can be
traced back to the exact prompt that produced it.

## Deploying to Vercel

1. **Enable Fluid Compute** on the Vercel project — Project Settings →
   Functions. This is a dashboard toggle, not something set in code or
   `vercel.json`. Without it, Hobby's default function duration is far below
   the 300 seconds `app/api/generate-roadmap/route.ts` needs, and long
   generations will be killed mid-stream.
2. Add the three environment variables above in the Vercel project settings.
3. Deploy. `export const maxDuration = 300` in the route handler is the
   correct Next.js mechanism and needs no additional Vercel config.

## What's deliberately not here

Per the product spec: no user accounts, no saved history, no return-visit
tracking, no payments, no notifications, no sharing/export beyond copy and
print. This is a one-sitting tool — refreshing mid-flow restarts at the
landing page, and that's fine.
