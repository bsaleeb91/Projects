# PDF Commentary Agent — Conversation Summary

## What We Built

A Bible commentary agent that answers questions **exclusively** from a library of
PDF commentaries you own. You ask "What does John 3:16 mean?" and it searches
your PDFs and answers using only what your commentaries say — with citations back
to the source document and page number.

---

## Architecture (Current State)

### Files
| File | Location | Purpose |
|------|----------|---------|
| `commentary_agent.py` | Windows + GitHub | Main agent script |
| `get_drive_token.py` | Windows | One-time Google Drive OAuth token generator |
| `debug_drive.py` | Windows | Diagnostic tool for Drive folder inspection |
| `commentary_index.json` | Windows + GitHub (`master`) | Maps Anthropic file IDs to Drive file IDs |
| `.env` | Windows only | Stores `ANTHROPIC_API_KEY` (never committed) |
| `credentials.json` | Windows only | Google OAuth client credentials (never committed) |
| `drive_token.json` | Windows only | Google Drive OAuth token (never committed) |

### File Locations on Windows
All files live in:
```
C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents\
```

### GitHub Repos
- **Agent code**: `bsaleeb91/Projects` — branch `claude/pdf-commentary-agent-55FAO`
- **Index + credentials config**: `bsaleeb91/Projects` — branch `master`

---

## How It Works

### Indexing (sync)
1. Connects to Google Drive using OAuth credentials
2. Recursively scans folder `1JGYkkGV62vuUOVWBo-MxW0b24ysLshC8` and all subfolders
3. Downloads each new PDF into memory
4. Uploads it to Anthropic's Files API (stores file ID in `commentary_index.json`)
5. Removes deleted files from the index automatically

### Answering (ask)
1. Reads `commentary_index.json` to get list of all 110 PDFs
2. Asks Claude which PDFs are relevant to the question (by filename)
3. Extracts search keywords from the question (e.g. "John 3:16", "3:16", "John 3")
4. Downloads each relevant PDF from Google Drive
5. Scans every page for keyword matches using `pypdf`
6. Sends only the matching pages as text to Claude Opus 4.6
7. Streams the answer back with citations (commentary name + page number)

### Why This Approach
- Anthropic's Files API has a **600-page limit** and **1M token limit** per request
- 110 large PDFs (100–300 pages each) far exceed these limits
- Solution: download PDFs on demand, extract only relevant pages, send as text

---

## PDF Sources (Google Drive)

Two top-level folders, each with multiple subfolders and PDFs:

| Source | Drive Folder Name |
|--------|------------------|
| Fr. Tadros Malaty | `Fr. Tadros Malaty Bible Commentary` |
| Ancient Christian Commentary | `Ancient Christian Commentary` |

**Total: 110 PDFs**

---

## Commands (Current CLI)

Run all commands from:
```
C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents\
```

| Command | What it does |
|---------|-------------|
| `python commentary_agent.py sync` | Sync Google Drive folder → upload new PDFs, remove deleted ones |
| `python commentary_agent.py ask "question"` | Ask a question, get answer from your PDFs |
| `python commentary_agent.py list` | List all indexed PDFs |
| `python commentary_agent.py remove <id>` | Remove a specific PDF from the index |
| `python commentary_agent.py debug` | Inspect top-level Drive folder contents |

### Updating the Script
GitHub's raw URL caches the old version. Use this to force a fresh download:
```powershell
$content = Invoke-RestMethod -Uri "https://api.github.com/repos/bsaleeb91/Projects/contents/commentary_agent.py?ref=claude/pdf-commentary-agent-55FAO" -Headers @{Accept="application/vnd.github.v3.raw"}
[System.IO.File]::WriteAllText("C:\Users\17165\OneDrive\Documents\Claude\Personal\Agents\commentary_agent.py", $content)
```

---

## Automated Weekly Sync (GitHub Actions)

A workflow at `.github/workflows/sync_commentaries.yml` runs every Monday at 6am UTC.

### What it does
1. Downloads all PDFs from Google Drive
2. Uploads any new ones to Anthropic Files API
3. Refreshes the Google OAuth token automatically
4. Commits the updated `commentary_index.json` back to the repo

