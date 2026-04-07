"""Database initialization and helper functions."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date

DATABASE_PATH = os.getenv("DATABASE_PATH", "psalm_app.db")


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH", DATABASE_PATH)


@contextmanager
def get_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        schema = f.read()
    with get_db() as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def get_user_by_email(email: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_user_by_id(user_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(email: str, name: str, role: str = "student") -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, name, role) VALUES (?, ?, ?)",
            (email, name, role),
        )
        user_id = cur.lastrowid
        # Initialize scores row
        conn.execute("INSERT INTO scores (user_id) VALUES (?)", (user_id,))
        return user_id


def update_last_login(user_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user_id),
        )


def get_all_students():
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE role = 'student' ORDER BY name"
        ).fetchall()


def delete_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Magic link helpers
# ---------------------------------------------------------------------------

def create_magic_link(user_id: int, token: str, expires_at: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO magic_links (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at),
        )


def get_magic_link(token: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM magic_links WHERE token = ?", (token,)
        ).fetchone()


def consume_magic_link(token: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE magic_links SET used = 1 WHERE token = ?", (token,)
        )


# ---------------------------------------------------------------------------
# Login code helpers
# ---------------------------------------------------------------------------

def create_login_code(user_id: int, code: str, expires_at: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO login_codes (user_id, code, expires_at) VALUES (?, ?, ?)",
            (user_id, code, expires_at),
        )


def get_login_code(code: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM login_codes WHERE code = ?", (code,)
        ).fetchone()


def consume_login_code(code: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE login_codes SET used = 1 WHERE code = ?", (code,)
        )


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def get_or_create_psalm_progress(user_id: int, psalm_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM psalm_progress WHERE user_id = ? AND psalm_id = ?",
            (user_id, psalm_id),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO psalm_progress (user_id, psalm_id) VALUES (?, ?)",
                (user_id, psalm_id),
            )
            row = conn.execute(
                "SELECT * FROM psalm_progress WHERE user_id = ? AND psalm_id = ?",
                (user_id, psalm_id),
            ).fetchone()
        return row


def get_chunk_progress(user_id: int, psalm_id: int, chunk_number: int, mode: str):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM chunk_progress
               WHERE user_id=? AND psalm_id=? AND chunk_number=? AND mode=?""",
            (user_id, psalm_id, chunk_number, mode),
        ).fetchone()


def get_or_create_chunk_progress(user_id: int, psalm_id: int, chunk_number: int, mode: str):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM chunk_progress
               WHERE user_id=? AND psalm_id=? AND chunk_number=? AND mode=?""",
            (user_id, psalm_id, chunk_number, mode),
        ).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO chunk_progress (user_id, psalm_id, chunk_number, mode)
                   VALUES (?, ?, ?, ?)""",
                (user_id, psalm_id, chunk_number, mode),
            )
            row = conn.execute(
                """SELECT * FROM chunk_progress
                   WHERE user_id=? AND psalm_id=? AND chunk_number=? AND mode=?""",
                (user_id, psalm_id, chunk_number, mode),
            ).fetchone()
        return row


def increment_chunk_success(user_id: int, psalm_id: int, chunk_number: int, mode: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE chunk_progress SET success_count = success_count + 1
               WHERE user_id=? AND psalm_id=? AND chunk_number=? AND mode=?""",
            (user_id, psalm_id, chunk_number, mode),
        )


def mark_chunk_completed(user_id: int, psalm_id: int, chunk_number: int, mode: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE chunk_progress SET completed = 1
               WHERE user_id=? AND psalm_id=? AND chunk_number=? AND mode=?""",
            (user_id, psalm_id, chunk_number, mode),
        )


def all_chunks_mastered(user_id: int, psalm_id: int, total_chunks: int) -> bool:
    """Return True if all sub-chunks of a psalm are fully recitation-mastered."""
    if total_chunks == 0:
        # Single-verse psalms use chunk_number=1
        row = get_chunk_progress(user_id, psalm_id, 1, "recitation")
        return row is not None and row["completed"]
    with get_db() as conn:
        rows = conn.execute(
            """SELECT COUNT(*) as cnt FROM chunk_progress
               WHERE user_id=? AND psalm_id=? AND mode='recitation' AND completed=1
               AND chunk_number > 0""",
            (user_id, psalm_id),
        ).fetchone()
        return rows["cnt"] >= total_chunks


def get_psalm_progress_all(user_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM psalm_progress WHERE user_id = ? ORDER BY psalm_id",
            (user_id,),
        ).fetchall()


def update_psalm_mastery_count(user_id: int, psalm_id: int):
    with get_db() as conn:
        conn.execute(
            """UPDATE psalm_progress SET mastery_count = mastery_count + 1
               WHERE user_id=? AND psalm_id=?""",
            (user_id, psalm_id),
        )
        row = conn.execute(
            "SELECT mastery_count FROM psalm_progress WHERE user_id=? AND psalm_id=?",
            (user_id, psalm_id),
        ).fetchone()
        if row and row["mastery_count"] >= 3:
            conn.execute(
                "UPDATE psalm_progress SET mastered = 1 WHERE user_id=? AND psalm_id=?",
                (user_id, psalm_id),
            )


