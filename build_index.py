#!/usr/bin/env python3
"""
build_index.py — Build SQLite FTS5 index from a local folder of PDFs.

Run once on your laptop before uploading commentary.db to Render.
Takes several hours for ~500 large PDFs — run it overnight.

Usage:
  python build_index.py --folder "/path/to/002. Patristics"

  Optional: specify a custom DB output path
  python build_index.py --folder "/path/to/002. Patristics" --db /path/to/commentary.db

Folder structure expected:
  <root>/
    <Source Name>/        <- subfolder name becomes the source label in the app
      book1.pdf
      book2.pdf
      <subfolder>/        <- nested folders supported; source is always top-level name
        book3.pdf
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "commentary.db"

CHUNK_SIZE = 500   # words per chunk
OVERLAP    = 50    # word overlap between chunks

# Filenames to skip regardless of source folder
BLACKLIST = {
    "ACCS INTRODUCTION AND BIBLIOGRAPHIC INFORMATION.pdf",
    "MELTHO... Syriac OpenType Fonts for Windows XP.pdf",
    "The Apocrypha ... King James Version.pdf",
    "1470-G.pdf",
    "1470-I.pdf",
    "000 Map_of_the_Old_Testament.pdf",
    "000 Search_Scriptures.pdf",
}


# ── Core helpers ──────────────────────────────────────────────────────────────

def detect_source(pdf_path: Path, root: Path) -> str:
    """Top-level subfolder name relative to root = source label."""
    try:
        return pdf_path.relative_to(root).parts[0]
    except (ValueError, IndexError):
        return pdf_path.stem


def chunk_text(text: str) -> list[str]:
    """Split text into ~CHUNK_SIZE word chunks with slight overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i: i + CHUNK_SIZE]))
        i += CHUNK_SIZE - OVERLAP
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

        -- Without this, `SELECT DISTINCT source FROM chunks` (app.py's
        -- get_sources, used to populate the sidebar) does a full table scan
        -- of every chunk -- 37s measured on the 751MB/196K-row production DB.
        CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);
    """)
    conn.commit()


def already_indexed(conn: sqlite3.Connection, filename: str, source: str) -> bool:
    """Check by (source, filename) so same-named files in different sources both get indexed."""
    return conn.execute(
        "SELECT 1 FROM chunks WHERE source = ? AND filename = ? LIMIT 1",
        (source, filename),
    ).fetchone() is not None


def index_pdf(conn: sqlite3.Connection, pdf_path: Path, source: str) -> int:
    """Extract pages, chunk text, insert into DB. Returns number of chunks added."""
    import fitz  # pymupdf

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"    Could not open: {e}")
        return 0

    rows = []
    for i, page in enumerate(doc):
        try:
            text = (page.get_text() or "").strip()
        except Exception:
            continue
        if not text:
            continue
        for chunk in chunk_text(text):
            if chunk.strip():
                rows.append((source, pdf_path.name, i + 1, chunk))

    if rows:
        conn.executemany(
            "INSERT INTO chunks (source, filename, page_number, chunk_text) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build commentary FTS5 index from a local folder of PDFs."
    )
    parser.add_argument(
        "--folder", required=True,
        help="Root folder — one subfolder per commentary source",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help=f"Output SQLite database path (default: {DB_PATH})",
    )
    args = parser.parse_args()

    root = Path(args.folder).resolve()
    if not root.exists():
        print(f"Error: folder not found: {root}")
        raise SystemExit(1)

    db_path = Path(args.db)
    print(f"Root folder : {root}")
    print(f"Database    : {db_path}\n")

    all_pdfs = sorted(p for p in root.rglob("*") if p.suffix.lower() == ".pdf")
    print(f"Found {len(all_pdfs)} PDFs.\n")

    conn = sqlite3.connect(db_path)
    init_db(conn)

    indexed = skipped = errors = 0

    for i, pdf_path in enumerate(all_pdfs):
        name   = pdf_path.name
        source = detect_source(pdf_path, root)
        prefix = f"[{i+1}/{len(all_pdfs)}]"

        if name in BLACKLIST:
            print(f"{prefix} BLACKLISTED -- {name}")
            skipped += 1
            continue

        if already_indexed(conn, name, source):
            print(f"{prefix} Already indexed -- {name}")
            skipped += 1
            continue

        print(f"{prefix} [{source}] {name}", flush=True)
        n = index_pdf(conn, pdf_path, source)

        if n == 0:
            print(f"  -> 0 chunks (image-only or unreadable PDF)")
            errors += 1
        else:
            print(f"  -> {n} chunks")
            indexed += 1

    conn.close()

    size_mb = db_path.stat().st_size / 1e6
    print(f"\n{'='*55}")
    print(f"Done.")
    print(f"  Indexed  : {indexed} PDFs")
    print(f"  Skipped  : {skipped} (already indexed or blacklisted)")
    print(f"  Errors   : {errors} (image-only or unreadable)")
    print(f"  DB size  : {size_mb:.1f} MB")
    print(f"  DB path  : {db_path}")


if __name__ == "__main__":
    main()
