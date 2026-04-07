# Psalm Memorization Agent
## Project Specification

---

## Overview

A web application to help 7th grade Sunday School students memorize Psalms. Features multi-user login, structured drill modes, progress tracking, a class leaderboard, and a teacher dashboard.

---

## Tech Stack

- **Backend:** Flask
- **Database:** SQLite
- **Frontend:** HTML/CSS (Bootstrap)
- **Email:** SMTP (magic link authentication)
- **AI:** Claude API (claude-opus-4-6) for feedback and encouragement

---

## Users & Authentication

- **Login method:** Magic link — user enters email, receives a link, clicks it to log in
- **Fallback login:** Teacher-generated one-time codes — if SMTP is unavailable, the teacher can generate a login code from the admin page and share it verbally or on-screen
- **Roles:** Student, Teacher
- **User setup:** Manual — teacher adds/removes students via an admin page inside the app
- **One class** of 7th graders to start

---

## Curated Psalm List (NKJV, in canonical order)

| # | Psalm | Notes |
|---|-------|-------|
| 1 | Psalm 1 | 6 verses |
| 2 | Psalm 23 | 6 verses |
| 3 | Psalm 27:1 | Single verse |
| 4 | Psalm 46 | 11 verses |
| 5 | Psalm 91 | 16 verses — the boss level |
| 6 | Psalm 100 | 5 verses |
| 7 | Psalm 119:105 | Single verse |
| 8 | Psalm 121 | 8 verses |

Students work through them in this order, unlocking the next Psalm only after mastering the current one.

---

## Chunk Definitions (NKJV)

Psalms are broken into manageable chunks. Students master each chunk before combining them for the final full recitation.

### Psalm 1 (6 verses)
- Chunk 1: v1-2
- Chunk 2: v3-4
- Chunk 3: v5-6
- Final: all 6 verses

### Psalm 23 (6 verses)
- Chunk 1: v1-3
- Chunk 2: v4-6
- Final: all 6 verses

### Psalm 27:1 (single verse)
- No chunks — drill modes applied directly to the verse
- Final: the verse

### Psalm 46 (11 verses)
- Chunk 1: v1-3
- Chunk 2: v4-7
- Chunk 3: v8-11
- Final: all 11 verses

### Psalm 91 (16 verses)
- Chunk 1: v1-4
- Chunk 2: v5-9
- Chunk 3: v10-13
- Chunk 4: v14-16
- Final: all 16 verses

### Psalm 100 (5 verses)
- Chunk 1: v1-3
- Chunk 2: v4-5
- Final: all 5 verses

### Psalm 119:105 (single verse)
- No chunks — same as Psalm 27:1

### Psalm 121 (8 verses)
- Chunk 1: v1-4
- Chunk 2: v5-8
- Final: all 8 verses

---

## Learning Flow

### Per-Chunk Progression (must complete in order)

1. **Study Mode** — Student reads the chunk at their own pace, hits "I'm Ready" to continue. No scoring.
2. **Fill in the Blank** — Key words removed, student fills them in. Must score 80% to unlock next mode.
3. **First Letter Hints** — Only first letters of each word shown. Must score 80% to unlock next mode.
4. **Full Recitation** — Student types the chunk entirely from memory. Must complete correctly 3 times to master the chunk.

### After All Chunks Are Mastered
- Student attempts the **full Psalm recitation** (all chunks combined)
- Complete it correctly 3 times → Psalm is **Mastered** ✅
- Psalm mastery unlocks the next Psalm in the list

### Session Continuity
- Students always pick up exactly where they left off
- Progress is saved after every attempt

---

## Typing Evaluation Rules

- **Ignore punctuation** (commas, periods, semicolons, colons)
- **Ignore capitalization**
- **Allow minor typos** — small character-level errors (1-2 chars) per word are forgiven
- Words themselves must be recognizably correct (no skipping words)

---

## Mastery Definition

A chunk or full Psalm is **mastered** when the student types it correctly (per above rules) **3 times** — these can be cumulative across sessions.

---

## Scoring & Gamification

### Points Formula

**Base points** per successful attempt = word count of the chunk (or full Psalm).
Study mode and failed attempts award 0 points.

| Factor | Value |
|--------|-------|
| **Fill in the Blank** | base × 1.0 |
| **First Letter Hints** | base × 1.5 |
| **Full Recitation** | base × 2.0 |
| **Chunk mastery** (3rd recitation pass) | +50 bonus |
| **Full Psalm mastery** (3rd full pass) | base × 2 bonus (mastery bonus) |
| **Streak** (consecutive days practicing) | +10 per day in streak, capped at +70 |
| **First in class** to master a Psalm | +100 bonus (requires ≥90% average accuracy across all attempts for that Psalm) |

### Leaderboard
- Visible to all students
- Shows total points and current streak
- Refreshes on page load (no WebSockets needed — current data shown whenever a student visits the leaderboard)
- Teachers see a more detailed breakdown

---

## Claude API Integration

### Purpose
Provide personalized, age-appropriate feedback to help students stay motivated and improve.

