from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moxfield_card_searcher.binder_fetcher import PageResult, entry_to_card_row, fetch_pages
from moxfield_card_searcher.web import db
from moxfield_card_searcher.web._util import iso_now as _now

PagesIter = Callable[[Any, str], Iterator[PageResult]]

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DrainedPages:
    """Successful drain result. Cancellation and failure are signalled by
    returning ``None`` from ``_drain_pages`` instead — the helper has already
    written the appropriate job-status row in those cases."""

    rows: list[db.CardRow]
    binder_name: str
    created_by_username: str | None
    total_cards: int


def _drain_pages(
    db_path: Path,
    job_id: int,
    binder_id: str,
    scraper: Any,
    pages_iter: PagesIter,
    *,
    label: str,
) -> _DrainedPages | None:
    """Iterate pages, accumulate CardRows, update progress.

    Returns ``None`` (and writes ``cancelled`` / ``failed`` to the job row) if
    the worker should bail; returns a ``_DrainedPages`` for the caller to
    commit on success. ``label`` is just for log messages so fetch and
    refresh paths stay distinguishable in the journal."""
    rows: list[db.CardRow] = []
    binder_name = ""
    created_by_username: str | None = None
    total_cards = 0
    try:
        for page in pages_iter(scraper, binder_id):
            with db.connect(db_path) as conn:
                job = db.get_job(conn, job_id)
                if job is not None and job.status == "cancelled":
                    _log.info("%s job %s cancelled mid-stream", label, job_id)
                    return None
                db.update_job_progress(
                    conn,
                    job_id,
                    status="fetching",
                    pages_done=page.page_number,
                    pages_total=page.total_pages,
                    updated_at=_now(),
                )
            binder_name = page.binder_name or binder_name
            created_by_username = page.created_by_username or created_by_username
            for entry in page.entries:
                row = entry_to_card_row(entry)
                rows.append(row)
                total_cards += row.count
    except Exception as exc:
        _log.exception("%s job %s failed: %s", label, job_id, exc)
        with db.connect(db_path) as exc_conn:
            db.fail_job(exc_conn, job_id, error=str(exc), updated_at=_now())
        return None

    return _DrainedPages(
        rows=rows,
        binder_name=binder_name,
        created_by_username=created_by_username,
        total_cards=total_cards,
    )


async def run_fetch_job(
    *,
    db_path: Path,
    job_id: int,
    binder_id: str,
    scraper: Any,
    pages_iter: PagesIter = fetch_pages,
) -> None:
    """Execute a fetch job to completion.

    The synchronous body runs on a worker thread via ``asyncio.to_thread`` so
    the FastAPI event loop stays responsive — multiple fetches truly run in
    parallel and HTMX progress polls keep getting served while ``time.sleep``
    paces the Moxfield requests.

    On success, atomically inserts the binder and its cards in a single
    transaction and marks the job as done. On failure (including cancellation
    detected mid-stream), the job is marked accordingly and no binder rows
    are committed for a fresh fetch. Refresh handling is in run_refresh_job.
    """
    await asyncio.to_thread(
        _run_fetch_job_sync,
        db_path,
        job_id,
        binder_id,
        scraper,
        pages_iter,
    )


def _run_fetch_job_sync(
    db_path: Path,
    job_id: int,
    binder_id: str,
    scraper: Any,
    pages_iter: PagesIter,
) -> None:
    _log.info("fetch job %s starting for binder %s", job_id, binder_id)
    drained = _drain_pages(db_path, job_id, binder_id, scraper, pages_iter, label="fetch")
    if drained is None:
        return

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        if job is not None and job.status == "cancelled":
            _log.info("fetch job %s cancelled before commit", job_id)
            return

        binder_row_id = db.create_binder(
            conn,
            moxfield_id=binder_id,
            name=drained.binder_name or binder_id,
            fetched_at=_now(),
            entry_count=len(drained.rows),
            total_cards=drained.total_cards,
            created_by_username=drained.created_by_username,
        )
        db.insert_cards(conn, binder_row_id, drained.rows)
        db.finish_job(conn, job_id, updated_at=_now())
    _log.info(
        "fetch job %s done — %d entries, %d cards",
        job_id, len(drained.rows), drained.total_cards,
    )


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
    metadata. Runs on a worker thread for the same reason as run_fetch_job.
    """
    await asyncio.to_thread(
        _run_refresh_job_sync,
        db_path,
        job_id,
        binder_id,
        existing_binder_id,
        scraper,
        pages_iter,
    )


def _run_refresh_job_sync(
    db_path: Path,
    job_id: int,
    binder_id: str,
    existing_binder_id: int,
    scraper: Any,
    pages_iter: PagesIter,
) -> None:
    _log.info(
        "refresh job %s starting (binder=%s, existing_id=%d)",
        job_id, binder_id, existing_binder_id,
    )
    drained = _drain_pages(db_path, job_id, binder_id, scraper, pages_iter, label="refresh")
    if drained is None:
        return

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        if job is not None and job.status == "cancelled":
            _log.info("refresh job %s cancelled before swap", job_id)
            return

        # Atomic swap: the whole `with` block is one transaction (connect()
        # commits on clean exit, rolls back on exception).
        db.delete_cards_for_binder(conn, existing_binder_id)
        db.update_binder_metadata(
            conn,
            existing_binder_id,
            name=drained.binder_name or binder_id,
            fetched_at=_now(),
            entry_count=len(drained.rows),
            total_cards=drained.total_cards,
            created_by_username=drained.created_by_username,
        )
        db.insert_cards(conn, existing_binder_id, drained.rows)
        db.finish_job(conn, job_id, updated_at=_now())
    _log.info(
        "refresh job %s done — %d entries, %d cards swapped in",
        job_id, len(drained.rows), drained.total_cards,
    )
