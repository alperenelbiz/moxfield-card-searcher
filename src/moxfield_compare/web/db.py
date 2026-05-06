import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS binders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    moxfield_id     TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    entry_count     INTEGER NOT NULL,
    total_cards     INTEGER NOT NULL
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
    """Create tables/indexes if missing. Safe to call repeatedly."""
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection]:
    """Open a connection with WAL journal mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        conn.close()


@dataclass(frozen=True)
class BinderRow:
    id: int
    moxfield_id: str
    name: str
    fetched_at: str
    entry_count: int
    total_cards: int


@dataclass(frozen=True)
class CardRow:
    name: str
    name_lower: str
    edition: str
    collector_number: str
    count: int
    foil: str
    scryfall_id: str | None


def create_binder(
    conn: sqlite3.Connection,
    *,
    moxfield_id: str,
    name: str,
    fetched_at: str,
    entry_count: int,
    total_cards: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO binders(moxfield_id, name, fetched_at, entry_count, total_cards) "
        "VALUES (?, ?, ?, ?, ?)",
        (moxfield_id, name, fetched_at, entry_count, total_cards),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def list_binders(conn: sqlite3.Connection) -> list[BinderRow]:
    cur = conn.execute(
        "SELECT id, moxfield_id, name, fetched_at, entry_count, total_cards "
        "FROM binders ORDER BY fetched_at DESC"
    )
    return [
        BinderRow(
            id=r["id"],
            moxfield_id=r["moxfield_id"],
            name=r["name"],
            fetched_at=r["fetched_at"],
            entry_count=r["entry_count"],
            total_cards=r["total_cards"],
        )
        for r in cur.fetchall()
    ]


def delete_binder(conn: sqlite3.Connection, binder_id: int) -> bool:
    cur = conn.execute("DELETE FROM binders WHERE id=?", (binder_id,))
    conn.commit()
    return cur.rowcount > 0


def insert_cards(conn: sqlite3.Connection, binder_id: int, cards: list[CardRow]) -> None:
    conn.executemany(
        "INSERT INTO cards(binder_id, name, name_lower, edition, "
        "collector_number, count, foil, scryfall_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                binder_id,
                c.name,
                c.name_lower,
                c.edition,
                c.collector_number,
                c.count,
                c.foil,
                c.scryfall_id,
            )
            for c in cards
        ],
    )
    conn.commit()


def list_cards(conn: sqlite3.Connection, binder_id: int) -> list[CardRow]:
    cur = conn.execute(
        "SELECT name, name_lower, edition, collector_number, count, foil, scryfall_id "
        "FROM cards WHERE binder_id=? ORDER BY id",
        (binder_id,),
    )
    return [
        CardRow(
            name=r["name"],
            name_lower=r["name_lower"],
            edition=r["edition"],
            collector_number=r["collector_number"],
            count=r["count"],
            foil=r["foil"],
            scryfall_id=r["scryfall_id"],
        )
        for r in cur.fetchall()
    ]


@dataclass(frozen=True)
class JobRow:
    id: int
    moxfield_id: str
    status: str
    progress_pct: int
    pages_done: int
    pages_total: int
    error_message: str | None
    refresh_of_binder_id: int | None
    created_at: str
    updated_at: str


def create_job(
    conn: sqlite3.Connection,
    *,
    moxfield_id: str,
    refresh_of_binder_id: int | None,
    created_at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO fetch_jobs(moxfield_id, status, progress_pct, pages_done, "
        "pages_total, error_message, refresh_of_binder_id, created_at, updated_at) "
        "VALUES (?, 'pending', 0, 0, 0, NULL, ?, ?, ?)",
        (moxfield_id, refresh_of_binder_id, created_at, created_at),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def get_job(conn: sqlite3.Connection, job_id: int) -> JobRow | None:
    row = conn.execute(
        "SELECT id, moxfield_id, status, progress_pct, pages_done, pages_total, "
        "error_message, refresh_of_binder_id, created_at, updated_at "
        "FROM fetch_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return JobRow(
        id=row["id"],
        moxfield_id=row["moxfield_id"],
        status=row["status"],
        progress_pct=row["progress_pct"],
        pages_done=row["pages_done"],
        pages_total=row["pages_total"],
        error_message=row["error_message"],
        refresh_of_binder_id=row["refresh_of_binder_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_jobs(conn: sqlite3.Connection) -> list[JobRow]:
    rows = conn.execute(
        "SELECT id, moxfield_id, status, progress_pct, pages_done, pages_total, "
        "error_message, refresh_of_binder_id, created_at, updated_at "
        "FROM fetch_jobs WHERE status IN ('pending', 'fetching') "
        "ORDER BY created_at"
    ).fetchall()
    return [
        JobRow(
            id=r["id"],
            moxfield_id=r["moxfield_id"],
            status=r["status"],
            progress_pct=r["progress_pct"],
            pages_done=r["pages_done"],
            pages_total=r["pages_total"],
            error_message=r["error_message"],
            refresh_of_binder_id=r["refresh_of_binder_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def update_job_progress(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    status: str,
    pages_done: int,
    pages_total: int,
    updated_at: str,
) -> None:
    pct = int(pages_done / pages_total * 100) if pages_total > 0 else 0
    conn.execute(
        "UPDATE fetch_jobs SET status=?, pages_done=?, pages_total=?, "
        "progress_pct=?, updated_at=? WHERE id=?",
        (status, pages_done, pages_total, pct, updated_at, job_id),
    )
    conn.commit()


def finish_job(conn: sqlite3.Connection, job_id: int, *, updated_at: str) -> None:
    conn.execute(
        "UPDATE fetch_jobs SET status='done', progress_pct=100, updated_at=? WHERE id=?",
        (updated_at, job_id),
    )
    conn.commit()


def fail_job(conn: sqlite3.Connection, job_id: int, *, error: str, updated_at: str) -> None:
    conn.execute(
        "UPDATE fetch_jobs SET status='failed', error_message=?, updated_at=? WHERE id=?",
        (error, updated_at, job_id),
    )
    conn.commit()


def cancel_job(conn: sqlite3.Connection, job_id: int, *, updated_at: str) -> None:
    conn.execute(
        "UPDATE fetch_jobs SET status='cancelled', updated_at=? WHERE id=?",
        (updated_at, job_id),
    )
    conn.commit()


def has_active_job(conn: sqlite3.Connection, moxfield_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM fetch_jobs WHERE moxfield_id=? "
        "AND status IN ('pending', 'fetching') LIMIT 1",
        (moxfield_id,),
    ).fetchone()
    return row is not None
