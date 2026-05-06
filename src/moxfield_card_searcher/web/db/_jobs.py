"""CRUD for the `fetch_jobs` table. Each row tracks one in-flight fetch
or refresh; finished jobs stay in the table until manually cleared."""

from __future__ import annotations

import sqlite3

from moxfield_card_searcher.web.db._rows import JobRow


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
    return _row_to_jobrow(row)


def list_jobs(conn: sqlite3.Connection) -> list[JobRow]:
    rows = conn.execute(
        "SELECT id, moxfield_id, status, progress_pct, pages_done, pages_total, "
        "error_message, refresh_of_binder_id, created_at, updated_at "
        "FROM fetch_jobs WHERE status IN ('pending', 'fetching') "
        "ORDER BY created_at"
    ).fetchall()
    return [_row_to_jobrow(r) for r in rows]


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


def fail_job(
    conn: sqlite3.Connection, job_id: int, *, error: str, updated_at: str
) -> None:
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


def _row_to_jobrow(r: sqlite3.Row) -> JobRow:
    return JobRow(
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
