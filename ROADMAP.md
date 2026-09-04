# Bible Commentary App — Roadmap

**Audience** (decided 2026-09-03): personal study, shared with family and a few
friends. Retrieval quality and coverage matter most; smooth UI and exportable
study notes are wanted. Must serve both verse-specific and non-verse-specific
questions. Not a public product — full auth and enterprise ops are out of scope.

Architecture background: `CONVERSATION_SUMMARY.md`.

---

## The three real problems

### P1. The app has no concept of a church father

**This is the direct cause of "it's missing some church fathers."** `detect_source()`
labels each chunk with its top-level *folder*, and those folders mix authors with
collections. Measured 2026-09-03:

| Label | Chunks | What it actually is |
|---|---|---|
| Nicene and Post-Nicene Fathers | 58,955 (39 files) | **Dozens of fathers.** First Series 9-14 = Chrysostom; Second Series 4 = Athanasius, 6 = Jerome, 8 = Basil, 10-11 = Ambrose... |
| Ancient Christian Commentary | 19,970 | Anthology quoting hundreds of fathers |
| Fathers of the Church | 10,986 | Multi-author series |
| Studia Patristica | 7,992 | Modern academic secondary literature |
| John Chrysostom | 17,584 | One author — who is *also* most of NPNF 9-14 and quoted all through ACC |

Three consequences, all of which you are feeling:

1. **No per-father floor.** `FLOOR_PER_SOURCE = 2` gives all of NPNF the same
   2-slot guarantee as `Severus of Antioch` (8 chunks total). Basil, Gregory,
   Ambrose, and Jerome compete against each other for one bucket's slots, so
   individual fathers vanish even when NPNF is "represented."
2. **Attribution is unusable on ~46% of the corpus** (89,911 chunks under
   NPNF + ACC + Fathers of the Church). A citation reading
   `(Nicene and Post-Nicene Fathers — ...Volume 11.PDF, page 340)` never says
   *who wrote it* — the single most important fact in a patristics tool.
3. **Double-counting inflates breadth.** Chrysostom occupies his own folder,
   most of NPNF 9-14, and much of ACC. "Three sources agree" may be one father
   quoted three times — and exact-hash dedup can't catch it across translations.

**Fix**: extract author-level metadata at index time (volume→father mapping for
NPNF is well-documented and mostly mechanical; ACC attributes each quotation
inline), store `author` alongside `source`, and make it the diversity axis and
the citation unit. Do this in the **same indexing pass** as P2's verse tagging.

### P2. Verse identity isn't structured data (verse/chapter questions)

Chunking is 500-word page slices with no verse metadata (`build_index.py:54-62`),
so a verse lookup depends on the citation string literally appearing in the same
chunk as the commentary. **Measured 2026-09-03, and worse than assumed** —
share of chunks containing a verse citation in *any* form (patterns overlap, so
true coverage is lower than the sum):

| Source | `John 3:16` | `John iii. 16` | `ver./chap.` |
|---|---|---|---|
| Nicene and Post-Nicene Fathers | 7.2% | 2.6% | 8.3% |
| John Chrysostom | 15.1% | **24.3%** | 10.9% |
| Fr. Tadros Malaty | 68.4% | 0.4% | 5.1% |
| Ancient Christian Commentary | 49.6% | 0.1% | 2.4% |

Two conclusions:

1. **80%+ of NPNF — the largest source, 58,955 chunks — carries no verse
   reference of any kind**, so it is simply unreachable by reference keywords.
   Fr. Tadros (68.4%) is well-referenced by comparison. This likely *is* your
   reported symptom: the modern commentary surfaces, the patristic homilies
   don't.
2. **Citation style is source-specific.** Roman numerals dominate the Chrysostom
   folder (24.3% vs 15.1%) but are negligible in NPNF, Fr. Tadros, and ACC — so
   citation-format expansion should be scoped to the sources that need it, not
   applied blanket.

Compounding both, `GATE_RATIO = 0.35` (`app.py:51`) zeroes out any source not
within 35% of the best score, and `CANDIDATE_K = 40` (`app.py:49`) caps
per-source candidates *before* gating, so the right homily can be cut before
selection runs.

### P3. Common-word collapse (thematic/pastoral questions)

"Does God love me more than I love myself?" has keywords (`love`, `God`,
`myself`) that are among the most frequent words in all 196,608 chunks. BM25 has
almost no signal to rank on and returns generic filler. **This is not a tuning
problem** — lexical search cannot serve this question class, and there is no
workaround short of semantic retrieval.

---

## The plan

Deliberately short. Everything else is in the backlog appendix.

### Now — cheap, no re-index, ship together

- **N1. Verify the diagnosis against the DB** (half a day). Query for citation
  formats, run the eval questions through current retrieval, confirm the gate
  actually excludes sources on real questions, check near-duplicate rates. The
  P1 finding above came from ~10 minutes of querying and outranked everything
  reasoned from code alone — so do this *before* investing in P2 or P3 fixes.
