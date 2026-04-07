-- Psalm Memorization App Database Schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
    class_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME
);

CREATE TABLE IF NOT EXISTS magic_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at DATETIME NOT NULL,
    used BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT UNIQUE NOT NULL,
    expires_at DATETIME NOT NULL,
    used BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS psalm_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    psalm_id INTEGER NOT NULL,
    mastery_count INTEGER NOT NULL DEFAULT 0,
    mastered BOOLEAN NOT NULL DEFAULT 0,
    points_earned INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, psalm_id)
);

CREATE TABLE IF NOT EXISTS chunk_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    psalm_id INTEGER NOT NULL,
    chunk_number INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('study', 'blank', 'letters', 'recitation')),
    success_count INTEGER NOT NULL DEFAULT 0,
    completed BOOLEAN NOT NULL DEFAULT 0,
    unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, psalm_id, chunk_number, mode)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    psalm_id INTEGER NOT NULL,
    chunk_number INTEGER NOT NULL,
    mode TEXT NOT NULL,
    typed_text TEXT NOT NULL,
    score REAL NOT NULL,
    passed BOOLEAN NOT NULL,
    points_awarded INTEGER NOT NULL DEFAULT 0,
    attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_points INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    last_activity_date DATE
);

CREATE TABLE IF NOT EXISTS teacher_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_of_the_day TEXT,
    set_by INTEGER REFERENCES users(id),
    set_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
