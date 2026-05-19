#!/usr/bin/env python3
"""
app.py -- Streamlit Bible Commentary Chat App

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

_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "commentary.db")))
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 10
FTS_TOP_N = 20


# -- Data helpers --------------------------------------------------------------

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
def get_sources(_conn) -> list[str]:
    rows = _conn.execute(
        "SELECT DISTINCT source FROM chunks ORDER BY source"
    ).fetchall()
    return [r[0] for r in rows]


# -- Claude calls --------------------------------------------------------------

def select_sources_and_keywords(
    client: anthropic.Anthropic,
    question: str,
    all_sources: list[str],
) -> tuple[list[str], list[str]]:
    """One Claude call: pick relevant sources AND generate search keywords."""
    source_list = "\n".join(f"- {s}" for s in all_sources)
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f'Question: "{question}"\n\n'
                f"Available commentary sources:\n{source_list}\n\n"
                "Respond in exactly this format (no other text):\n"
                "SOURCES:\n"
                "<source1>\n"
                "<source2>\n"
                "KEYWORDS:\n"
                "<keyword1>, <keyword2>, <keyword3>\n\n"
                "SOURCES: list only the sources most likely to contain commentary on this question. "
                "Use the exact source names from the list above.\n"
                "KEYWORDS: verse references AND synonyms/related terms for full-text search "
                "(e.g. for 'John 3:16' -> John 3:16, 3:16, For God so loved, eternal life, believe, faith)."
            ),
        }],
    )
    text = response.content[0].text.strip()

    selected_sources: list[str] = []
    keywords: list[str] = []
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line == "SOURCES:":
            section = "sources"
        elif line == "KEYWORDS:":
            section = "keywords"
        elif section == "sources" and line:
            selected_sources.append(line)
        elif section == "keywords" and line:
            keywords = [k.strip() for k in line.split(",") if k.strip()]

    return selected_sources, keywords


def generate_keywords(
    client: anthropic.Anthropic,
    question: str,
) -> list[str]:
    """Generate FTS keywords when sources are already known."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                f'Question: "{question}"\n\n'
                "Generate search keywords for a full-text search of Bible commentaries. "
                "Include verse references AND synonyms/related terms. "
                "Respond with ONLY a comma-separated list of keywords, nothing else.\n"
                "Example: John 3:16, 3:16, For God so loved, eternal life, believe, faith"
            ),
        }],
    )
    return [k.strip() for k in response.content[0].text.strip().split(",") if k.strip()]


# -- Search --------------------------------------------------------------------

def fts_search(
    conn: sqlite3.Connection,
    keywords: list[str],
    sources: list[str] | None = None,
    top_n: int = FTS_TOP_N,
) -> list[sqlite3.Row]:
    if not keywords:
        return []

    fts_query = " OR ".join(f'"{k}"' for k in keywords)
    conditions = ["chunks_fts MATCH ?"]
    params: list = [fts_query]

    if sources:
        placeholders = ", ".join("?" * len(sources))
        conditions.append(f"c.source IN ({placeholders})")
        params.extend(sources)

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
            f"[{row['source']} -- {row['filename']}, page {row['page_number']}]\n"
            f"{row['chunk_text']}"
        )
    return "\n\n---\n\n".join(parts)


# -- Answer generation ---------------------------------------------------------

def build_system_prompt(compare_sources: list[str] | None = None) -> str:
    base = (
        "You are a Bible commentary assistant. "
        "Answer using ONLY the commentary excerpts provided -- no outside knowledge, ever. "
        "Do NOT fabricate quotes, page numbers, or content not present in the excerpts. "
        "Every quote must be verbatim from the excerpts. "
        "If the excerpts do not contain commentary on the topic asked, say so plainly. "
        "Cite sources as: (Source -- filename, page N), using only page numbers from the excerpts."
    )
    if compare_sources:
        names = " vs. ".join(compare_sources)
        base += (
            f"\n\nThe user wants a comparison across these sources: {names}. "
            "Structure your answer by source -- summarize what each says, "
            "then note where they agree or differ. "
            "If a source has no excerpts on the topic, state that clearly."
        )
    return base


