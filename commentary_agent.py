#!/usr/bin/env python3
"""
PDF Commentary Agent
--------------------
Answers Bible commentary questions using ONLY the PDFs you provide.

Usage:
  python commentary_agent.py add path/to/commentary.pdf [another.pdf ...]
  python commentary_agent.py ask "What does John 3:16 mean?"
  python commentary_agent.py list
  python commentary_agent.py remove <file_id>
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


# ── Commands ──────────────────────────────────────────────────────────────────

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

    if command == "add":
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
