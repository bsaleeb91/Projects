# Bible Commentary App — Conversation Summary

## What We Built

A Streamlit web app that answers Bible questions **exclusively** from a library of
PDF commentaries you own. Ask "What does John 3:16 mean?" and it searches your PDFs
using hybrid Claude + FTS5 search, then streams an answer with citations.

Live URL: **https://bible-commentary-w76w.onrender.com/**

---

## Architecture

### Model
All API calls use **Claude Sonnet 4.6** (`claude-sonnet-4-6`).

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
| `commentary.db` | SQLite FTS5 database (142MB, stored in Git LFS) |
| `requirements.txt` | Python dependencies for Render |
| `.gitattributes` | Tracks `*.db` files via Git LFS |

### File Locations on Windows
```
C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents\
```

### GitHub
- **Repo**: `bsaleeb91/Projects` — branch `main`
- **`commentary.db`** is stored via Git LFS (142MB, exceeds GitHub's 100MB limit)

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

### app.py — Query Flow
1. User types question + selects source filter
2. **Single Claude call**: picks relevant filenames AND generates search keywords
   (verse refs + synonyms, e.g. "John 3:16, 3:16, eternal life, believe, faith")
3. **SQLite FTS5** returns top 20 matching chunks from only those files (milliseconds)
4. Claude Sonnet 4.6 streams the answer with citations
5. **Sources expander** shows the exact excerpts Claude used — user can verify

### Source Filters
- **All** — searches both sources
- **Fr. Tadros Malaty** — Tadros only
- **Ancient Christian Commentary** — ACC only
- **Compare Both** — searches each source separately, asks Claude to compare explicitly

### Conversation Memory
Last 10 turns kept in Claude's context. Older messages dropped to control costs.

---

## PDF Sources (Google Drive)

| Source | Drive Folder |
|--------|-------------|
| Fr. Tadros Malaty | `Fr. Tadros Malaty Bible Commentary` |
| Ancient Christian Commentary | `Ancient Christian Commentary` |

**Total: 110 PDFs** (109 indexed — `049 Ephesians.pdf` is image-only, no text layer)

---

## Deployment (Render)

- **Service**: Web Service, Free tier
- **Branch**: `main`
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `streamlit run app.py --server.port $PORT --server.headless true`
- **Environment variable**: `ANTHROPIC_API_KEY`

### Free Tier Notes
- App sleeps after 15 min inactivity — ~30 sec cold start on first visit
- Upgrade to Starter ($7/mo) for always-on if cold starts become annoying

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
| Claude hallucinated quotes and page numbers | Strengthened system prompt; added file selection before FTS; added Sources expander |
| `commentary.db` is 142MB — exceeds GitHub's 100MB limit | Set up Git LFS: `git lfs track "*.db"` |
| `git lfs migrate import` needed to rewrite history after committing DB before LFS was set up | Run `git lfs migrate import --include="commentary.db"` then force push |
| `.gitignore` had `*.txt` which blocked `requirements.txt` | Fixed to explicitly list secret files instead |

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
git add commentary.db
git commit -m "update commentary index"
git push origin main
```

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
3. Commit and push the updated `commentary.db`
4. Render auto-redeploys

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
- **Cost controls**: ~$1–3/month for personal use with Sonnet. If usage grows, add rate limiting.
- **Upgrade Render**: Move to Starter ($7/mo) to eliminate cold start for regular users.
