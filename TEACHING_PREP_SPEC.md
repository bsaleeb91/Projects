# Teaching Prep — Specification

Draft, 2026-09-09. Companion to `ROADMAP.md` (retrieval) and
`CONVERSATION_SUMMARY.md` (architecture).

---

## Overview

A mode in the commentary app that turns **a passage** into **a prepared lesson**:
what the fathers say on it, organized for someone who has to teach it on Sunday.

The existing chat answers a question. This produces a document you carry into a
classroom.

### Why this and not thematic browse

Considered and deferred: a thematic entry point ("what does the Church say about
my identity in Christ"). Deferred because it depends on a curated
modern-question → patristic-vocabulary translation layer that doesn't exist yet,
and because a curated theme page is *intolerant* of mediocre retrieval — its
whole promise is "trust this." Teaching prep is **tolerant**: the teacher is an
expert user filtering candidates, so imperfect ranking still saves an hour.

Build the tolerant product while P1/P2/P3 are open. Teaching prep also generates
the labeled data (passage + which excerpts a human kept) that makes the thematic
product buildable later. The reverse order bootstraps nothing.

### Who it's for

The Sunday School teacher already in this repo — `psalm_memorization_agent/`
serves one class of 7th graders. Same user, same weekly deadline, adjacent job.

---

## Non-goals

- **Not a sermon generator.** It does not write the lesson. It assembles the
  material and organizes it; the teacher writes the lesson.
- **Not a paraphraser.** The fathers are quoted, not summarized into Claude's
  voice. Model prose exists only to frame, connect, and label.
- **No multi-user, no auth.** Same personal-use bar as the rest of the app.
- **No new index build.** Runs against `commentary.db` as it exists today.

---

## Input

| Field | Required | Values | Notes |
|---|---|---|---|
| `passage` | yes | free text | "Luke 15:11-32", "Romans 8", "the prodigal son" |
| `audience` | yes | `kids` (7-11) / `youth` (12-17) / `adults` | Default `youth` |
| `length` | yes | `20min` / `45min` / `90min` | Controls excerpt budget and section depth |
| `focus` | no | free text | "I want to land on repentance, not on the older brother" |
| `sources` | no | multi-select | Defaults to whole corpus |

`passage` is resolved by Claude to a book/chapter/verse range, then normalized.
Unresolvable input returns a clarifying prompt, not a guess.

---

## Output

One document, ten sections. Rendered in-app, exported to Markdown and PDF.

### 1. Passage
The text, verse by verse, verse numbers preserved. Public-domain translation in
the DB (see Open Questions — translation choice is unresolved).

### 2. The through-line
One or two sentences: what this passage is about, as the fathers read it. Written
by the model, grounded in sections 3–4. This is the sentence the teacher builds
the lesson around.

### 3. What the fathers say, verse by verse
**The core section.** The passage is split into verse blocks (2–6 verses, at
natural breaks). Each block gets:

- the verses
- 2–4 excerpts, each with the **father's name**, the source, and the page
- excerpts quoted at length — a paragraph, not a clause

This is the section that is 70% of the value and 70% of the token budget.

### 4. Where they converge
3–5 points the fathers agree on, each tagged with which fathers hold it. The
spine of a lesson.

### 5. Where they differ
Points of genuine divergence, both readings given. Frequently the most teachable
material in the document — a class remembers a disagreement.

Empty is a valid result. The section says "the fathers in your library read this
the same way" rather than manufacturing a controversy.

### 6. Images and illustrations the fathers use
Analogies, metaphors, and word-pictures lifted from the excerpts — Chrysostom's
physician, ship, furnace, debtor. **No index of these exists anywhere**, they are
the single most usable thing in a patristic library for teaching children, and
they fall out of a classification pass over chunks already retrieved.

Expected to be the feature that gets the app opened.

### 7. Questions your class will ask
5–8 questions this passage provokes *from this audience*, each with an answer
grounded in the retrieved excerpts. A 7th grader's questions about Luke 15 are
not an adult's.

Where the excerpts don't answer a question, it says so — that is useful
information for a teacher at 10pm on Saturday.

### 8. What the fathers connect this to
Cross-references the fathers themselves make — other passages they quote while
commenting on this one. Mechanically extracted from the excerpts (see
`ROADMAP.md` X3 / quote-matching), lightly labeled by the model.

### 9. Teaching notes
Audience-specific, and the section that makes this usable rather than merely
impressive:

- which excerpts will land as-is, and which need paraphrase
- what to skip — fourth-century rhetoric aimed at adults in Antioch is often
  wrong for a 12-year-old, and the app should say which
- where the fathers are severe, and how to frame it (see `ROADMAP.md` N6)
- a suggested time allocation across the verse blocks

### 10. Sources used
Every source and page cited, once, as a list. Lets the teacher go read the
original.

---

## Output shape — worked example

Passage `Luke 15:11-32`, audience `youth`, length `45min`.

**This is the document skeleton, not generated content.** Every excerpt slot is
filled from a `chunk_id` at generation time. No patristic text is invented here
or anywhere in this system — see Grounding Rules.

```markdown
# Luke 15:11-32 — The Prodigal Son
Youth (12-17) · 45 minutes · prepared 2026-09-09 · index v1

## The through-line
[1-2 sentences, model-written, grounded in §4]

## The passage
11  A certain man had two sons...
[...through v32]

## What the fathers say

### vv. 11-13 — the younger son asks for his inheritance
> [excerpt, 120-200 words, verbatim from chunk]
— **John Chrysostom**, NPNF First Series Vol. 10, p. 412

> [excerpt]
— **Cyril of Alexandria**, Commentary on Luke, p. 88

### vv. 14-16 — the famine and the swine
[2-4 excerpts, same shape]

### vv. 17-20a — "he came to himself"
[2-4 excerpts]

### vv. 20b-24 — the father runs
[2-4 excerpts]

### vv. 25-32 — the older brother
[2-4 excerpts]

## Where they converge
1. [point] — Chrysostom, Cyril, Ambrose
2. [point] — Cyril, Jerome
[3-5 total]

## Where they differ
**[Question at issue]**
- [Reading A] — Father X
- [Reading B] — Father Y

## Images the fathers use
- **[image]** — Chrysostom, NPNF I.10 p. 415 — [one line on how to use it]
[3-8 total]

## Questions your class will ask
**"Wasn't the older brother right to be angry?"**
[answer grounded in excerpts, or: "your library doesn't address this directly"]
[5-8 total]

## What the fathers connect this to
- Genesis 1:26 — [why, one line] — quoted by Cyril
- Ezekiel 18:23 — quoted by Chrysostom
[from quote-matching over the retrieved excerpts]

## Teaching notes
- **Lead with** vv. 17-20a. [why]
- **Skip** [excerpt] — [reason]
- **Paraphrase** [excerpt] — [reason]
- **Handle with care**: [where the fathers are severe, and the framing]
- **Time**: 10 / 15 / 15 / 5 across the four blocks

## Sources used
- Nicene and Post-Nicene Fathers, First Series Vol. 10 — pp. 412, 415, 418
- [...]
```

---

## Pipeline

Five stages. Stages 1–2 reuse `app.py` unchanged.

### Stage 1 — Resolve the passage
Claude call (cheap, ~200 tokens out): free text → `book`, `chapter`,
`verse_start`, `verse_end`. Ambiguous input returns options, not a guess.

### Stage 2 — Retrieve
Reuses `fts_search()`, `select_passages()`, `format_context()` as they stand.

Keywords are generated from the *passage*, not from a user question — a
different call from `generate_query_plan()`:

- the reference in every citation format (`Luke 15:11`, `Luke xv. 11`,
  `ver. 11`, `chap. xv`) — cheap here because the source-scoping evidence in
  `ROADMAP.md` N3 applies
- distinctive phrases from the verse text ("came to himself", "fatted calf")
- theological terms the passage raises (repentance, *metanoia*, sonship,
  the father's *philanthropia*)

A new depth preset, above `Deep`:

```python
DEPTH_PRESETS["Lesson"] = {"cap": 250, "gate_ratio": 0.30}
```

Justified because this runs once a week on purpose, not once a message. The
looser gate is what `ROADMAP.md` N4 proposed and shelved for cost reasons — cost
is not the binding constraint here.

### Stage 3 — Compose
Four Claude calls over **one shared excerpt block**:

| Call | Produces | Sections |
|---|---|---|
| A | verse-by-verse commentary | 3 |
| B | convergence + divergence | 4, 5 |
| C | illustrations + class questions | 6, 7 |
| D | through-line, cross-refs, teaching notes | 2, 8, 9 |

Separate calls because one call producing ten sections does all of them
shallowly. Four is the point where focus stops improving and cost keeps rising.

**Prompt caching is what makes this affordable.** The excerpt block (~170K
tokens) is byte-identical across all four calls, so it is cached once and read
three times at ~10% of input cost. Cache reads verify via
`usage.cache_read_input_tokens`.

> Corrects a note in `ROADMAP.md`: *"prompt caching barely helps here — the ~65K
> of excerpts is unique per question."* True for chat. **False for lesson
> composition**, where one excerpt set feeds four calls. Caching cuts the
> composition bill roughly in half.

Ordering matters: the excerpt block must be the stable prefix, with the
per-section instruction after the last `cache_control` breakpoint. Anything
volatile (timestamps, a regeneration counter) must not appear before it.

### Stage 4 — Verify
Programmatic, before anything renders:

1. Every quoted span in the output is matched against the retrieved excerpt set.
2. Any quotation not found verbatim (normalizing whitespace) is **flagged in the
   UI**, not silently shipped.
3. Every citation resolves to a real `(source, filename, page_number)` row.
4. Every named father is one the excerpt actually attributes.

Cheap to implement, and it is the difference between a tool a teacher can stand
behind and one they have to double-check.

### Stage 5 — Review and export
The teacher keeps or discards each excerpt, edits any section, then exports.
Discards are recorded — see Data Model.

---

## Data model

New tables in a **separate** `lessons.db`. `commentary.db` stays read-only, so a
rebuilt index never destroys prepared lessons.

```sql
CREATE TABLE lessons (
  id           INTEGER PRIMARY KEY,
  created_at   TEXT NOT NULL,
  book         TEXT, chapter INTEGER,
  verse_start  INTEGER, verse_end INTEGER,
  audience     TEXT NOT NULL,          -- kids | youth | adults
  length       TEXT NOT NULL,
  focus        TEXT,
  index_version TEXT NOT NULL,         -- which commentary.db produced it
  cost_usd     REAL
);

CREATE TABLE lesson_sections (
  lesson_id    INTEGER NOT NULL,
  section      TEXT NOT NULL,          -- through_line | verse_by_verse | ...
  body_md      TEXT NOT NULL,
  edited       INTEGER DEFAULT 0       -- teacher touched it
);

CREATE TABLE lesson_excerpts (
  lesson_id    INTEGER NOT NULL,
  chunk_id     INTEGER NOT NULL,       -- FK into commentary.db chunks
  block        TEXT,                   -- which verse block
  author       TEXT,
  kept         INTEGER,                -- 1 kept, 0 discarded, NULL unreviewed
  flagged      INTEGER DEFAULT 0       -- failed Stage 4 verification
);
```

`lesson_excerpts.kept` is the point. Every prepared lesson yields human judgments
of "this excerpt was worth using for this passage" — which is `ROADMAP.md` N5's
eval set and N7's feedback signal, generated by ordinary use instead of by
labeling sessions.

`index_version` exists so the L3 staleness trap in `ROADMAP.md` doesn't repeat:
when the index is rebuilt, every lesson knows whether it predates the change.

---

## Grounding rules

Non-negotiable, and the reason to trust the output:

1. **Every excerpt is a `chunk_id`.** The model selects and orders; it never
   authors patristic text.
2. **A father is named only where the excerpt attributes him.** Where the source
   is a collection with no author-level metadata (46% of the corpus — see
   `ROADMAP.md` P1), the citation says the collection and volume, and the app
   does not guess.
3. **Model prose is visually distinct** from quoted text in every render and
   every export.
4. **Verification failures are shown, not swallowed.**
5. **Thin coverage is stated.** "Only two sources in your library comment on
   vv. 25-32" is more useful than four padded excerpts.

---

## UI

A new Streamlit page, `pages/2_Prepare_a_Lesson.py`, beside the existing chat.

```
Passage [Luke 15:11-32        ]  Audience [Youth ▾]  Length [45 min ▾]
Focus   [optional                                                    ]
                                                    [ Prepare lesson ]
```

Generation streams section by section — §3 first, since it's the longest wait and
the most useful thing to start reading.

Review controls per excerpt: **keep** / **drop**. Sections are editable in place.
An edited section is marked so a later regeneration doesn't silently overwrite
the teacher's work.

Saved lessons list in the sidebar, most recent first, reopenable and re-exportable.

---

## Export

Non-negotiable, not a later phase. Nobody teaches from a Streamlit page.

| Format | Use | Implementation |
|---|---|---|
| Markdown | Notes apps, phone, editing | Direct |
| PDF — teacher copy | Print, tablet | Markdown → PDF |
| PDF — handout | Class copy: passage, questions, images; no teacher notes | Section subset |

The handout is a section filter, not a second generation.

---

## Cost

Retrieval at `cap=250` ≈ 170K input tokens.

Composition on `claude-opus-5` ($5 / $25 per MTok), four calls sharing one cached
block:

| Item | Tokens | Cost |
|---|---|---|
| Call A — cache write | 170K × 1.25 | $1.06 |
| Calls B–D — cache reads | 3 × 170K × 0.1 | $0.26 |
| Output, all four | ~12K | $0.30 |
| Stage 1 passage resolution | negligible | ~$0.01 |
| **Total per lesson** | | **~$1.62** |

Without caching the same four calls cost ~$3.70 — caching saves ~56%.

On `claude-sonnet-5` ($2 / $10) the same lesson is **~$0.65**. Opus is specified
for composition because the volume is one lesson a week, the quality bar is a
document someone teaches from, and the difference is under a dollar. The chat
path stays on Sonnet 5.

Weekly use ≈ **$84/year**. If a term of lessons is planned in advance, the Batch
API halves it (13 weeks ≈ $10, overnight).

The four composition calls run back-to-back, well inside the default 5-minute
cache TTL. Regenerating a section later in a review session re-pays the write
cost; a 1h TTL would avoid that at a higher write multiplier — measure before
enabling.

---

## What's reused vs. new

| Component | Status |
|---|---|
| `fts_search`, `select_passages`, `expand_anchor`, `format_context` | Reused unchanged |
| `get_db`, `get_sources` | Reused |
| `DEPTH_PRESETS` | One entry added |
| Passage resolution | New, small |
| Passage-based keyword generation | New — distinct from `generate_query_plan()` |
| Four-call cached composer | New — the bulk of the work |
| Verification pass | New, small |
| `lessons.db` + persistence | New |
| Streamlit page, review controls | New |
| Markdown/PDF export | New |

No re-index. No schema change to `commentary.db`. Nothing here is blocked on
`ROADMAP.md` X1–X6 — but §8 gets materially better once verse tagging lands, and
§3's citations get materially better once author metadata lands (P1).

---

## Build phases

**Phase 1 — the spine.** Passage → retrieval → call A only → §3 rendered →
Markdown export. This is the minimum that answers *"is the material any good?"*
If §3 on a familiar passage isn't worth reading, stop and fix retrieval instead.

**Phase 2 — the rest of the document.** Calls B–D, sections 2, 4–9, caching,
verification.

**Phase 3 — make it a tool.** Save/reopen, keep/drop review, PDF, handout.

**Phase 4 — measure.** Prepare four real lessons. Record keep/drop rates per
source and per section. That is the first honest retrieval baseline this project
has had, on real work rather than eval questions.

---

## Success criteria

Deliberately about use, not scores:

- A lesson is prepared for a class **actually taught**, and the teacher uses it.
- **≥60% of §3 excerpts are kept** in review. Below that, retrieval is wasting
  the reader's attention.
- **Zero unflagged fabricated quotations** across the first ten lessons.
- **≥3 distinct named fathers** on a major passage.
- Preparation takes **under 10 minutes** end to end, including review.
- Generated **under $2** per lesson.

---

## Open questions

1. **Which Bible translation?** The DB has none. Needs a public-domain text
   (KJV / WEB / Douay-Rheims) or a licensed one. For a Coptic Orthodox library,
   LXX versification matters — see `ROADMAP.md` verse-spine notes on the Psalm
   numbering offset. Blocks §1.
2. **Verse-block splitting.** Model-chosen, or fixed at 3–5 verses? Model-chosen
   is better and less predictable. Start fixed, revisit.
3. **Does §6 need its own pass?** Illustrations may be reliably extractable
   inside call C, or may need a dedicated classification over a wider candidate
   set. Phase 2 answers it.
4. **Regeneration semantics.** If a teacher edits §4 and regenerates §3, what
   happens? Proposal: edited sections are frozen and never overwritten without
   explicit confirmation.
5. **Lectionary integration.** The Coptic lectionary would let the app propose
   next Sunday's passage unprompted, and connects to `morning_brief.py`. Out of
   scope here; noted so it isn't rediscovered.
