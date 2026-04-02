#!/usr/bin/env python3
"""
PDF Commentary Agent
--------------------
Answers Bible commentary questions using ONLY the PDFs you provide.

Usage:
  python commentary_agent.py sync <folder>   # index every PDF in a folder
  python commentary_agent.py ask "What does John 3:16 mean?"
  python commentary_agent.py list
  python commentary_agent.py remove <file_id>

Tip: set a default folder once with --set-folder, then just run 'sync' with no arguments:
  python commentary_agent.py sync ~/Commentaries --set-folder
  python commentary_agent.py sync
"""

import anthropic
import json
import sys
from pathlib import Path

INDEX_FILE = Path(__file__).parent / "commentary_index.json"
client = anthropic.Anthropic()


# ── Index helpers ─────────────────────────────────────────────────────────────

def load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {}


def save_index(index: dict):
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def get_default_folder() -> Path | None:
    index = load_index()
    folder = index.get("_folder")
    return Path(folder) if folder else None


def set_default_folder(folder: Path):
    index = load_index()
    index["_folder"] = str(folder)
    save_index(index)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_sync(folder_str: str | None, set_folder: bool = False):
    """Sync a folder: upload new PDFs, remove deleted ones from the index."""
    if folder_str is None:
        folder = get_default_folder()
        if folder is None:
            print("No folder set. Run: python commentary_agent.py sync <folder> --set-folder")
            sys.exit(1)
    else:
        folder = Path(folder_str).expanduser().resolve()

    if not folder.is_dir():
        print(f"Not a directory: {folder}")
        sys.exit(1)

    if set_folder:
        set_default_folder(folder)
        print(f"Default folder saved: {folder}")

    index = load_index()
    # PDFs currently on disk (by resolved path string)
    disk_pdfs = {str(p): p for p in folder.rglob("*.pdf")}

    # Already-indexed paths
    indexed_paths = {meta["original_path"]: fid for fid, meta in index.items() if not fid.startswith("_")}

    # Upload new PDFs (on disk but not in index)
    new_paths = set(disk_pdfs) - set(indexed_paths)
    for path_str in sorted(new_paths):
        p = disk_pdfs[path_str]
        print(f"  + Uploading {p.name} ...", end=" ", flush=True)
        with p.open("rb") as f:
            uploaded = client.beta.files.upload(file=(p.name, f, "application/pdf"))
        index[uploaded.id] = {"filename": p.name, "original_path": path_str}
        save_index(index)
        print(f"done  →  {uploaded.id}")

    # Remove PDFs that were deleted from disk
    removed_paths = set(indexed_paths) - set(disk_pdfs)
    for path_str in removed_paths:
        fid = indexed_paths[path_str]
        name = index[fid]["filename"]
        try:
            client.beta.files.delete(fid)
        except Exception:
            pass
        del index[fid]
        save_index(index)
        print(f"  - Removed {name} (no longer on disk)")

    pdf_count = sum(1 for k in index if not k.startswith("_"))
    if not new_paths and not removed_paths:
        print(f"Already up to date. {pdf_count} PDF(s) indexed.")
    else:
        print(f"\n{pdf_count} PDF(s) now indexed.")


def cmd_add(paths: list[str]):
    """Upload PDFs to the Files API and record their IDs."""
    index = load_index()
    for path_str in paths:
        p = Path(path_str).expanduser().resolve()
        if not p.exists():
            print(f"  [skip] File not found: {p}")
            continue
        if p.suffix.lower() != ".pdf":
            print(f"  [skip] Not a PDF: {p.name}")
            continue
        print(f"  Uploading {p.name} ...", end=" ", flush=True)
        with p.open("rb") as f:
            uploaded = client.beta.files.upload(
                file=(p.name, f, "application/pdf"),
            )
        index[uploaded.id] = {"filename": p.name, "original_path": str(p)}
        save_index(index)
        print(f"done  →  {uploaded.id}")
    print(f"\n{len(index)} PDF(s) in index.")


def cmd_list():
    """Show all uploaded commentaries."""
    index = load_index()
    if not index:
        print("No PDFs indexed. Use: python commentary_agent.py add <file.pdf>")
        return
    print(f"{'File ID':<40}  Filename")
    print("-" * 65)
    for fid, meta in index.items():
        print(f"{fid:<40}  {meta['filename']}")


def cmd_remove(file_id: str):
    """Delete a file from the Files API and remove it from the index."""
    index = load_index()
    if file_id not in index:
        print(f"ID not found in local index: {file_id}")
        return
    try:
        client.beta.files.delete(file_id)
        print(f"Deleted from Files API: {file_id}")
    except Exception as e:
        print(f"Warning – could not delete from API ({e}); removing from local index anyway.")
    name = index.pop(file_id)["filename"]
    save_index(index)
    print(f"Removed '{name}' from index.")


def cmd_ask(question: str):
    """Answer a question using only the indexed PDF commentaries."""
    index = load_index()
    if not index:
        print("No PDFs indexed. Add some first:\n  python commentary_agent.py add <file.pdf>")
        return

    print(f"Searching {len(index)} PDF(s) for an answer...\n")

    # Build the document blocks — one per PDF
    doc_blocks = []
    for fid, meta in index.items():
        doc_blocks.append({
            "type": "document",
            "source": {"type": "file", "file_id": fid},
            "title": meta["filename"],
            "citations": {"enabled": True},
        })

    # Add the user question last
    doc_blocks.append({"type": "text", "text": question})

    system_prompt = (
        "You are a Bible commentary assistant. "
        "You have been given a set of PDF commentary documents. "
        "Answer the user's question using ONLY the information found in these documents. "
        "Do not use any outside knowledge. "
        "If a verse or topic is not covered in the provided documents, say so clearly. "
        "When you cite information, mention which document it came from."
    )

    with client.beta.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": doc_blocks}],
        betas=["files-api-2025-04-14"],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

    print()  # newline after streamed response


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "sync":
        folder_arg = None
        set_folder_flag = False
        remaining = sys.argv[2:]
        if "--set-folder" in remaining:
            set_folder_flag = True
            remaining = [a for a in remaining if a != "--set-folder"]
        if remaining:
            folder_arg = remaining[0]
        cmd_sync(folder_arg, set_folder=set_folder_flag)

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python commentary_agent.py add <file.pdf> [more.pdf ...]")
            sys.exit(1)
        cmd_add(sys.argv[2:])

    elif command == "ask":
        if len(sys.argv) < 3:
            print('Usage: python commentary_agent.py ask "Your question here"')
            sys.exit(1)
        cmd_ask(" ".join(sys.argv[2:]))

    elif command == "list":
        cmd_list()

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python commentary_agent.py remove <file_id>")
            sys.exit(1)
        cmd_remove(sys.argv[2])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