- **N2. Patristic vocabulary expansion.** Teach `generate_keywords()` to map
  thematic questions into the fathers' technical terms — *philanthropia* (love
  of mankind), *philautia* (self-love), *agape*, providence, condescension. Best
  effort-to-payoff ratio here: a prompt change that lifts P3 recall immediately.
- **N3. Citation-format expansion.** Emit roman-numeral, abbreviated, and
  chapter-only variants for any reference in the question. Measurement says
  scope this to where it pays: roman numerals matter for the Chrysostom folder
  (24.3% of chunks), not for NPNF/Fr. Tadros/ACC. Expect a modest win — it
  cannot reach the 80% of NPNF that carries no reference at all (that's X3).
- **N4. Reference-aware gate loosening.** When the question names a specific
  verse (regex is enough), raise `CANDIDATE_K` and lower `GATE_RATIO`.
- **N5. Small eval + query log.** 10-15 questions split across P2/P3 classes,
  scored by hand, plus logging of every real question (text, keywords, sources
  retrieved, latency, cost). Intentionally small — enough to catch a regression,
  not a research project. Grow it to 30-50 only before the Next re-index.
  **Score the answer, not just retrieval.** Recall measures what reached the
  model; it says nothing about whether the answer was faithful to the excerpts,
  cited accurately, or actually addressed the question. Perfect retrieval can
  still produce a skimming answer — the synthesis prompt's "prefer breadth over
  repeating one source" pushes that way. Spot-check citations by hand at first;
  an LLM judge scored against the excerpts is the cheap scale-up.
- **N7. Feedback button.** A "this missed something" control that logs the
  question plus what was retrieved. Family and friends will find failures you
  never would, and this is what grows the eval set without you hand-labeling it
  alone — the highest-leverage small feature on this roadmap.
- **N6. Pastoral handling for P3 questions.** Excerpts on self-hatred,
  unworthiness, and mortification can read brutally when returned to someone
  asking whether God loves them. Decide deliberately how the app answers this
  class: present the range of the fathers rather than one verdict, keep the
  frame "here is what the fathers say" rather than a pronouncement about the
  reader, and prefer sources that supply context. Worth getting right before
  sharing more widely — family and friends will ask exactly these questions.

### Next — one overnight re-index, both fixes in the same pass

- **X1. Spike the extractors first** (timeboxed, ~a day). Author detection and
  verse-reference detection on 3-4 representative sources — NPNF, ACC, Fr.
  Tadros, one small single-author folder. If accuracy looks poor here, the full
  re-index is not yet worth running.
- **X2. Author-level metadata** (P1 fix). `author` column; diversity floor and
  dominance cap keyed on author; citations render the father's name.
- **X3. Verse-range tagging** (P2 fix). `verse_ref` / `chunk_verses`, so
  retrieval matches structured references instead of literal strings.
  **Must be a stateful, propagating tagger — not a per-chunk regex.** 80%+ of
  NPNF chunks contain no reference to detect, so the tagger has to find the
  reference at a homily/section heading and carry it forward across following
  chunks until the next heading, tracking book/chapter context as it goes.
  This is the hard part of the whole roadmap and the main thing X1 must derisk.
- **X4. Chunking revisit.** Paragraph/pericope-aware boundaries instead of
  500-word hard cuts. Only worth doing *inside* this pass, never as its own
  re-index.
- **X5. Near-duplicate dedup.** Replace exact-sha1 with near-duplicate detection
  so the same homily in three collections stops eating the budget.
- **X6. Keep the previous DB.** Do not overwrite the Render disk copy until the
  new one beats it on the eval. Right now the re-index is irreversible — this is
  the cheapest risk reduction on the roadmap.

### Later — measured, not assumed

- **L1. Hybrid semantic + lexical retrieval** (the real P3 fix). Embedding index
  fused with BM25 via reciprocal rank fusion. **Anthropic has no first-party
  embeddings endpoint**, so this is a new dependency: recommend a local
  open-source embedding model run during the index build (no per-token cost,
  fits the existing build-then-upload workflow) over a hosted API. Budget
  ~300MB (384-dim) or ~600MB (768-dim) float32 on top of the ~757MB DB; int8
  quantization cuts that ~4x. Confirm Render disk headroom first.
- **L2. Coverage map.** Book × author matrix, nearly free once X2/X3 land.
  Distinguishes "retrieval missed it" from "no father in my library covers
  Habakkuk," and becomes an acquisition list.
- **L3. Precomputed chapter digests + export.** The **Batch API runs at 50%**,
  making this affordable: ~1,189 chapters × ~65K input ≈ 77M tokens ≈ **$86
  one-time** on Sonnet 5 at batch rates (rough). Yields instant answers for the
  commonest question type, a verse-first browse mode, and an exportable,
  correctable corpus of study notes — one job serving four goals.
- **L4. Per-answer export** to Markdown/PDF with citations intact.

> **Trap to avoid on L3**: digests generated *before* X2/X3 land will be built on
> today's weaker retrieval, and improving retrieval afterwards silently makes
> them stale. Stamp each digest with the index version that produced it, and
> plan for regeneration — otherwise that's ~$86 spent on output you then have to
> distrust.

---

## Success criteria

Without targets, "measure" is unfalsifiable. Starting bars, revise once N1 gives
a baseline:

- **P2 (verse questions)**: the expected father appears for ≥90% of eval
  questions; ≥5 distinct *authors* represented on a major-passage question.
- **P3 (thematic questions)**: ≥3 distinct authors with genuinely on-topic
  excerpts; zero answers built from generic filler.
- **Attribution**: 100% of citations name an author, not just a collection.
- **Latency**: unchanged or better on cached/warm queries.
- **Cost**: no worse than today's ~$0.15-0.20/question unless deliberately traded.

---

## Appendix — backlog

Real, just not now. One line each so they stop competing for attention.

- **UI**: mobile layout (family/friends are on phones); conversation persistence;
  source-panel readability (`st.caption()` on long excerpts); Render cold start.
- **Cost/sharing**: shared password (protects the *bill*, not secrecy); spend
  ceiling; depth selector (Standard/Deep/Exhaustive).
- **Corpus**: OCR the image-only PDFs (`049 Ephesians.pdf` and any other file
  `build_index.py` logs as 0 chunks — currently 100% invisible); decide whether
  `Studia Patristica` (modern secondary literature) should compete for slots
  with primary patristic commentary.
- **Ops**: incremental/resumable re-index; DB schema versioning; post-deploy
  smoke check; repo tidy (`debug_*.py` at root, unrelated agents sharing the repo).
- **Back up the source PDFs.** The 551 curated PDFs are the one genuinely
  irreplaceable asset here — the DB is rebuildable from them in a few hours, but
  nothing rebuilds the library. Confirm there's a backup independent of the
  Google Drive folder.
- **Graceful "no results."** Today a miss dead-ends at "No matching content
  found." Better: say which sources *do* cover that book, and offer a broader
  search — a miss should teach the reader something about the library.
- **Model/prompt**: A/B `claude-opus-5` ($5/$25 per MTok) vs. current
  `claude-sonnet-5` ($2/$10) for synthesis — measure, don't assume; structured
  outputs for keyword generation; prompt tuning against the eval. Note prompt
  caching barely helps here — the ~65K of excerpts is unique per question.
- **Deferred outright**: multi-user auth; Files API for small PDFs; citation
  verification and spuria/pseudonymous-work flagging (valuable for patristics,
  but a research project — the "Sources used" panel meets the personal-use bar).

---

## Evidence log

Measured facts, so future work doesn't re-derive them.

- **2026-09-03** — 196,608 chunks / 37 sources / 551 files. NPNF = 58,955 chunks
  in 39 files under one label. NPNF + ACC + Fathers of the Church = 89,911
  chunks (~46% of corpus) with no author-level attribution. Chrysostom appears
  in at least three separate "sources."
- **2026-09-03** — Verse-citation density by source (random 1,500-chunk samples):
  NPNF 7.2% arabic / 2.6% roman / 8.3% `ver.-chap.`; Chrysostom 15.1% / 24.3% /
  10.9%; Fr. Tadros 68.4% / 0.4% / 5.1%; ACC 49.6% / 0.1% / 2.4%. Conclusion:
  80%+ of NPNF has no verse reference to match on, and roman-numeral citation is
  a Chrysostom-folder phenomenon, not a general one.
- **2026-09-03** — Checked and *not* found: reference-dense index/front-matter
  pages polluting retrieval (0 of 4,000 NPNF chunks had ≥15 verse-like refs).
  Extraction quality reads clean; only minor page-number bleed into body text
  (e.g. a chunk starting `523 to deliver us...`). Not worth chasing.
- **2026-09-03** — Anthropic exposes no first-party embeddings endpoint;
  semantic search requires a third-party or local model either way.
- Current pricing: Sonnet 5 $2/$10 per MTok, Opus 5 $5/$25, Haiku 4.5 $1/$5;
  Batch API at 50%.

## Decision log

- **2026-08-24** — Dropped the "Claude guesses relevant filenames" pre-filter; it
  guessed wrong and silently dropped sources whose names it didn't reproduce
  exactly. Replaced by full-corpus search + `select_diverse()`.
- **2026-08-24** — Retired Git LFS for `commentary.db`; it lives on the Render
  persistent disk via `DB_PATH`, gitignored.
- **2026-09-03** — Audience fixed as personal + family/friends; deferred auth,
  citation verification, public-product ops.
- **2026-09-03** — Non-verse-specific questions accepted as a first-class
  requirement, promoting semantic retrieval from "nice to have" to necessary.
- **2026-09-03** — Folder-as-source identified as a category error; author-level
  metadata promoted to the top of the roadmap, ahead of verse tagging.
- **2026-09-03** — Verse tagging (X3) respecified from a per-chunk regex to a
  stateful propagating tagger, after measuring that 80%+ of NPNF chunks contain
  no reference to detect. Citation-format expansion (N3) narrowed from blanket
  to source-scoped on the same evidence.

## Keeping this honest

The eval numbers decide what comes next, not this document. Re-read after each
Now/Next block; log what was tried and rejected — that's the expensive thing to
reconstruct later.
