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

### app.py — Query Flow (rewritten 2026-08-24, extended 2026-09-03)
1. User types question + optionally selects a source filter and a search depth
2. **Single Claude call** (`generate_query_plan()`) returns both FTS search
   keywords **and** a depth classification. There is no longer a "Claude
   guesses relevant filenames" step — that used to guess from filenames alone
   before seeing any content, which both missed sources and silently dropped
   any source whose name Claude didn't reproduce character-for-character.
   Depth rides along on this existing call, so classification costs no extra
   request and no extra latency; an unparseable reply falls back to Standard
   rather than silently costing 4x.
3. **SQLite FTS5**, scoped to the `chunk_text` column only (an earlier bug let
   an unqualified `MATCH` also match the `source`/`filename` columns, so a
   keyword like "Chrysostom" pulled in that entire source by name rather than
   by content). One windowed query returns each source's top candidates using
   `rank MATCH 'bm25(0.0, 0.0, 1.0)'` (bm25 can't run inside a window function
   directly, so the weights are set this way instead).
4. **Gate + guaranteed passage + merit fill** in Python (`select_passages()`).
   Any source clearing the relevance gate is guaranteed one *anchor* chunk
   expanded by `PASSAGE_RADIUS` neighbours into a contiguous passage — the unit
   of the floor is a passage, not a lone excerpt, because a chunk is roughly
   one page here and usually cuts mid-argument. Expansion is clipped to the
   anchor's own `(source, filename)`: chunks are inserted in document order, so
   consecutive ids are consecutive text of the same PDF (verified — ids
   5000-5008 are pages 234-242 of one volume), but `filename` alone is not
   unique across sources. The rest is filled by merit, with no source allowed
   more than `MAX_SOURCE_SHARE` of the budget. Exact-duplicate chunk text
   (front-matter/boilerplate) is deduped and backfilled.
5. `format_context()` merges contiguous chunks into one passage block and
   strips the words that overlap between them. The overlap is **measured, not
   assumed**: `build_index.py` chunks each page separately, so consecutive ids
   overlap only within a page and share nothing across a page boundary —
   stripping a fixed 50 words would eat real text at every page break.
6. Claude Sonnet 5 streams the answer with citations, instructed to quote the
   fathers directly and to name them where an excerpt identifies one. At Deep
   it is additionally told to answer in proportion to the material rather than
   summarising it — without that it applies one-verse-lookup compression to a
   150-excerpt thematic question.
7. **Sources used expander** shows every excerpt, grouped by source, so the
   user can verify what the model had to work with.

### Search depth (added 2026-09-03)

Cost is close to linear in excerpts sent, and most questions are single-verse
lookups that don't need the full budget.

| Depth | Excerpts | `gate_ratio` | Input tokens | ~Input cost |
|-------|----------|--------------|--------------|-------------|
| Standard | 40 | 0.45 | ~21K | ~$0.042 |
| Deep | 150 | 0.35 | ~75K | ~$0.150 |

Sidebar offers `Auto` (default), `Standard`, `Deep`. Auto sends single-verse
lookups to Standard and thematic/doctrinal/comparative questions to Deep.

`gate_ratio` is the fraction of the corpus-best score a source must reach to
earn a guaranteed passage — **higher = stricter = fewer sources**. Measured on
"John 3:16": 0.30 → 16 sources qualify, 0.35 → 13, 0.40 → 11, 0.50 → 5,
0.60 → 3, 0.70 → 1. Standard gates harder on purpose: at a 40-chunk budget it
is better to quote 7-8 fathers coherently than to scatter 40 orphan fragments
across 18 of them.

Measured live 2026-09-03: "give me the commentary for John 3:16" → 40 excerpts
from **13 sources** (Standard); "Does God love me more than I love myself?" →
150 excerpts from **17 sources** (Deep).

**Why this changed**: the flat "top 20 by rank" approach let whichever source
happened to be most verse-indexed take 15–20 of 20 slots on a typical question,
leaving 30+ of the 37 sources completely unrepresented even when they had
directly relevant commentary. See the retrieval-overhaul plan for the measured
before/after on "What does John 3:16 mean?".

