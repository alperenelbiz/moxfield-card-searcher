"""SQLite connection factory and schema bootstrap."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS binders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    moxfield_id         TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    entry_count         INTEGER NOT NULL,
    total_cards         INTEGER NOT NULL,
    created_by_username TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    binder_id        INTEGER NOT NULL REFERENCES binders(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    name_lower       TEXT NOT NULL,
    edition          TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    count            INTEGER NOT NULL,
    foil             TEXT NOT NULL,
    scryfall_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_cards_binder ON cards(binder_id);
CREATE INDEX IF NOT EXISTS idx_cards_name_lower ON cards(name_lower);

CREATE TABLE IF NOT EXISTS fetch_jobs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    moxfield_id           TEXT NOT NULL,
    status                TEXT NOT NULL,
    progress_pct          INTEGER NOT NULL DEFAULT 0,
    pages_done            INTEGER NOT NULL DEFAULT 0,
    pages_total           INTEGER NOT NULL DEFAULT 0,
    error_message         TEXT,
    refresh_of_binder_id  INTEGER REFERENCES binders(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
"""


def init_schema(db_path: Path) -> None:
    """Create tables/indexes if missing. Safe to call repeatedly.

    Also runs idempotent column-add migrations for legacy DBs created before
    a column existed in the canonical schema. SQLite's ALTER TABLE raises if
    the column already exists, so we swallow that specific failure and let
    real errors bubble up."""
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        _add_column_if_missing(conn, "binders", "created_by_username", "TEXT")
        conn.commit()


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, type_: str
) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_}")


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection]:
    """Open a connection with WAL journal mode and foreign keys enabled.

    The whole ``with`` block is one transaction: a clean exit commits, an
    exception rolls back. Call sites stay free of repetitive ``conn.commit()``
    boilerplate, and multi-statement work (e.g. the refresh swap) inherits
    atomicity from the context manager."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
