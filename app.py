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
# Two depths, because cost is close to linear in the number of excerpts sent:
# ~150 chunks is ~65K input tokens (~$0.20/question on Sonnet 5), while ~40 is
# ~17K (~$0.055). Most questions are single-verse lookups that don't need the
# larger budget, so Standard is the default and Deep is reserved for thematic,
# doctrinal, or comparative questions that genuinely draw on many fathers.
#
# `gate_ratio`: a source qualifies for a guaranteed passage only if its best
# match is within this fraction of the single best match corpus-wide. Higher
# ratio = stricter gate = fewer sources. Standard gates harder on purpose: at a
# 40-chunk budget it is better to quote 6-8 fathers coherently than to spread
# 40 orphan fragments across 18 of them.
DEPTH_PRESETS = {
    "Standard": {"cap": 40, "gate_ratio": 0.45},
    "Deep": {"cap": 150, "gate_ratio": 0.35},
}

# No single source may take more than this share of the budget during merit
# fill. This is deliberately a fraction of `cap` and NOT a function of how many
# sources cleared the gate: deriving it from the qualifying count made the gate
# and the cap fight each other -- a stricter gate left fewer qualifiers, which
# made the per-source allowance *larger*. Measured on "John 3:16", a 0.60 gate
# admitted 3 sources, which set the old allowance to 26 of 40 slots and let one
# commentary take 65% of the budget.
MAX_SOURCE_SHARE = 0.25
DEFAULT_DEPTH = "Standard"  # also the fallback when depth classification fails

# Per-source candidates pulled from SQL before Python selects (cheap -- fetching
# more candidates costs ~nothing).
CANDIDATE_K = 40

# A qualifying source is guaranteed one *anchor* chunk expanded by this many
# neighbours on each side. A single chunk is roughly one page here and usually
# cuts mid-argument, so the unit of the floor is a contiguous passage rather
# than a lone excerpt. Raising the old per-source floor from 1 to 2 would not
# have fixed that: two independent BM25 hits from one source can come from
# different volumes entirely.
PASSAGE_RADIUS = 1


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

def generate_query_plan(
    client: anthropic.Anthropic,
    question: str,
) -> tuple[list[str], str]:
    """Generate FTS keywords and a retrieval depth for the question.

    Depth rides along on the keyword call rather than being a second request:
    this call already runs for every question, so classifying here costs no
    extra latency and no extra money.

    There is no source pre-filter step -- Claude was previously asked to guess
    relevant sources from filenames alone, before seeing any content. That both
    missed sources it guessed wrong on and silently dropped any source whose
    name it didn't reproduce character-for-character. Retrieval now always
    searches the full corpus and lets `select_passages()` pick sources by what
    they actually contain.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f'Question: "{question}"\n\n'
                "Respond with exactly two lines and nothing else:\n"
                "DEPTH: simple or complex\n"
                "KEYWORDS: comma-separated search keywords\n\n"
                "DEPTH is \"simple\" for a lookup about one specific verse or a "
                "short passage. DEPTH is \"complex\" for thematic, doctrinal, "
                "pastoral or comparative questions, anything spanning multiple "
                "passages, and anything asking what several fathers say.\n\n"
                "KEYWORDS are for a full-text search of Bible commentaries. "
                "Include verse references AND synonyms/related terms. "
                "Prefer specific phrases over bare numbers -- write \"John 3:16\", "
                "never a bare \"3:16\" (it matches unrelated footnote citations).\n\n"
                "Example:\n"
                "DEPTH: simple\n"
                "KEYWORDS: John 3:16, For God so loved, eternal life, believe, faith"
            ),
        }],
    )
    text = response.content[0].text.strip()

    depth = DEFAULT_DEPTH
    keyword_line = text
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("DEPTH:"):
            # Only "complex" escalates -- an unparseable or unexpected value
            # falls back to the cheaper depth rather than silently costing 4x.
            if line.split(":", 1)[1].strip().lower().startswith("complex"):
                depth = "Deep"
        elif line.upper().startswith("KEYWORDS:"):
            keyword_line = line.split(":", 1)[1]

    keywords = [k.strip() for k in keyword_line.split(",") if k.strip()]
    return keywords, depth


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
#  2. select_passages() -- gate + one guaranteed passage per qualifying source
#     + merit fill in Python, so a handful of verse-indexed sources can't take
#     every slot (see DEPTH_PRESETS above for why a flat floor isn't enough).
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


def expand_anchor(
    conn: sqlite3.Connection,
    anchor_id: int,
    radius: int = PASSAGE_RADIUS,
) -> list[int]:
    """Chunk ids forming a contiguous passage centred on `anchor_id`.

    build_index.py inserts chunks in document order -- page by page, chunk by
    chunk within a page -- so consecutive ids are consecutive text of the same
    PDF (verified against the production DB: ids 5000-5008 are pages 234-242 of
    one volume). Expansion is clipped to the anchor's own (source, filename) so
    a passage never runs off the end of one book into the start of the next --
    filename alone is not unique, since build_index.py indexes same-named files
    under different sources.
    """
    rows = conn.execute(
        """
        SELECT id FROM chunks
        WHERE id BETWEEN ? AND ?
          AND source   = (SELECT source   FROM chunks WHERE id = ?)
          AND filename = (SELECT filename FROM chunks WHERE id = ?)
        ORDER BY id
        """,
        (anchor_id - radius, anchor_id + radius, anchor_id, anchor_id),
    ).fetchall()
    return [row[0] for row in rows]


def select_passages(
    conn: sqlite3.Connection,
    candidates: list[sqlite3.Row],
    cap: int,
    gate_ratio: float,
    radius: int = PASSAGE_RADIUS,
) -> list[int]:
    """Pick up to `cap` chunk ids: one contiguous passage per relevant source,
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
    # Strongest sources claim their passage first, so that when the budget runs
    # out it is the weakest matches that go unrepresented.
    qualifying.sort(key=lambda src: by_source[src][0]["r"])

    selected: list[int] = []
    seen: set[int] = set()
    per_source_count: dict[str, int] = {}

    # Pass 1: one anchor per qualifying source, expanded into a passage.
    for src in qualifying:
        if len(selected) >= cap:
            break
        for cid in expand_anchor(conn, by_source[src][0]["rid"], radius):
            if cid in seen or len(selected) >= cap:
                continue
            seen.add(cid)
            selected.append(cid)
            per_source_count[src] = per_source_count.get(src, 0) + 1

    # Pass 2: merit fill, with a per-source cap so a handful of strong sources
    # can't crowd out the diversity the passage pass just established.
    dominance_cap = max(2 * radius + 1, int(cap * MAX_SOURCE_SHARE))
    for row in sorted(candidates, key=lambda row: row["r"]):
        if len(selected) >= cap:
            break
        if row["rid"] in seen:
            continue
        if per_source_count.get(row["src"], 0) >= dominance_cap:
            continue
        seen.add(row["rid"])
        selected.append(row["rid"])
        per_source_count[row["src"]] = per_source_count.get(row["src"], 0) + 1

    return selected[:cap]