### Source Filters
Sidebar multiselect over all 37 sources. Leave blank to search the whole
corpus (gate/passage/merit selection decides what's relevant). Select one or
more to restrict retrieval to exactly those sources. Select 2+ and toggle
**Compare** to get a structured side-by-side instead of a blended answer.

Note that a "source" is a top-level folder, which mixes individual authors
(`John Chrysostom`, `Cyril of Alexandria`) with whole collections (`Nicene and
Post-Nicene Fathers` = 58,955 chunks across 39 volumes, each volume a different
father). Selecting NPNF therefore selects dozens of fathers at once, and a
citation naming it does not say who is speaking. See ROADMAP.md P1.

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
| `get_sources()` (`SELECT DISTINCT source FROM chunks`) took 37s on the 751MB DB — full table scan, no index on `source` — blocking the whole UI behind a spinner on every cold start | Added `CREATE INDEX idx_chunks_source ON chunks(source)` to `build_index.py`'s schema so future rebuilds get it. **Unconfirmed on the live Render DB** — a 2026-09-03 cold start still sat on `Running get_sources(...)` for ~30-40s, so the index may never have been applied there. `build_index.py` only affects future builds, not the file already on the persistent disk. Verify and apply directly if missing |
| **The whole 2026-08-24 retrieval overhaul was never deployed.** It sat uncommitted in the working tree until 2026-09-03, while `main` — and therefore Render — stayed on `99b7b79`. Production ran the flat `ORDER BY rank LIMIT 20` retrieval, the unscoped `MATCH` bug, and the filename-guessing pre-filter the entire time | Committed and pushed 2026-09-03 (`dc86807`). Any judgement about retrieval quality formed before that date was formed against the *old* code |
| Every question asked without a source filter returned "No matching content found" despite retrieval succeeding — the default branch assigned `all_rows` but never built `context` from it, unlike the compare and selected-source branches, so `context` stayed `""` and the answer step was skipped | Fixed 2026-09-03 (`dab4e86`). Caught by a live test: John 3:16 selected 150 excerpts across 18 sources and discarded all of them |
| One commentary took 65% of the budget at Standard depth. `dominance_cap` was `(cap // n_qualified) * 2` — derived from how many sources cleared the gate, so a *stricter* gate left fewer qualifiers and made the per-source allowance *larger*. On "John 3:16" a 0.60 gate admitted 3 sources, setting the allowance to 26 of 40 slots | Replaced with `MAX_SOURCE_SHARE` (0.25), a fixed fraction of the budget independent of the gate (2026-09-03, `8052338`). Same query then returned 11 sources with a 27% maximum |
| Deep retrieved ~4x the excerpts but the answer stayed the same length — the system prompt was identical at both depths and told the model to "prefer breadth over repeating one source at length", so it surveyed 17 sources in two paragraphs | Deep now asks for a treatment proportional to the material; the base prompt also asks for direct quotation and for naming the father (2026-09-03, `988a4a5`) |

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

## Cost

Roughly linear in excerpts sent. Sonnet 5 is $2/MTok input, $10/MTok output.

| | Input | Output | Total |
|---|---|---|---|
| Standard (40 excerpts) | ~$0.042 | ~$0.01-0.02 | **~$0.05** |
| Deep (150 excerpts) | ~$0.150 | ~$0.03-0.05 | **~$0.20** |

Auto depth keeps routine lookups at the Standard price and spends the larger
budget only on thematic questions. Prompt caching does **not** help here — the
excerpts are unique per question, so there is no reusable prefix.

## What's next

Planning has moved to **`ROADMAP.md`**, which is prioritized and carries the
measured evidence behind each item. Summary of where things stand:

- **Done since this doc was written**: depth presets + auto-selection,
  passage-based retrieval floor, the dominance-cap fix, answer depth matched to
  retrieval depth, direct quotation of the fathers.
- **The two structural problems** (ROADMAP P1, P2): "source" is a folder, not a
  father, so ~46% of the corpus carries no author attribution and no father gets
  a retrieval floor of his own; and 80%+ of NPNF chunks contain no verse
  reference of any form, making them unreachable by reference keywords. Both
  need an indexing pass to fix.
- **Still purely lexical** (ROADMAP P3): FTS5 can't serve thematic questions
  well — "theosis" misses commentary that only says "deification". Semantic
  retrieval is the remaining quality ceiling and requires re-embedding all
  196,608 chunks.
- Also open: OCR for image-only PDFs, an eval set, query logging, a shared
  password, and the Render tier. See ROADMAP.md.