### Persona
Warm, encouraging, and faith-aware — like a supportive Sunday School teacher. Age-appropriate for 7th graders. References the meaning and beauty of the Psalm they're working on when relevant.

### When It Fires
| Trigger | Source | What Happens |
|---------|--------|-------------|
| **Failed attempt** | **Claude API** | Analyzes the student's typed text vs. the correct text. Gives specific, actionable tips (e.g., "You're mixing up verses 3 and 4 — try focusing on the transition between them"). Encouraging tone. |
| **Successful attempt** | **Built-in** (no API call) | Short encouragement message from a pre-written pool (e.g., "Great job — you nailed it this time!"). Randomized to stay fresh. |
| **Chunk mastery** | **Built-in** (no API call) | Celebrates the milestone (e.g., "You've memorized the first half of Psalm 23!"). Pre-written per Psalm for a personal touch. |
| **Full Psalm mastery** | **Built-in** (no API call) | Bigger celebration with a reflection on the Psalm's meaning. Pre-written per Psalm. |

### Input Context (sent to Claude API)
- The correct Psalm text for the chunk
- The student's typed text (from the current attempt)
- Last 3-5 attempts for this chunk (from the Attempts table) to identify patterns
- Current mode (blank / letters / recitation)
- Whether the attempt passed or failed

### Output
- A single short message (1-3 sentences) displayed below the drill area
- No streaming — request/response is fine for this use case

### Cost Controls
- Use `claude-haiku-4-5-20251001` for feedback (fast, cheap, sufficient for short encouragement)
- Cache the system prompt per session to reduce token usage
- Rate limit: max 1 Claude API call per attempt (no retries on failure — show a generic fallback message instead)

---

## Database Structure

### Users
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| email | TEXT UNIQUE | |
| name | TEXT | |
| role | TEXT | 'student' or 'teacher' |
| class_id | INTEGER | nullable — for future multi-class support |
| created_at | DATETIME | |
| last_login | DATETIME | |

### Magic Links
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| token | TEXT UNIQUE | |
| expires_at | DATETIME | |
| used | BOOLEAN | |

### Psalm Progress
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| psalm_id | INTEGER | 1-8 per curated list |
| mastery_count | INTEGER | 0-3 full Psalm recitations |
| mastered | BOOLEAN | |
| points_earned | INTEGER | |

Current chunk/mode are derived from the Chunk Progress table (the furthest incomplete entry).

### Login Codes
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| code | TEXT UNIQUE | 6-digit alphanumeric |
| expires_at | DATETIME | short-lived (15 min) |
| used | BOOLEAN | |

Teacher generates these from the admin page when SMTP is unavailable.

### Chunk Progress
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| psalm_id | INTEGER | 1-8 per curated list |
| chunk_number | INTEGER | which chunk (or 0 for full Psalm) |
| mode | TEXT | study / blank / letters / recitation |
| success_count | INTEGER | 0-3, tracks mastery progress |
| completed | BOOLEAN | true when chunk+mode is mastered |
| unlocked_at | DATETIME | when student reached this stage |

### Attempts
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| psalm_id | INTEGER | 1-8 per curated list |
| chunk_number | INTEGER | which chunk (or 0 for full Psalm) |
| mode | TEXT | blank / letters / recitation |
| typed_text | TEXT | the student's raw input |
| score | REAL | 0.0-1.0 accuracy |
| passed | BOOLEAN | met the threshold for this mode? |
| points_awarded | INTEGER | points earned for this attempt |
| attempted_at | DATETIME | |

Powers the Teacher "Student Detail" screen and provides context for Claude API feedback.

### Scores
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| total_points | INTEGER | |
| current_streak | INTEGER | days |
| last_activity_date | DATE | |

### Teacher Settings
| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| verse_of_the_day | TEXT | |
| set_by | INTEGER FK | user_id |
| set_at | DATETIME | |

---

## Screens

### Student Screens
1. **Login** — Enter email → receive magic link
2. **Dashboard** — Current Psalm/chunk progress, streak, points, verse of the day
3. **Drill Screen** — The active study/practice mode for current chunk
4. **Leaderboard** — All students' total points and streaks
5. **My Progress** — All 8 Psalms shown with status: Locked / In Progress / Mastered

### Teacher Screens
1. **Login** — Same magic link flow
2. **Class Dashboard** — Every student's progress at a glance (Psalm, chunk, mode, mastery)
3. **Student Detail** — Drill down on one student's full history
4. **Admin Page** — Add/remove students, set verse of the day, generate login codes (SMTP fallback)

---

## Verse of the Day
- Teacher sets it from the admin page
- Displayed on every student's dashboard when they log in
- Adds a communal, class-wide touchpoint

---

## Open Items / Future Considerations
- Email service credentials (SMTP host, port, user, password) needed in `.env`
- Bible text (NKJV) needs to be hardcoded or loaded from a local file — no API dependency
- May expand to multiple classes in the future (class_id column added to Users table, nullable for now)
- Mobile-friendly UI important — kids will likely use phones
