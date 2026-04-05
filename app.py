#!/usr/bin/env python3
"""
app.py — Streamlit Bible Commentary Chat App

Answers questions from your PDF commentary library using SQLite FTS5 search
and Claude Sonnet 4.6. Run build_index.py first to build the database.

Usage:
  streamlit run app.py

Environment variables:
  ANTHROPIC_API_KEY    required
"""

import os
import sqlite3
from pathlib import Path

import anthropic
import streamlit as st

# Load .env from same directory
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "commentary.db"
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 10   # conversation turns kept in Claude context
FTS_TOP_N = 20     # max chunks returned from FTS search

# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_anthropic_client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


@st.cache_resource
def get_db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data
def get_filenames(_conn, source_filter: str | None) -> list[str]:
    """Return distinct filenames in the DB, optionally filtered by source."""
    if source_filter:
        rows = _conn.execute(
            "SELECT DISTINCT filename FROM chunks WHERE source = ? ORDER BY filename",
            (source_filter,),
        ).fetchall()
    else:
        rows = _conn.execute(
            "SELECT DISTINCT filename FROM chunks ORDER BY filename"
        ).fetchall()
    return [r[0] for r in rows]


def select_files_and_keywords(
    client: anthropic.Anthropic, question: str, filenames: list[str]
) -> tuple[list[str], list[str]]:
    """Single Claude call: pick relevant files AND generate search keywords."""
    file_list = "\n".join(f"- {f}" for f in filenames)
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Question: \"{question}\"\n\n"
                f"Available commentary files:\n{file_list}\n\n"
                "Respond in exactly this format (no other text):\n"
                "FILES:\n"
                "<filename1>\n"
                "<filename2>\n"
                "KEYWORDS:\n"
                "<keyword1>, <keyword2>, <keyword3>\n\n"
                "FILES: list only the filenames most likely to contain commentary on this question.\n"
                "KEYWORDS: verse references AND synonyms/related terms for full-text search "
                "(e.g. for 'John 3:16' → John 3:16, 3:16, For God so loved, eternal life, believe, faith)."
            ),
        }],
    )
    text = response.content[0].text.strip()

    selected_files: list[str] = []
    keywords: list[str] = []
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line == "FILES:":
            section = "files"
        elif line == "KEYWORDS:":
            section = "keywords"
        elif section == "files" and line:
            selected_files.append(line)
        elif section == "keywords" and line:
            keywords = [k.strip() for k in line.split(",") if k.strip()]

    return selected_files, keywords


def fts_search(
    conn: sqlite3.Connection,
    keywords: list[str],
    source_filter: str | None,
    filenames: list[str] | None = None,
    top_n: int = FTS_TOP_N,
) -> list[sqlite3.Row]:
    """FTS search, optionally filtered by source and/or specific filenames."""
    if not keywords:
        return []

    fts_query = " OR ".join(f'"{k}"' for k in keywords)

    conditions = ["chunks_fts MATCH ?"]
    params: list = [fts_query]

    if source_filter:
        conditions.append("c.source = ?")
        params.append(source_filter)

    if filenames:
        placeholders = ", ".join("?" * len(filenames))
        conditions.append(f"c.filename IN ({placeholders})")
        params.extend(filenames)

    params.append(top_n)
    where = " AND ".join(conditions)

    return conn.execute(
        f"""
        SELECT c.source, c.filename, c.page_number, c.chunk_text
        FROM chunks_fts f
        JOIN chunks c ON c.id = f.rowid
        WHERE {where}
        ORDER BY rank
        LIMIT ?
        """,
        params,
    ).fetchall()


def format_context(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return ""
    parts = []
    for row in rows:
        parts.append(
            f"[{row['source']} — {row['filename']}, page {row['page_number']}]\n"
            f"{row['chunk_text']}"
        )
    return "\n\n---\n\n".join(parts)


def build_system_prompt(mode: str) -> str:
    base = (
        "You are a Bible commentary assistant. "
        "Answer using ONLY the commentary excerpts provided below — no outside knowledge, ever. "
        "Do NOT fabricate quotes, page numbers, or content not explicitly present in the excerpts. "
        "Every quote must be verbatim from the excerpts. "
        "If the excerpts do not contain commentary on the topic asked, say so plainly — do not guess or extrapolate. "
        "Cite sources as: (Source — filename, page N), using only page numbers that appear in the excerpts."
    )
    if mode == "Compare Both":
        base += (
            "\n\nThe user has selected Compare Both mode. "
            "Explicitly compare what Fr. Tadros Malaty says versus what the Ancient Christian Commentary says. "
            "If one source does not cover this topic in the provided excerpts, state that clearly."
        )
    return base


def stream_answer(
    client: anthropic.Anthropic,
    question: str,
    context: str,
    history: list[dict],
    mode: str,
):
    messages = list(history[-(MAX_HISTORY * 2):])
    messages.append({
        "role": "user",
        "content": f"Commentary excerpts:\n\n{context}\n\n---\n\nQuestion: {question}",
    })
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=build_system_prompt(mode),
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def search_one_source(
    client: anthropic.Anthropic,
    conn: sqlite3.Connection,
    question: str,
    source: str | None,
    status,
) -> str:
    """Select relevant files, run FTS, return formatted context."""
    filenames = get_filenames(conn, source)
    selected, keywords = select_files_and_keywords(client, question, filenames)
    status.write(f"Files: {', '.join(selected) or 'all'} | Keywords: {', '.join(keywords)}")
    rows = fts_search(conn, keywords, source, selected or None)
    return format_context(rows)


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Bible Commentary", page_icon="📖", layout="wide")
st.title("📖 Bible Commentary")
st.caption("Answers drawn exclusively from your PDF commentary library.")

conn = get_db()
if conn is None:
    st.error("Database not found. Run `python build_index.py` first.")
    st.stop()

client = get_anthropic_client()

mode = st.radio(
    "Source",
    options=["All", "Fr. Tadros Malaty", "Ancient Christian Commentary", "Compare Both"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("Ask a question about the Bible..."):
    with st.chat_message("user"):
        st.markdown(question)

    with st.status("Searching commentaries...", expanded=False) as status:
        if mode == "Compare Both":
            tadros_context = search_one_source(client, conn, question, "Fr. Tadros Malaty", status)
            acc_context = search_one_source(client, conn, question, "Ancient Christian Commentary", status)
            tadros_block = "=== Fr. Tadros Malaty ===\n\n" + (tadros_context or "(No matching excerpts found.)")
            acc_block = "=== Ancient Christian Commentary ===\n\n" + (acc_context or "(No matching excerpts found.)")
            context = tadros_block + "\n\n" + acc_block
        else:
            source_filter = None if mode == "All" else mode
            context = search_one_source(client, conn, question, source_filter, status)

        if not context:
            status.update(label="No matching excerpts found.", state="error")
            st.warning("No matching content found in your commentaries for that question.")
        else:
            status.update(label="Found relevant excerpts. Answering...", state="complete")

    if context:
        history_for_claude = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_answer = ""
            for chunk in stream_answer(client, question, context, history_for_claude, mode):
                full_answer += chunk
                placeholder.markdown(full_answer + "▌")
            placeholder.markdown(full_answer)

        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.messages.append({"role": "assistant", "content": full_answer})

        if len(st.session_state.messages) > MAX_HISTORY * 2:
            st.session_state.messages = st.session_state.messages[-(MAX_HISTORY * 2):]