def stream_answer(
    client: anthropic.Anthropic,
    question: str,
    context: str,
    history: list[dict],
    compare_sources: list[str] | None,
):
    messages = list(history[-(MAX_HISTORY * 2):])
    messages.append({
        "role": "user",
        "content": f"Commentary excerpts:\n\n{context}\n\n---\n\nQuestion: {question}",
    })
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=build_system_prompt(compare_sources),
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


# -- UI ------------------------------------------------------------------------

st.set_page_config(page_title="Bible Commentary", page_icon="📖", layout="wide")
st.title("📖 Bible Commentary")
st.caption("Answers drawn exclusively from your PDF commentary library.")

conn = get_db()
if conn is None:
    st.error("Database not found. Run `python build_index.py` first.")
    st.stop()

client = get_anthropic_client()
all_sources = get_sources(conn)

# Sidebar
with st.sidebar:
    st.header("Sources")
    selected_sources = st.multiselect(
        "Filter by source",
        options=all_sources,
        placeholder="All sources (auto-selected)",
        help="Leave blank to search all sources. Select 2+ to enable Compare mode.",
    )

    compare_mode = False
    if len(selected_sources) >= 2:
        compare_mode = st.toggle("Compare selected sources", value=False)

    st.divider()
    with st.expander("How to use"):
        st.markdown("""
**What to ask**
- *"What does John 3:16 mean?"*
- *"What do the fathers say about baptism?"*
- *"What does Chrysostom say about the Eucharist?"*

**Selecting sources**
Leave blank to search all sources -- the app picks the most relevant ones automatically.
Select one to focus. Select two or more and toggle **Compare** for a side-by-side.

**Hallucination prevention**
Claude only uses retrieved excerpts -- never outside knowledge.
The **Sources used** expander shows exactly what it had to work with.

**Tips**
- Be specific -- verse references work best
- The app remembers the last 10 turns
- If an answer seems off, check Sources used to verify
""")

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
        all_rows: list[sqlite3.Row] = []
        context = ""

        if compare_mode:
            # Generate keywords once, search each selected source separately
            keywords = generate_keywords(client, question)
            status.write(f"Keywords: {', '.join(keywords)}")
            context_blocks = []
            for source in selected_sources:
                rows = fts_search(conn, keywords, sources=[source])
                all_rows.extend(rows)
                block = format_context(rows) or "(No matching excerpts found.)"
                context_blocks.append(f"=== {source} ===\n\n{block}")
                status.write(f"{source}: {len(rows)} excerpts")
            context = "\n\n".join(context_blocks)

        elif selected_sources:
            # User picked specific sources -- just generate keywords
            keywords = generate_keywords(client, question)
            status.write(f"Keywords: {', '.join(keywords)}")
            all_rows = fts_search(conn, keywords, sources=selected_sources)
            context = format_context(all_rows)

        else:
            # All sources -- Claude picks the relevant ones + keywords
            picked, keywords = select_sources_and_keywords(client, question, all_sources)
            valid = [s for s in picked if s in set(all_sources)]
            status.write(f"Sources: {', '.join(valid) or 'all'} | Keywords: {', '.join(keywords)}")
            all_rows = fts_search(conn, keywords, sources=valid or None)
            context = format_context(all_rows)

        if not context:
            status.update(label="No matching excerpts found.", state="error")
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
            for chunk in stream_answer(
                client, question, context, history_for_claude,
                selected_sources if compare_mode else None,
            ):
                full_answer += chunk
                placeholder.markdown(full_answer + "▌")
            placeholder.markdown(full_answer)

        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.messages.append({"role": "assistant", "content": full_answer})

        if len(st.session_state.messages) > MAX_HISTORY * 2:
            st.session_state.messages = st.session_state.messages[-(MAX_HISTORY * 2):]

        with st.expander("Sources used", expanded=False):
            if all_rows:
                for row in all_rows:
                    st.markdown(
                        f"**{row['source']} -- {row['filename']}, page {row['page_number']}**"
                    )
                    st.caption(row["chunk_text"])
                    st.divider()
            else:
                st.write("No excerpts retrieved.")

    elif not context:
        st.warning("No matching content found in your commentaries for that question.")
