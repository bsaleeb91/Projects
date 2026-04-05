#!/usr/bin/env python3
"""
Remove non-commentary files from commentary.db.
Run once after pulling this update.
"""
import sqlite3
from pathlib import Path
from build_index import BLACKLIST

DB_PATH = Path(__file__).parent / "commentary.db"
conn = sqlite3.connect(DB_PATH)

for filename in BLACKLIST:
    count = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE filename = ?", (filename,)
    ).fetchone()[0]
    if count:
        conn.execute("DELETE FROM chunks WHERE filename = ?", (filename,))
        print(f"Removed {count} chunks from: {filename}")
    else:
        print(f"Not in DB (already clean): {filename}")

conn.commit()

# Rebuild FTS index to stay in sync
conn.executescript("""
    INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');
""")
conn.commit()
conn.close()
print("\nDone.")