def fetch_texts_and_dedupe(
    conn: sqlite3.Connection,
    selected: list[int],
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

    order = {cid: i for i, cid in enumerate(selected)}
    rows = fetch_by_ids(selected)
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
    cap: int = DEPTH_PRESETS[DEFAULT_DEPTH]["cap"],
    gate_ratio: float = DEPTH_PRESETS[DEFAULT_DEPTH]["gate_ratio"],
) -> list[sqlite3.Row]:
    """Retrieve up to `cap` chunks.

    sources=None: search the whole corpus with the gate/passage/merit algorithm
    in select_passages(), so results aren't dominated by whichever source
    happens to be the most verse-indexed.

    sources=[...]: the user (or Compare mode) explicitly chose these sources --
    honor that choice directly and split `cap` evenly across them rather than
    gating, since there's nothing to gate against. Contiguous runs still get
    stitched back together by format_context().
    """
    if not keywords:
        return []
    fts_query = build_fts_query(keywords)

    if sources:
        per_source_cap = max(1, cap // len(sources))
        candidates = fetch_candidates(conn, fts_query, sources=sources, candidate_k=per_source_cap)
        selected = [row["rid"] for row in sorted(candidates, key=lambda row: row["r"])[:cap]]
    else:
        candidates = fetch_candidates(conn, fts_query, sources=None, candidate_k=CANDIDATE_K)
        selected = select_passages(conn, candidates, cap=cap, gate_ratio=gate_ratio)

    return fetch_texts_and_dedupe(conn, selected, candidates, cap)


def strip_overlap(previous: str, text: str, max_overlap: int = 60) -> str:
    """Drop the leading words of `text` that repeat the tail of `previous`.

    build_index.py overlaps chunks by OVERLAP words, but it chunks each page
    separately -- so consecutive ids overlap only when they came from the same
    page, and share nothing when they straddle a page boundary. The overlap is
    therefore measured rather than assumed; stripping a fixed 50 words would
    eat real text at every page break.
    """
    prev_words, words = previous.split(), text.split()
    for n in range(min(max_overlap, len(prev_words), len(words)), 0, -1):
        if prev_words[-n:] == words[:n]:
            return " ".join(words[n:])
    return text


def format_context(rows: list[sqlite3.Row]) -> str:
    """Render rows as excerpt blocks, merging contiguous chunks into a single
    passage so the model sees continuous prose instead of the same passage
    broken across repeated headers with its overlap duplicated.
    """
    if not rows:
        return ""

    ordered = sorted(rows, key=lambda row: (row["source"], row["filename"], row["id"]))
    blocks: list[str] = []
    run: list[sqlite3.Row] = []

    def flush() -> None:
        if not run:
            return
        first, last = run[0], run[-1]
        pages = (
            f"page {first['page_number']}"
            if first["page_number"] == last["page_number"]
            else f"pages {first['page_number']}-{last['page_number']}"
        )
        text = first["chunk_text"]
        for prev, cur in zip(run, run[1:]):
            text += " " + strip_overlap(prev["chunk_text"], cur["chunk_text"])
        blocks.append(f"[{first['source']} -- {first['filename']}, {pages}]\n{text}")
        run.clear()

    for row in ordered:
        contiguous = (
            run
            and row["source"] == run[-1]["source"]
            and row["filename"] == run[-1]["filename"]
            and row["id"] == run[-1]["id"] + 1
        )
        if not contiguous:
            flush()
        run.append(row)
    flush()

    return "\n\n---\n\n".join(blocks)


# -- Answer generation ---------------------------------------------------------

def build_system_prompt(
    compare_sources: list[str] | None = None,
    depth: str = DEFAULT_DEPTH,
) -> str:
    base = (
        "You are a Bible commentary assistant. "
        "Answer using ONLY the commentary excerpts provided -- no outside knowledge, ever. "
        "Do NOT fabricate quotes, page numbers, or content not present in the excerpts. "
        "Every quote must be verbatim from the excerpts. "
        "If the excerpts do not contain commentary on the topic asked, say so plainly. "
        "Cite sources as: (Source -- filename, page N), using only page numbers from the excerpts.\n\n"
        "Quote the fathers directly and often, in their own words and in full sentences, "
        "rather than paraphrasing them. Their actual language is the point of this library. "
        "Name the father wherever an excerpt identifies one, rather than citing only the "
        "collection it came from.\n\n"
        "You will typically receive excerpts from many sources at once. Synthesize across them "
        "rather than walking through excerpts in order: organize the answer by theme or by "
        "question, note where sources agree, and call out where they genuinely diverge. "
        "Include a source that appears only once or twice rather than skipping it."
    )
    if depth == "Deep":
        # Deep sends ~4x the excerpts because the question is thematic or
        # doctrinal. Without this the model applies the same compression it
        # would to a one-verse lookup and surveys 17 sources in two paragraphs.
        base += (
            "\n\nThis question was judged thematic or doctrinal, so you have been given a "
            "large body of excerpts. Answer in proportion to it: develop each theme instead "
            "of listing it, follow an argument through where a father makes one, and quote "
            "substantially. Aim for a full treatment the reader can study from -- not a "
            "summary of what is available."
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
    depth: str = DEFAULT_DEPTH,
):
    messages = list(history[-(MAX_HISTORY * 2):])
    messages.append({
        "role": "user",
        "content": f"Commentary excerpts:\n\n{context}\n\n---\n\nQuestion: {question}",
    })
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=build_system_prompt(compare_sources, depth),
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
    st.header("Depth")
    depth_choice = st.radio(
        "Search depth",
        ["Auto", "Standard", "Deep"],
        index=0,
        help=(
            "Auto reads the question: Standard for a single-verse lookup, "
            "Deep for thematic or comparative questions. "
            "Standard is ~$0.05 a question, Deep ~$0.20."
        ),
    )

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
        raw_keywords, auto_depth = generate_query_plan(client, question)
        keywords = clean_keywords(raw_keywords)

        depth = auto_depth if depth_choice == "Auto" else depth_choice
        preset = DEPTH_PRESETS[depth]
        cap, gate_ratio = preset["cap"], preset["gate_ratio"]

        status.write(f"Keywords: {', '.join(keywords) or '(none usable)'}")
        status.write(
            f"Depth: {depth} ({cap} excerpts)"
            + (" -- chosen automatically" if depth_choice == "Auto" else "")
        )

        if compare_mode:
            # Split the retrieval budget evenly across the sources being compared.
            per_source_cap = max(10, cap // len(selected_sources))
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
            all_rows = fts_search(conn, keywords, sources=selected_sources, cap=cap)
            context = format_context(all_rows)
            status.write(f"{len(all_rows)} excerpts from {len(selected_sources)} selected source(s)")

        else:
            # All sources -- gate/passage/merit selection decides what's relevant
            # by content, not by Claude guessing from filenames.
            all_rows = fts_search(conn, keywords, sources=None, cap=cap, gate_ratio=gate_ratio)
            context = format_context(all_rows)
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
                depth,
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
