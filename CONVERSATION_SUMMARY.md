# Bible Commentary App — Conversation Summary

## What We Built

A Streamlit web app that answers Bible questions **exclusively** from a library of
PDF commentaries you own. Ask "What does John 3:16 mean?" and it searches your PDFs
using Claude-generated keywords + SQLite FTS5, then streams an answer with citations.

Live URL: **https://bible-commentary-w76w.onrender.com/**

---

## Architecture

### Model
All API calls use **Claude Sonnet 5** (`claude-sonnet-5`).

### Files
| File | Purpose |
|------|---------|
| `commentary_agent.py` | Original CLI tool (sync, ask, list, remove) |
| `build_index.py` | One-time indexer: downloads Drive PDFs → SQLite FTS5 |
| `app.py` | Streamlit web app |
| `cleanup_db.py` | One-time script: removes non-commentary files from DB |
| `debug_ephesians.py` | Diagnostic script (can be deleted) |
| `debug_drive.py` | Drive folder inspector |
| `get_drive_token.py` | One-time Google OAuth token generator |
| `commentary_index.json` | Maps Anthropic file IDs → Drive file IDs (used by CLI) |
| `commentary.db` | SQLite FTS5 database (~751MB as of 2026-08, not in git — see Deployment) |
| `requirements.txt` | Python dependencies for Render |

### File Locations on Windows
```
C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents\
```

### GitHub
- **Repo**: `bsaleeb91/projects` — branch `main`
- **`commentary.db`** is gitignored — it lives on a **Render persistent disk**, not in the
  repo and not in Git LFS (an earlier LFS setup was retired; see `DB_PATH` below)

---

## How It Works

### build_index.py (run once, or when PDFs change)
1. Connects to Google Drive using OAuth credentials
2. Recursively scans folder `1JGYkkGV62vuUOVWBo-MxW0b24ysLshC8`
3. Skips blacklisted non-commentary files (see below)
4. Downloads each PDF into memory
5. Extracts text page-by-page using **pymupdf** (`fitz`)
6. Splits into ~500-word chunks with 50-word overlap
7. Stores in SQLite FTS5 (`commentary.db`) with source, filename, page number

### app.py — Query Flow (rewritten 2026-08-24)
1. User types question + optionally selects a source filter
2. **Single Claude call** generates FTS search keywords only — there is no
   longer a "Claude guesses relevant filenames" step. That step used to guess
   from filenames alone before seeing any content, which both missed sources
   and silently dropped any source whose name Claude didn't reproduce
   character-for-character.
3. **SQLite FTS5**, scoped to the `chunk_text` column only (an earlier bug let
   an unqualified `MATCH` also match the `source`/`filename` columns, so a
   keyword like "Chrysostom" pulled in that entire source by name rather than
   by content). One windowed query returns each source's top candidates using
   `rank MATCH 'bm25(0.0, 0.0, 1.0)'` (bm25 can't run inside a window function
   directly, so the weights are set this way instead).
4. **Gate + guaranteed floor + merit fill** in Python (`select_diverse()`)
   picks up to 150 chunks total: any source that clears a relevance gate gets
   a guaranteed floor of a few excerpts, the rest is filled by merit with a
   per-source cap so no single source can dominate. Exact-duplicate chunk text
   (front-matter/boilerplate pages) is deduped and backfilled.
5. Claude Sonnet 5 streams the answer with citations, instructed to synthesize
   across sources thematically rather than walk through excerpts in order.
6. **Sources used expander** shows every excerpt, grouped by source, so the
   user can verify what the model had to work with.

**Why this changed**: the flat "top 20 by rank" approach let whichever source
happened to be most verse-indexed take 15–20 of 20 slots on a typical question,
leaving 30+ of the 37 sources completely unrepresented even when they had
directly relevant commentary. See the retrieval-overhaul plan for the measured
before/after on "What does John 3:16 mean?".