### Required GitHub Secrets
Go to `github.com/bsaleeb91/Projects → Settings → Secrets → Actions`:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | From your `.env` file |
| `GOOGLE_CREDENTIALS_JSON` | Full contents of `credentials.json` |
| `GOOGLE_TOKEN_JSON` | Full contents of `drive_token.json` |

> **Status**: Workflow is created and pushed. Secrets still need to be added.

---

## File Expiry

Anthropic's Files API expires files after **30 days of no use**. The weekly GitHub
Actions sync re-uploads any expired files automatically — you don't need to think
about it.

---

## What's Next — Streamlit Web App

### The Problem with the Current CLI
- You have to be at your Windows laptop to run commands
- You want to ask questions from your **phone**, anywhere

### The Plan

#### Phase 1: Pre-process PDFs into SQLite
Run `build_index.py` once (estimated 1–2 hours for 110 PDFs):
1. Download every PDF from Google Drive
2. Extract all text page by page using `pypdf`
3. Split into ~500-word chunks
4. Store in a SQLite database with full-text search (FTS5)

**Database structure:**
```
chunks table
  - id
  - source        ("Fr. Tadros Malaty" or "Ancient Christian Commentary")
  - filename
  - page_number
  - chunk_text    (FTS5 indexed)
```

#### Phase 2: Streamlit Web App
`app.py` provides a chat interface:

```
┌─────────────────────────────────────────┐
│  Source:  [All] [Fr. Tadros] [ACC]      │
│           [Compare Both]                │
│                                         │
│  Ask a question...                      │
│  ┌───────────────────────────────────┐  │
│  │ What does John 3:16 mean?         │  │
│  └───────────────────────────────────┘  │
│                    [Ask]                │
└─────────────────────────────────────────┘
```

**Query flow:**
1. User types question + selects source filter
2. App extracts keywords ("John 3:16", "3:16", "John 3")
3. SQLite FTS search returns top ~20 matching chunks (milliseconds)
4. Chunks sent to Claude Opus 4.6 with system prompt
5. Answer streams back with citations

**Conversation memory:** Claude sees full chat history, so follow-up questions work naturally:
```
You:  Show me all ACC commentary on John 3:16
App:  [answers from ACC only]

You:  Now show me Abouna Tadros Malaty on the same verse
App:  [knows "same verse" = John 3:16, searches Fr. Tadros only]

You:  How do they differ on the role of faith?
App:  [compares both sources, still in context of John 3:16]
```

**Compare Both mode:** Runs search against each source separately and asks Claude to explicitly compare what each commentary says.

#### Phase 3: Deploy to Render
- Connect Render to `bsaleeb91/Projects` GitHub repo
- Set environment variables (API keys) in Render dashboard
- Upload `commentary.db` to Render's persistent disk
- App gets a permanent public URL: `https://commentary-agent.onrender.com`
- Bookmark on phone — works anywhere with internet

**Render free tier:** App "sleeps" after 15 min inactivity, ~30 sec wake-up time.
**Render paid tier (~$7/month):** Always on, instant response.

---

## Dependencies

```
anthropic
google-api-python-client
google-auth-oauthlib
pypdf
streamlit          # (next phase)
```

Install on Windows:
```powershell
pip install anthropic google-api-python-client google-auth-oauthlib pypdf
```

---

## Known Issues / Gotchas

| Issue | Status |
|-------|--------|
| GitHub raw URL caches old script versions | Workaround: use GitHub API URL (see above) |
| `__pycache__` can cause old code to run | Fix: `Remove-Item -Recurse -Force __pycache__` |
| Google OAuth token was for Gmail/Calendar, not Drive | Fixed: generated new `drive_token.json` with Drive scope |
| Drive API wasn't enabled in Google Cloud project | Fixed: enabled at console.developers.google.com |
| Anthropic Files API 600-page limit | Fixed: switched to on-demand page extraction |
| Anthropic 1M token limit | Fixed: only send matching pages, not whole PDFs |
| PDFs are in nested subfolders | Fixed: recursive folder scanning |