def add_points_to_psalm(user_id: int, psalm_id: int, points: int):
    with get_db() as conn:
        conn.execute(
            """UPDATE psalm_progress SET points_earned = points_earned + ?
               WHERE user_id=? AND psalm_id=?""",
            (points, user_id, psalm_id),
        )


# ---------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------

def record_attempt(user_id: int, psalm_id: int, chunk_number: int, mode: str,
                   typed_text: str, score: float, passed: bool, points: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO attempts
               (user_id, psalm_id, chunk_number, mode, typed_text, score, passed, points_awarded)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, psalm_id, chunk_number, mode, typed_text, score, passed, points),
        )
        return cur.lastrowid


def get_recent_attempts(user_id: int, psalm_id: int, chunk_number: int, limit: int = 5):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM attempts
               WHERE user_id=? AND psalm_id=? AND chunk_number=?
               ORDER BY attempted_at DESC LIMIT ?""",
            (user_id, psalm_id, chunk_number, limit),
        ).fetchall()


def get_all_attempts_for_student(user_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM attempts WHERE user_id=? ORDER BY attempted_at DESC",
            (user_id,),
        ).fetchall()


# ---------------------------------------------------------------------------
# Scores / leaderboard
# ---------------------------------------------------------------------------

def add_total_points(user_id: int, points: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE scores SET total_points = total_points + ? WHERE user_id = ?",
            (points, user_id),
        )


def update_streak(user_id: int):
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT last_activity_date, current_streak FROM scores WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            return
        last = row["last_activity_date"]
        streak = row["current_streak"] or 0
        if last == today:
            return  # already counted today
        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last == yesterday:
            streak += 1
        else:
            streak = 1
        conn.execute(
            "UPDATE scores SET current_streak=?, last_activity_date=? WHERE user_id=?",
            (streak, today, user_id),
        )


def get_score(user_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM scores WHERE user_id=?", (user_id,)
        ).fetchone()


def get_leaderboard():
    with get_db() as conn:
        return conn.execute(
            """SELECT u.id, u.name, s.total_points, s.current_streak
               FROM scores s JOIN users u ON u.id = s.user_id
               WHERE u.role = 'student'
               ORDER BY s.total_points DESC, u.name ASC""",
        ).fetchall()


def is_first_to_master(user_id: int, psalm_id: int) -> bool:
    """Check if this student is the first to master this psalm."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM psalm_progress
               WHERE psalm_id=? AND mastered=1 AND user_id != ?""",
            (psalm_id, user_id),
        ).fetchone()
        return row["cnt"] == 0


def get_average_accuracy(user_id: int, psalm_id: int) -> float:
    """Average accuracy across all attempts for a psalm."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT AVG(score) as avg FROM attempts WHERE user_id=? AND psalm_id=?",
            (user_id, psalm_id),
        ).fetchone()
        return row["avg"] or 0.0


# ---------------------------------------------------------------------------
# Teacher settings
# ---------------------------------------------------------------------------

def get_verse_of_the_day() -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT verse_of_the_day FROM teacher_settings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["verse_of_the_day"] if row else None


def set_verse_of_the_day(verse: str, teacher_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO teacher_settings (verse_of_the_day, set_by) VALUES (?, ?)",
            (verse, teacher_id),
        )


# ---------------------------------------------------------------------------
# Teacher class overview
# ---------------------------------------------------------------------------

def get_class_overview():
    """Return every student with their latest psalm/chunk/mode."""
    with get_db() as conn:
        students = conn.execute(
            "SELECT id, name, email FROM users WHERE role='student' ORDER BY name"
        ).fetchall()
        result = []
        for s in students:
            # Find the most advanced incomplete chunk_progress entry
            cp = conn.execute(
                """SELECT psalm_id, chunk_number, mode, success_count
                   FROM chunk_progress
                   WHERE user_id=? AND completed=0
                   ORDER BY psalm_id ASC, chunk_number ASC
                   LIMIT 1""",
                (s["id"],),
            ).fetchone()
            score = conn.execute(
                "SELECT total_points, current_streak FROM scores WHERE user_id=?",
                (s["id"],),
            ).fetchone()
            result.append({
                "id": s["id"],
                "name": s["name"],
                "email": s["email"],
                "current_psalm_id": cp["psalm_id"] if cp else None,
                "current_chunk": cp["chunk_number"] if cp else None,
                "current_mode": cp["mode"] if cp else None,
                "total_points": score["total_points"] if score else 0,
                "streak": score["current_streak"] if score else 0,
            })
        return result