### Source Filters
Sidebar multiselect over all 37 sources. Leave blank to search the whole
corpus (gate/floor/merit selection decides what's relevant). Select one or
more to restrict retrieval to exactly those sources. Select 2+ and toggle
**Compare** to get a structured side-by-side instead of a blended answer.

### Conversation Memory
Last 10 turns kept in Claude's context. Older messages dropped to control costs.

---

## PDF Sources (Google Drive)

37 top-level source folders (Nicene and Post-Nicene Fathers, Fr. Tadros Malaty
Bible Commentary, Ancient Christian Commentary, John Chrysostom, and many more
patristic and commentary collections), **551 PDFs indexed** as of 2026-08-24,
producing 196,608 FTS5 chunks. Sizes vary enormously by source — from Nicene
and Post-Nicene Fathers (58,955 chunks) down to Severus of Antioch (8 chunks)
— which is exactly why retrieval needs the gate/floor/merit logic above rather
than a flat top-N.

---

## Deployment (Render)

- **Service**: Web Service (persistent disk plan — required for `commentary.db`
  to survive redeploys; free tier has no persistent disk)
- **Branch**: `main`
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `streamlit run app.py --server.port $PORT --server.headless true`
- **Environment variables**: `ANTHROPIC_API_KEY`, `DB_PATH` (points at the
  persistent disk mount, e.g. `/var/data/commentary.db`; falls back to the
  local repo path if unset)

---

## Blacklisted Files

These files are in the Drive folder but are NOT commentary — excluded from indexing:

```python
BLACKLIST = {
    "ACCS INTRODUCTION AND BIBLIOGRAPHIC INFORMATION.pdf",
    "MELTHO... Syriac OpenType Fonts for Windows XP.pdf",
    "The Apocrypha ... King James Version.pdf",
    "1470-G.pdf",
    "1470-I.pdf",
    "000 Map_of_the_Old_Testament.pdf",
    "000 Search_Scriptures.pdf",
}
```

---

## Known Issues / Gotchas

| Issue | Resolution |
|-------|-----------|
| `pypdf` returned 0 chunks for Ephesians; crashed on Proverbs/Ecclesiastes/Song of Solomon | Switched to `pymupdf` (`fitz`) — far more robust |
| `049 Ephesians.pdf` (Fr. Tadros) returns 0 chunks even with pymupdf | Image-only PDF, no text layer — would need OCR. ACC volume covers Ephesians |
| Non-commentary files (intro, font, KJV) polluted FTS results | Added `BLACKLIST` in `build_index.py`; run `cleanup_db.py` to clean existing DB |
| Claude hallucinated quotes and page numbers | Strengthened system prompt; added Sources expander |
| `.gitignore` had `*.txt` which blocked `requirements.txt` | Fixed to explicitly list secret files instead |
| *(retired)* `commentary.db` exceeded GitHub's 100MB limit | Originally handled via Git LFS; superseded — the DB now lives entirely on a Render persistent disk (`DB_PATH`) and is gitignored, not committed at all |
| Flat `ORDER BY rank LIMIT 20` let one verse-indexed source take 15-20 of 20 slots, leaving 30+ of 37 sources unrepresented | Rewrote retrieval (2026-08-24): FTS scoped to `chunk_text` only (was also matching `source`/`filename` columns), plus gate/floor/merit selection across 150 chunks — see Query Flow above |
| `get_sources()` (`SELECT DISTINCT source FROM chunks`) took 37s on the 751MB DB — full table scan, no index on `source` — blocking the whole UI behind a spinner on every cold start | Added `CREATE INDEX idx_chunks_source ON chunks(source)` (2026-08-24, both to the live DB and to `build_index.py`'s schema so future rebuilds get it too). Query now takes ~0.03s |

---

## Commands

### Windows — initial setup / after pulling fresh
```powershell
cd "C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents"
pip install anthropic google-api-python-client google-auth-oauthlib pymupdf streamlit
```

### Build the index (1–2 hrs, run when PDFs change)
```powershell
python build_index.py
```
`commentary.db` is gitignored — it is never committed. Upload the rebuilt file
directly to the Render persistent disk (e.g. via Render's shell/SFTP) instead
of pushing it through git.

### Clean non-commentary files from existing DB (one-time)
```powershell
python cleanup_db.py
```

### Run locally
```powershell
streamlit run app.py
```

---

## Adding New PDFs

1. Drop the PDF into the correct Google Drive folder
2. Run `python build_index.py` on Windows (skips already-indexed files, only processes new ones)
3. Upload the updated `commentary.db` to the Render persistent disk — it is not
   committed to git, so there is nothing to push for this step

---

## Dependencies

```
anthropic
google-api-python-client
google-auth-oauthlib
pymupdf
streamlit
```

---

## V2 Considerations

- **Hallucination**: Can't be fully prevented with prompting. The Sources expander lets users verify. Better retrieval = less hallucination. Consider Files API for small PDFs.
- **OCR for image-only PDFs**: `049 Ephesians.pdf` has no text layer. Adobe Acrobat can OCR it; replace the Drive file and re-run `build_index.py`.
- **Password protection**: The app URL is public. Add Streamlit's built-in auth if you want to restrict access.
- **Cost controls**: retrieval now sends ~150 chunks (~65K tokens) per question instead of 20
  (~8.6K), roughly a 5-7x cost increase per question (~$0.20/question vs. ~$0.03-0.05 before,
  on Sonnet). Watch actual usage after this change; a sidebar depth selector (Standard/Deep/
  Exhaustive mapping to fewer/more chunks) is the mitigation if cost becomes a concern.
- **Upgrade Render**: Move to Starter ($7/mo) to eliminate cold start for regular users, if not
  already on it (a persistent disk plan is required for `commentary.db` regardless).
- **Semantic search (not yet built)**: FTS5 is purely lexical — a question about "theosis" misses
  commentary that only says "deification". Adding an embedding-based vector index (fused with
  BM25 via reciprocal rank fusion) is the next quality ceiling to address, but it requires
  re-indexing all 196,608 chunks and a plan for getting the larger DB onto the Render persistent
  disk — bigger scope than the 2026-08-24 retrieval rewrite, deliberately deferred.
