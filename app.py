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
from pathlib import Path

# Load .env from same directory
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
import sqlite3
from pathlib import Path

import anthropic
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "commentary.db"
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 10   # number of conversation turns to keep in context
FTS_TOP_N = 20     # max chunks returned from FTS search

SOURCES = {
    "All": None,
    "Fr. Tadros Malaty": "Fr. Tadros Malaty",
    "Ancient Christian Commentary": "Ancient Christian Commentary",
}

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


def generate_keywords(client: anthropic.Anthropic, question: str) -> list[str]:
    """Ask Claude to expand the question into FTS keywords + synonyms."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Question: \"{question}\"\n\n"
                "Return ONLY a comma-separated list of search keywords for this question. "
                "Include: verse references (e.g. John 3:16), key terms, and relevant synonyms. "
                "Example: John 3:16, 3:16, eternal life, believe, faith, salvation, love"
            ),
        }],
    )
    return [k.strip() for k in response.content[0].text.strip().split(",") if k.strip()]


def fts_search(conn: sqlite3.Connection, keywords: list[str],
               source_filter: str | None, top_n: int = FTS_TOP_N) -> list[sqlite3.Row]:
    """Full-text search across chunks, optionally filtered by source."""
    if not keywords:
        return []

    # Build FTS query: OR across all keywords
    fts_query = " OR ".join(f'"{k}"' for k in keywords)

    if source_filter:
        rows = conn.execute(
            """
            SELECT c.source, c.filename, c.page_number, c.chunk_text
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ? AND c.source = ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, source_filter, top_n),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT c.source, c.filename, c.page_number, c.chunk_text
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, top_n),
        ).fetchall()

    return rows


def format_context(rows: list[sqlite3.Row]) -> str:
    """Format DB rows into a context block for Claude."""
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
        "Answer the user's question using ONLY the commentary excerpts provided. "
        "Do not use outside knowledge. "
        "If the topic is not covered in the provided excerpts, say so clearly. "
        "Cite sources as: (Commentary Name, filename, page N)."
    )
    if mode == "Compare Both":
        base += (
            "\n\nThe user has selected Compare Both mode. "
            "Explicitly compare what Fr. Tadros Malaty says versus what the Ancient Christian Commentary says. "
            "If one source does not cover this verse or topic, state that clearly."
        )
    return base


def stream_answer(client: anthropic.Anthropic, question: str, context: str,
                  history: list[dict], mode: str):
    """Stream Claude's answer and yield text chunks."""
    system = build_system_prompt(mode)

    # Build messages: trimmed history + current question with context
    messages = list(history[-MAX_HISTORY * 2:])  # keep last N turns (user+assistant pairs)
    messages.append({
        "role": "user",
        "content": (
            f"Commentary excerpts:\n\n{context}\n\n"
            f"---\n\nQuestion: {question}"
        ),
    })

    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def compare_both_search(conn: sqlite3.Connection, keywords: list[str],
                        top_n: int = FTS_TOP_N) -> str:
    """Search each source separately and combine into labelled context."""
    tadros_rows = fts_search(conn, keywords, "Fr. Tadros Malaty", top_n // 2)
    acc_rows = fts_search(conn, keywords, "Ancient Christian Commentary", top_n // 2)

    parts = []
    if tadros_rows:
        parts.append("=== Fr. Tadros Malaty ===\n\n" + format_context(tadros_rows))
    else:
        parts.append("=== Fr. Tadros Malaty ===\n\n(No matching excerpts found.)")

    if acc_rows:
        parts.append("=== Ancient Christian Commentary ===\n\n" + format_context(acc_rows))
    else:
        parts.append("=== Ancient Christian Commentary ===\n\n(No matching excerpts found.)")

    return "\n\n".join(parts)


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Bible Commentary", page_icon="📖", layout="wide")
st.title("📖 Bible Commentary")
st.caption("Answers drawn exclusively from your PDF commentary library.")

# Check DB
conn = get_db()
if conn is None:
    st.error(
        "Database not found. Run `python build_index.py` to build the search index first."
    )
    st.stop()

client = get_anthropic_client()

# Source selector
mode = st.radio(
    "Source",
    options=["All", "Fr. Tadros Malaty", "Ancient Christian Commentary", "Compare Both"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

# Conversation history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if question := st.chat_input("Ask a question about the Bible..."):
    # Show user message
    with st.chat_message("user"):
        st.markdown(question)

    # Generate keywords
    with st.status("Searching commentaries...", expanded=False) as status:
        keywords = generate_keywords(client, question)
        status.write(f"Keywords: {', '.join(keywords)}")

        # FTS search
        if mode == "Compare Both":
            context = compare_both_search(conn, keywords)
        else:
            source_filter = SOURCES.get(mode)
            rows = fts_search(conn, keywords, source_filter)
            context = format_context(rows)

        if not context:
            status.update(label="No matching excerpts found.", state="error")
            st.warning("No matching content found in your commentaries for that question.")
        else:
            n_chunks = context.count("[") - context.count("===")
            status.update(label=f"Found relevant excerpts. Answering...", state="complete")

    if context:
        # Build history for Claude (role: user/assistant pairs without the injected context)
        history_for_claude = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        # Stream answer
        with st.chat_message("assistant"):
            answer_placeholder = st.empty()
            full_answer = ""
            for chunk in stream_answer(client, question, context, history_for_claude, mode):
                full_answer += chunk
                answer_placeholder.markdown(full_answer + "▌")
            answer_placeholder.markdown(full_answer)

        # Save to history
        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.messages.append({"role": "assistant", "content": full_answer})

        # Trim history to last MAX_HISTORY turns
        if len(st.session_state.messages) > MAX_HISTORY * 2:
            st.session_state.messages = st.session_state.messages[-(MAX_HISTORY * 2):]
