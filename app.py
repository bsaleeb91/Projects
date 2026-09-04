#!/usr/bin/env python3
"""
app.py -- Streamlit Bible Commentary Chat App

Answers questions from your PDF commentary library using SQLite FTS5 search
and Claude Sonnet 5. Run build_index.py first to build the database.

Usage:
  streamlit run app.py

Environment variables:
  ANTHROPIC_API_KEY    required
"""

import hashlib
import os
import re
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
MODEL = "claude-sonnet-5"
MAX_HISTORY = 10

# -- Retrieval tuning -----------------------------------------------------------
# RETRIEVAL_CAP: total excerpts fed to the model per question. ~150 chunks is
# ~65K tokens -- comfortable inside the model's 1M context window.
# CANDIDATE_K: per-source candidates pulled from SQL before Python does
# gate/floor/merit selection (cheap -- fetching more candidates costs ~nothing).
# FLOOR_PER_SOURCE: guaranteed excerpts for any source that clears the gate.
# GATE_RATIO: a source qualifies for the floor only if its best match score is
# within this fraction of the single best match across the whole corpus.
# Without a gate, a flat per-source floor spends most of the budget forcing in
# sources that have nothing relevant to say (e.g. a source with 8 total chunks
# on a question about John 3:16) -- see the retrieval-overhaul plan for the
# measurements behind these numbers.
RETRIEVAL_CAP = 150
CANDIDATE_K = 40
FLOOR_PER_SOURCE = 2
GATE_RATIO = 0.35


# -- Data helpers --------------------------------------------------------------

@st.cache_resource
def get_anthropic_client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


@st.cache_resource
def get_db():
    if not DB_PATH.exists():
        return None
    # Read-only URI: the app never writes, and this skips write-lock overhead.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -64000")  # 64MB page cache per connection
    # Warm the FTS index pages so the first real query after a cold Render
    # restart isn't the one paying full disk-read latency.
    conn.execute("SELECT 1 FROM chunks_fts WHERE chunks_fts MATCH 'the' LIMIT 1").fetchall()
    return conn


@st.cache_data
def get_sources(_conn) -> list[str]:
    rows = _conn.execute(
        "SELECT DISTINCT source FROM chunks ORDER BY source"
    ).fetchall()
    return [r[0] for r in rows]


# -- Claude calls --------------------------------------------------------------

def generate_keywords(
    client: anthropic.Anthropic,
    question: str,
) -> list[str]:
    """Generate FTS keywords for the question.

    There is no source pre-filter step anymore -- Claude was previously asked to
    guess relevant sources from filenames alone, before seeing any content. That
    both missed sources it guessed wrong on and silently dropped any source whose
    name it didn't reproduce character-for-character. Retrieval now always
    searches the full corpus and lets `select_diverse()` pick sources by what
    they actually contain.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                f'Question: "{question}"\n\n'
                "Generate search keywords for a full-text search of Bible commentaries. "
                "Include verse references AND synonyms/related terms. "
                "Prefer specific phrases over bare numbers -- write \"John 3:16\", "
                "never a bare \"3:16\" (it matches unrelated footnote citations). "
                "Respond with ONLY a comma-separated list of keywords, nothing else.\n"
                "Example: John 3:16, For God so loved, eternal life, believe, faith"
            ),
        }],
    )
    return [k.strip() for k in response.content[0].text.strip().split(",") if k.strip()]


# A keyword that strips down to only digits/punctuation (e.g. a bare "3:16")
# tokenizes into a garbage phrase match against footnote/citation-index pages
# rather than the verse -- drop these rather than search on them.
_DIGIT_ONLY_RE = re.compile(r"^[\d\s:.\-]+$")


def clean_keywords(keywords: list[str]) -> list[str]:
    """De-dupe, drop digit-only noise keywords, cap the list length."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        kw = kw.strip()
        if not kw or kw.lower() in seen or _DIGIT_ONLY_RE.match(kw):
            continue
        cleaned.append(kw)
        seen.add(kw.lower())
        if len(cleaned) >= 8:  # more generic terms dilute bm25 signal, not help it
            break
    return cleaned


def build_fts_query(keywords: list[str]) -> str:
    """Build an FTS5 MATCH string scoped to chunk_text only.

    chunks_fts is a 3-column table (source, filename, chunk_text). An
    unqualified MATCH searches all three columns -- so a keyword like
    "Chrysostom" doesn't just match text mentioning Chrysostom, it matches
    every one of that source's 27,000+ chunks by the `source` column alone,
    silently flooding and skewing the result set. Scoping to `chunk_text`
    fixes that at the query level.
    """
    escaped = [k.replace('"', '""') for k in keywords]  # FTS5 escapes " by doubling it
    or_clause = " OR ".join(f'"{k}"' for k in escaped)
    return f"chunk_text : ({or_clause})"


