#!/usr/bin/env python3
"""
PDF Commentary Agent
--------------------
Answers Bible commentary questions using ONLY the PDFs you provide.

Usage:
  # First-time setup — point at your Google Drive folder:
  python commentary_agent.py sync <drive-folder-id> --set-folder \
      --credentials "C:\\Users\\17165\\OneDrive\\...\\credentials.json" \
      --token "C:\\Users\\17165\\OneDrive\\...\\token.json"

  # After setup, just drop PDFs in the Drive folder and run:
  python commentary_agent.py sync

  # Ask questions:
  python commentary_agent.py ask "What does John 3:16 mean?"

  # Manage:
  python commentary_agent.py list
  python commentary_agent.py remove <anthropic-file-id>

How to find your Drive folder ID:
  Open the folder in Google Drive — the ID is the last part of the URL:
  https://drive.google.com/drive/folders/<FOLDER-ID-IS-HERE>
"""

import anthropic
import io
import json
import os
import sys
from pathlib import Path

# Load .env from the same folder as this script
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

INDEX_FILE = Path(__file__).parent / "commentary_index.json"
client = anthropic.Anthropic()


# ── Index helpers ─────────────────────────────────────────────────────────────

def load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {}


def save_index(index: dict):
    INDEX_FILE.write_text(json.dumps(index, indent=2))


# ── Google Drive helpers ──────────────────────────────────────────────────────

def build_drive_service(credentials_path: str, token_path: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(
        token_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token back
        Path(token_path).write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_drive_pdfs(service, folder_id: str) -> list[dict]:
    """Return all PDFs in the given Drive folder (non-recursive)."""
    results = []
    page_token = None
    query = (
        f"'{folder_id}' in parents "
        "and mimeType='application/pdf' "
        "and trashed=false"
    )
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, md5Checksum)",
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def download_drive_file(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_sync(folder_id: str | None, set_folder: bool = False,
             credentials_path: str | None = None, token_path: str | None = None):
    """Sync from Google Drive: upload new PDFs, remove deleted ones."""
    index = load_index()

    # Persist / recall configuration
    if set_folder:
        if not folder_id:
            print("Provide a folder ID when using --set-folder.")
            sys.exit(1)
        if not credentials_path or not token_path:
            print("Provide --credentials and --token when using --set-folder.")
            sys.exit(1)
        index["_folder_id"]    = folder_id
        index["_credentials"]  = credentials_path
        index["_token"]        = token_path
        save_index(index)
        print(f"Configuration saved.")
        print(f"  Drive folder : {folder_id}")
        print(f"  Credentials  : {credentials_path}")
        print(f"  Token        : {token_path}\n")
    else:
        folder_id        = folder_id        or index.get("_folder_id")
        credentials_path = credentials_path or index.get("_credentials")
        token_path       = token_path       or index.get("_token")

    if not all([folder_id, credentials_path, token_path]):
        print(
            "Missing configuration. Run once with --set-folder to save your settings:\n"
            "  python commentary_agent.py sync <folder-id> --set-folder \\\n"
            '      --credentials "C:\\path\\to\\credentials.json" \\\n'
            '      --token "C:\\path\\to\\token.json"'
        )
        sys.exit(1)

    print("Connecting to Google Drive...", flush=True)
    service = build_drive_service(credentials_path, token_path)

    drive_files = list_drive_pdfs(service, folder_id)
    drive_by_id = {f["id"]: f for f in drive_files}

    # Already indexed Drive files: drive_id → anthropic_file_id
    indexed = {
        meta["drive_id"]: aid
        for aid, meta in index.items()
        if not aid.startswith("_") and "drive_id" in meta
    }

    # Upload new files
    new_ids = set(drive_by_id) - set(indexed)
    for drive_id in sorted(new_ids, key=lambda i: drive_by_id[i]["name"]):
        name = drive_by_id[drive_id]["name"]
        print(f"  + Downloading {name} ...", end=" ", flush=True)
        pdf_bytes = download_drive_file(service, drive_id)
        print("uploading ...", end=" ", flush=True)
        uploaded = client.beta.files.upload(
            file=(name, io.BytesIO(pdf_bytes), "application/pdf")
        )
        index[uploaded.id] = {
            "filename": name,
            "drive_id": drive_id,
            "md5": drive_by_id[drive_id].get("md5Checksum", ""),
        }
        save_index(index)
        print(f"done  →  {uploaded.id}")

    # Remove files deleted from Drive
    removed_ids = set(indexed) - set(drive_by_id)
    for drive_id in removed_ids:
        aid  = indexed[drive_id]
        name = index[aid]["filename"]
        try:
            client.beta.files.delete(aid)
        except Exception:
            pass
        del index[aid]
        save_index(index)
        print(f"  - Removed {name} (deleted from Drive)")

    pdf_count = sum(1 for k in index if not k.startswith("_"))
    if not new_ids and not removed_ids:
        print(f"Already up to date. {pdf_count} PDF(s) indexed.")
    else:
        print(f"\n{pdf_count} PDF(s) now indexed.")


def cmd_list():
    """Show all uploaded commentaries."""
    index = load_index()
    pdfs = {k: v for k, v in index.items() if not k.startswith("_")}
    if not pdfs:
        print("No PDFs indexed. Run: python commentary_agent.py sync")
        return
    print(f"{'Anthropic File ID':<40}  Filename")
    print("-" * 70)
    for fid, meta in pdfs.items():
        print(f"{fid:<40}  {meta['filename']}")


def cmd_remove(file_id: str):
    """Delete a file from the Anthropic Files API and remove it from the index."""
    index = load_index()
    if file_id not in index:
        print(f"ID not found in local index: {file_id}")
        return
    try:
        client.beta.files.delete(file_id)
        print(f"Deleted from Anthropic Files API: {file_id}")
    except Exception as e:
        print(f"Warning – could not delete from API ({e}); removing from index anyway.")
    name = index.pop(file_id)["filename"]
    save_index(index)
    print(f"Removed '{name}' from index.")


def cmd_ask(question: str):
    """Answer a question using only the indexed PDF commentaries."""
    index = load_index()
    pdfs = {k: v for k, v in index.items() if not k.startswith("_")}
    if not pdfs:
        print("No PDFs indexed. Run: python commentary_agent.py sync")
        return

    print(f"Searching {len(pdfs)} PDF(s) for an answer...\n")

    doc_blocks = []
    for fid, meta in pdfs.items():
        doc_blocks.append({
            "type": "document",
            "source": {"type": "file", "file_id": fid},
            "title": meta["filename"],
            "citations": {"enabled": True},
        })
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

    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_flag(args: list[str], flag: str) -> tuple[str | None, list[str]]:
    """Extract --flag value from args, return (value, remaining_args)."""
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            value = args[i + 1]
            remaining = args[:i] + args[i + 2:]
            return value, remaining
    return None, args


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "sync":
        set_folder = "--set-folder" in args
        args = [a for a in args if a != "--set-folder"]

        credentials, args = parse_flag(args, "--credentials")
        token, args       = parse_flag(args, "--token")
        folder_id         = args[0] if args else None

        cmd_sync(folder_id, set_folder=set_folder,
                 credentials_path=credentials, token_path=token)

    elif command == "ask":
        if not args:
            print('Usage: python commentary_agent.py ask "Your question here"')
            sys.exit(1)
        cmd_ask(" ".join(args))

    elif command == "list":
        cmd_list()

    elif command == "remove":
        if not args:
            print("Usage: python commentary_agent.py remove <file_id>")
            sys.exit(1)
        cmd_remove(args[0])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
