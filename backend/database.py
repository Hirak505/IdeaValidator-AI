"""
Async SQLite database layer for IdeaValidator-AI.

Provides user and saved-evaluation persistence with WAL mode
for concurrent read/write access during async evaluation jobs.
"""

import aiosqlite
import logging
import os
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

# Database file location — stored in backend/data/ (gitignored)
_DB_DIR = Path(__file__).parent / "data"
_DB_PATH = os.getenv("DATABASE_PATH", str(_DB_DIR / "ideavalidator.db"))

# Schema version for future migrations
_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

CREATE TABLE IF NOT EXISTS saved_evaluations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Untitled Evaluation',
    attack_mode INTEGER NOT NULL DEFAULT 0,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_saved_evaluations_user_id ON saved_evaluations(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_evaluations_created_at ON saved_evaluations(created_at);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


async def get_db() -> aiosqlite.Connection:
    """
    Open a new async SQLite connection with WAL mode and foreign keys enabled.
    Callers are responsible for closing the connection.
    """
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(_DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    return db


async def init_db() -> None:
    """
    Initialize the database schema.
    Safe to call multiple times (uses CREATE IF NOT EXISTS).
    """
    db = await get_db()
    try:
        await db.executescript(_SCHEMA_SQL)

        # Set schema version if not already set
        cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cursor.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (_SCHEMA_VERSION,),
            )
        await db.commit()
        logger.info("Database initialized at %s (schema v%d)", _DB_PATH, _SCHEMA_VERSION)
    finally:
        await db.close()


async def close_db(db: aiosqlite.Connection) -> None:
    """Safely close a database connection."""
    if db:
        try:
            await db.close()
        except Exception:
            pass
