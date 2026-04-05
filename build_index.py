#!/usr/bin/env python3
"""
build_index.py — Build SQLite FTS5 index from Google Drive PDFs.

Run once before launching app.py (or as part of Render's build command).
Takes 1–2 hours for 110 large PDFs.

Usage:
  python build_index.py

Credentials:
  Reads from environment variables (Render / GitHub Actions):
    GOOGLE_CREDENTIALS_JSON   full contents of credentials.json
    GOOGLE_TOKEN_JSON         full contents of drive_token.json
    DRIVE_FOLDER_ID           Google Drive folder ID to scan

  Falls back to local files if env vars are not set:
    commentary_index.json     for _folder_id, _credentials, _token paths
"""

import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Load .env from same directory
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

DB_PATH = Path(__file__).parent / "commentary.db"
INDEX_FILE = Path(__file__).parent / "commentary_index.json"

CHUNK_SIZE = 500  # words per chunk

# Files that are not actual commentary — skip during indexing
BLACKLIST = {
    "ACCS INTRODUCTION AND BIBLIOGRAPHIC INFORMATION.pdf",
    "MELTHO... Syriac OpenType Fonts for Windows XP.pdf",
    "The Apocrypha ... King James Version.pdf",
    "1470-G.pdf",
    "1470-I.pdf",
    "000 Map_of_the_Old_Testament.pdf",
    "000 Search_Scriptures.pdf",
}


def build_drive_service_from_env():
    """Build Drive service from env vars (Render/CI) or fall back to local files."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")

    if creds_json and token_json:
        # Running in CI / Render — write temp files
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(token_json)
            token_path = tf.name
        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        os.unlink(token_path)
    else:
        # Local dev — read paths from commentary_index.json
        if not INDEX_FILE.exists():
            print("No credentials found. Set GOOGLE_CREDENTIALS_JSON / GOOGLE_TOKEN_JSON env vars,")
            print("or run: python commentary_agent.py sync --set-folder ... to save local config.")
            sys.exit(1)
        index = json.loads(INDEX_FILE.read_text())
        token_path = index.get("_token")
        if not token_path:
            print("No token path in commentary_index.json. Run sync --set-folder first.")
            sys.exit(1)
        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)


def get_folder_id() -> str:
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if folder_id:
        return folder_id
    if INDEX_FILE.exists():
        index = json.loads(INDEX_FILE.read_text())
        folder_id = index.get("_folder_id")
        if folder_id:
            return folder_id
    print("No Drive folder ID found. Set DRIVE_FOLDER_ID env var or run sync --set-folder.")
    sys.exit(1)


def list_drive_pdfs(service, folder_id: str) -> list[dict]:
    """Return all PDFs in the given Drive folder, recursively through subfolders."""
    pdfs = []

    def _collect(fid: str, path: str = ""):
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{fid}' in parents and mimeType='application/pdf' and trashed=false",
                fields="nextPageToken, files(id, name, md5Checksum)",
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                f["_path"] = path
            pdfs.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{fid}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            ).execute()
            for subfolder in resp.get("files", []):
                _collect(subfolder["id"], path=f"{path}/{subfolder['name']}" if path else subfolder["name"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    _collect(folder_id)
    return pdfs


def download_drive_file(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def detect_source(path: str, filename: str) -> str:
    """Infer commentary source from Drive folder path or filename."""
    combined = (path + "/" + filename).lower()
    if "tadros" in combined or "malaty" in combined:
        return "Fr. Tadros Malaty"
    if "ancient christian" in combined or "acc" in combined:
        return "Ancient Christian Commentary"
    return "Unknown"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into ~chunk_size word chunks with slight overlap."""
    words = text.split()
    chunks = []
    overlap = 50
    i = 0
    while i < len(words):
        chunk = words[i: i + chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap
    return chunks


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            filename    TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            chunk_text  TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            source,
            filename,
            chunk_text,
            content=chunks,
            content_rowid=id
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, source, filename, chunk_text)
            VALUES (new.id, new.source, new.filename, new.chunk_text);
        END;
    """)
    conn.commit()


def already_indexed(conn: sqlite3.Connection, filename: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM chunks WHERE filename = ? LIMIT 1", (filename,)
    ).fetchone()
    return row is not None


def index_pdf(conn: sqlite3.Connection, pdf_bytes: bytes, filename: str, source: str):
    """Extract pages, chunk, and insert into DB."""
    import fitz  # pymupdf

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        print(f"    Could not read PDF: {e}")
        return 0

    rows = []
    for i, page in enumerate(doc):
        try:
            text = page.get_text() or ""
        except Exception:
            continue  # skip unreadable page, keep going
        text = text.strip()
        if not text:
            continue
        for chunk in chunk_text(text):
            if chunk.strip():
                rows.append((source, filename, i + 1, chunk))

    if rows:
        conn.executemany(
            "INSERT INTO chunks (source, filename, page_number, chunk_text) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return len(rows)


def main():
    print("Connecting to Google Drive...", flush=True)
    service = build_drive_from_env = build_drive_service_from_env()
    folder_id = get_folder_id()

    print(f"Scanning folder {folder_id} for PDFs...", flush=True)
    all_pdfs = list_drive_pdfs(service, folder_id)
    print(f"Found {len(all_pdfs)} PDFs.\n")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    skipped = 0
    indexed = 0
    for i, pdf_file in enumerate(all_pdfs):
        name = pdf_file["name"]
        source = detect_source(pdf_file.get("_path", ""), name)

        if name in BLACKLIST:
            print(f"[{i+1}/{len(all_pdfs)}] Skipping (blacklisted): {name}")
            skipped += 1
            continue

        if already_indexed(conn, name):
            skipped += 1
            continue

        print(f"[{i+1}/{len(all_pdfs)}] {name} ({source})", flush=True)
        print(f"  Downloading...", end=" ", flush=True)
        try:
            pdf_bytes = download_drive_file(service, pdf_file["id"])
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        print(f"indexing...", end=" ", flush=True)
        n_chunks = index_pdf(conn, pdf_bytes, name, source)
        print(f"{n_chunks} chunks.")
        indexed += 1

    conn.close()
    print(f"\nDone. {indexed} PDFs indexed, {skipped} already in DB.")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