# -- Search --------------------------------------------------------------------
#
# Retrieval is two stages:
#  1. fetch_candidates() -- one SQL query returns each source's top-K matches
#     as (id, source, rank) only, no text yet. Scoped to chunk_text (see
#     build_fts_query) and using 'rank MATCH bm25(...)' rather than calling
#     bm25() directly, because bm25() cannot run inside a window function --
#     `rank MATCH 'bm25(weights)'` is FTS5's documented way to set the same
#     weights in a form that ROW_NUMBER() OVER (...) can sit next to.
#  2. select_diverse() -- gate + guaranteed floor + merit fill in Python, so a
#     handful of verse-indexed sources can't take every slot (see RETRIEVAL_CAP
#     comment above for why a flat floor alone isn't enough).
# Only the winning ids get their chunk_text fetched, in fetch_texts_and_dedupe.


def fetch_candidates(
    conn: sqlite3.Connection,
    fts_query: str,
    sources: list[str] | None = None,
    candidate_k: int = CANDIDATE_K,
) -> list[sqlite3.Row]:
    """Top-`candidate_k` matches per source, as (rid, src, r) -- no chunk_text."""
    where_extra = ""
    params: list = [fts_query]
    if sources:
        placeholders = ", ".join("?" * len(sources))
        where_extra = f"AND c.source IN ({placeholders})"
        params.extend(sources)
    params.append(candidate_k)

    sql = f"""
        SELECT rid, src, r FROM (
            SELECT f.rowid AS rid,
                   c.source AS src,
                   rank AS r,
                   ROW_NUMBER() OVER (PARTITION BY c.source ORDER BY rank) AS rn
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ?
              AND rank MATCH 'bm25(0.0, 0.0, 1.0)'
              {where_extra}
        )
        WHERE rn <= ?
    """
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # Malformed FTS5 syntax (e.g. an unbalanced quote that slipped past
        # escaping) should degrade to "no results", not crash the request.
        return []


