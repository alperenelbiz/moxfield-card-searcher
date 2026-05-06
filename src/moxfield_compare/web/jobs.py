from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moxfield_compare.binder_fetcher import PageResult, entry_to_card_row, fetch_pages
from moxfield_compare.web import db

PagesIter = Callable[[Any, str], Iterator[PageResult]]


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


async def run_fetch_job(
    *,
    db_path: Path,
    job_id: int,
    binder_id: str,
    scraper: Any,
    pages_iter: PagesIter = fetch_pages,
) -> None:
    """Execute a fetch job to completion.

    On success, atomically inserts the binder and its cards in a single
    transaction and marks the job as done. On failure (including cancellation
    detected mid-stream), the job is marked accordingly and no binder rows
    are committed for a fresh fetch. Refresh handling is in run_refresh_job.
    """
    rows: list[db.CardRow] = []
    binder_name = ""
    total_cards = 0
    try:
        for page in pages_iter(scraper, binder_id):
            with db.connect(db_path) as conn:
                # Cooperative cancellation check.
                job = db.get_job(conn, job_id)
                if job is not None and job.status == "cancelled":
                    return
                db.update_job_progress(
                    conn,
                    job_id,
                    status="fetching",
                    pages_done=page.page_number,
                    pages_total=page.total_pages,
                    updated_at=_now(),
                )
            binder_name = page.binder_name or binder_name
            for entry in page.entries:
                row = entry_to_card_row(entry)
                rows.append(row)
                total_cards += row.count
    except Exception as exc:  # network, JSON, anything
        with db.connect(db_path) as exc_conn:
            db.fail_job(exc_conn, job_id, error=str(exc), updated_at=_now())
        return

    # Final cancellation check before commit.
    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        if job is not None and job.status == "cancelled":
            return

        binder_row_id = db.create_binder(
            conn,
            moxfield_id=binder_id,
            name=binder_name or binder_id,
            fetched_at=_now(),
            entry_count=len(rows),
            total_cards=total_cards,
        )
        db.insert_cards(conn, binder_row_id, rows)
        db.finish_job(conn, job_id, updated_at=_now())


async def run_refresh_job(
    *,
    db_path: Path,
    job_id: int,
    binder_id: str,
    existing_binder_id: int,
    scraper: Any,
    pages_iter: PagesIter = fetch_pages,
) -> None:
    """Execute a refresh job. The old binder row and its cards remain intact
    until the new fetch completes successfully; then a single transaction
    deletes the old cards, inserts the new ones, and updates the binder
    metadata.
    """
    rows: list[db.CardRow] = []
    binder_name = ""
    total_cards = 0
    try:
        for page in pages_iter(scraper, binder_id):
            with db.connect(db_path) as conn:
                job = db.get_job(conn, job_id)
                if job is not None and job.status == "cancelled":
                    return
                db.update_job_progress(
                    conn,
                    job_id,
                    status="fetching",
                    pages_done=page.page_number,
                    pages_total=page.total_pages,
                    updated_at=_now(),
                )
            binder_name = page.binder_name or binder_name
            for entry in page.entries:
                row = entry_to_card_row(entry)
                rows.append(row)
                total_cards += row.count
    except Exception as exc:
        with db.connect(db_path) as exc_conn:
            db.fail_job(exc_conn, job_id, error=str(exc), updated_at=_now())
        return

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        if job is not None and job.status == "cancelled":
            return

        # Atomic swap: delete old cards, update metadata, insert new cards.
        # We use a single connection and rely on SQLite transaction semantics.
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM cards WHERE binder_id=?", (existing_binder_id,))
            conn.execute(
                "UPDATE binders SET name=?, fetched_at=?, entry_count=?, total_cards=? WHERE id=?",
                (binder_name or binder_id, _now(), len(rows), total_cards, existing_binder_id),
            )
            if rows:
                conn.executemany(
                    "INSERT INTO cards(binder_id, name, name_lower, edition, "
                    "collector_number, count, foil, scryfall_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            existing_binder_id,
                            c.name,
                            c.name_lower,
                            c.edition,
                            c.collector_number,
                            c.count,
                            c.foil,
                            c.scryfall_id,
                        )
                        for c in rows
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        db.finish_job(conn, job_id, updated_at=_now())