def select_diverse(
    candidates: list[sqlite3.Row],
    cap: int = RETRIEVAL_CAP,
    floor: int = FLOOR_PER_SOURCE,
    gate_ratio: float = GATE_RATIO,
) -> list[sqlite3.Row]:
    """Pick up to `cap` candidates: a guaranteed floor per relevant source,
    then fill by merit, capped so no single source can dominate the fill.
    `r` (rank) is more negative for a better match -- MIN(r) is the best score.
    """
    if not candidates:
        return []

    by_source: dict[str, list[sqlite3.Row]] = {}
    for row in candidates:
        by_source.setdefault(row["src"], []).append(row)
    for rows in by_source.values():
        rows.sort(key=lambda row: row["r"])

    global_best = min(row["r"] for row in candidates)
    threshold = gate_ratio * global_best  # global_best is negative; threshold is less negative
    qualifying = [src for src, rows in by_source.items() if rows[0]["r"] <= threshold]

    selected: list[sqlite3.Row] = []
    selected_ids: set[int] = set()
    per_source_count: dict[str, int] = {}

    # Pass 1: guaranteed floor for every source that clears the relevance gate.
    for src in qualifying:
        for row in by_source[src][:floor]:
            if row["rid"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["rid"])
                per_source_count[src] = per_source_count.get(src, 0) + 1

    # Pass 2: merit fill, with a per-source cap so a handful of strong sources
    # can't crowd out the diversity the floor pass just established.
    n_qualified = max(len(qualifying), 1)
    dominance_cap = max(6, (cap // n_qualified) * 2)
    for row in sorted(candidates, key=lambda row: row["r"]):
        if len(selected) >= cap:
            break
        if row["rid"] in selected_ids:
            continue
        if per_source_count.get(row["src"], 0) >= dominance_cap:
            continue
        selected.append(row)
        selected_ids.add(row["rid"])
        per_source_count[row["src"]] = per_source_count.get(row["src"], 0) + 1

    return selected[:cap]


def fetch_texts_and_dedupe(
    conn: sqlite3.Connection,
    selected: list[sqlite3.Row],
    candidates: list[sqlite3.Row],
    cap: int,
) -> list[sqlite3.Row]:
    """Fetch chunk_text for the selected ids, drop exact-duplicate text (front
    matter / boilerplate pages repeat verbatim across a PDF), and backfill from
    the remaining candidates so dedup doesn't shrink the result below `cap`.
    """
    if not selected:
        return []

    def fetch_by_ids(ids: list[int]) -> list[sqlite3.Row]:
        if not ids:
            return []
        placeholders = ", ".join("?" * len(ids))
        return conn.execute(
            f"SELECT id, source, filename, page_number, chunk_text "
            f"FROM chunks WHERE id IN ({placeholders})",
            ids,
        ).fetchall()

    order = {row["rid"]: i for i, row in enumerate(selected)}
    rows = fetch_by_ids([row["rid"] for row in selected])
    rows.sort(key=lambda row: order.get(row["id"], len(order)))

    seen_hashes: set[str] = set()
    used_ids: set[int] = set()
    deduped: list[sqlite3.Row] = []
    for row in rows:
        h = hashlib.sha1(row["chunk_text"].encode("utf-8")).hexdigest()
        used_ids.add(row["id"])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        deduped.append(row)

    if len(deduped) < cap:
        leftover = [c for c in sorted(candidates, key=lambda row: row["r"]) if c["rid"] not in used_ids]
        need = cap - len(deduped)
        fill_rows = fetch_by_ids([c["rid"] for c in leftover[:need]])
        for row in fill_rows:
            h = hashlib.sha1(row["chunk_text"].encode("utf-8")).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                deduped.append(row)

    return deduped


def fts_search(
    conn: sqlite3.Connection,
    keywords: list[str],
    sources: list[str] | None = None,
    cap: int = RETRIEVAL_CAP,
) -> list[sqlite3.Row]:
    """Retrieve up to `cap` chunks.

    sources=None: search the whole corpus with the gate/floor/merit algorithm
    in select_diverse(), so results aren't dominated by whichever source
    happens to be the most verse-indexed.

    sources=[...]: the user (or Compare mode) explicitly chose these sources --
    honor that choice directly and split `cap` evenly across them rather than
    gating, since there's nothing to gate against.
    """
    if not keywords:
        return []
    fts_query = build_fts_query(keywords)

    if sources:
        per_source_cap = max(1, cap // len(sources))
        candidates = fetch_candidates(conn, fts_query, sources=sources, candidate_k=per_source_cap)
        selected = sorted(candidates, key=lambda row: row["r"])[:cap]
    else:
        candidates = fetch_candidates(conn, fts_query, sources=None, candidate_k=CANDIDATE_K)
        selected = select_diverse(candidates, cap=cap)

    return fetch_texts_and_dedupe(conn, selected, candidates, cap)


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
        "Cite sources as: (Source -- filename, page N), using only page numbers from the excerpts.\n\n"
        "You will typically receive excerpts from many sources at once. Synthesize across them "
        "rather than walking through excerpts in order: organize the answer by theme or by "
        "question, note where sources agree, and call out where they genuinely diverge. Prefer "
        "breadth of witness over repeating one source at length -- if a source appears only once "
        "or twice, that is still worth including, not a reason to skip it."
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
        max_tokens=16000,
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
        keywords = clean_keywords(generate_keywords(client, question))
        status.write(f"Keywords: {', '.join(keywords) or '(none usable)'}")

        if compare_mode:
            # Split the retrieval budget evenly across the sources being compared.
            per_source_cap = max(10, RETRIEVAL_CAP // len(selected_sources))
            context_blocks = []
            for source in selected_sources:
                rows = fts_search(conn, keywords, sources=[source], cap=per_source_cap)
                all_rows.extend(rows)
                block = format_context(rows) or "(No matching excerpts found.)"
                context_blocks.append(f"=== {source} ===\n\n{block}")
                status.write(f"{source}: {len(rows)} excerpts")
            context = "\n\n".join(context_blocks)

        elif selected_sources:
            # User picked specific sources -- honor that directly, no gating.
            all_rows = fts_search(conn, keywords, sources=selected_sources, cap=RETRIEVAL_CAP)
            context = format_context(all_rows)
            status.write(f"{len(all_rows)} excerpts from {len(selected_sources)} selected source(s)")

        else:
            # All sources -- gate/floor/merit selection decides what's relevant
            # by content, not by Claude guessing from filenames.
            all_rows = fts_search(conn, keywords, sources=None, cap=RETRIEVAL_CAP)
            n_sources = len({row["source"] for row in all_rows})
            status.write(f"{len(all_rows)} excerpts from {n_sources} sources")

        if not context:
            status.update(label="No matching excerpts found.", state="error")
        else:
            status.update(label="Found relevant excerpts. Answering...", state="complete")

    if context:
        history_for_claude = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        n_sources = len({row["source"] for row in all_rows})
        st.caption(f"Drawing on {n_sources} source(s), {len(all_rows)} excerpts")

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("_Thinking..._")
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

        with st.expander(f"Sources used ({n_sources} sources, {len(all_rows)} excerpts)", expanded=False):
            if all_rows:
                by_source: dict[str, list[sqlite3.Row]] = {}
                for row in all_rows:
                    by_source.setdefault(row["source"], []).append(row)
                for source in sorted(by_source):
                    st.markdown(f"#### {source} ({len(by_source[source])})")
                    for row in by_source[source]:
                        st.markdown(f"**{row['filename']}, page {row['page_number']}**")
                        st.caption(row["chunk_text"])
                        st.divider()
            else:
                st.write("No excerpts retrieved.")

    elif not context:
        st.warning("No matching content found in your commentaries for that question.")
