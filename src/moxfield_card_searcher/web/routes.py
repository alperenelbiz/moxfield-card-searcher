"""HTTP route handlers for the moxfield-card-searcher web UI.

`register_routes` attaches all routes to a given FastAPI app. Tests that
need to stub the background workers monkeypatch `run_fetch_job` /
`run_refresh_job` on this module — that's why both names are imported at
module scope rather than locally inside `register_routes`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from moxfield_card_searcher.binder_fetcher import extract_binder_id, make_scraper
from moxfield_card_searcher.parser import parse_list_text
from moxfield_card_searcher.web import db
from moxfield_card_searcher.web._util import iso_now
from moxfield_card_searcher.web.jobs import run_fetch_job, run_refresh_job
from moxfield_card_searcher.web.search_service import run_search


def _spawn_background(app: FastAPI, coro: Coroutine[Any, Any, None]) -> None:
    """Schedule a worker coroutine and keep a strong reference until it
    finishes. Without the set membership, asyncio is free to garbage-collect
    the task mid-flight (see asyncio.create_task docs)."""
    task = asyncio.create_task(coro)
    app.state.background_tasks.add(task)
    task.add_done_callback(app.state.background_tasks.discard)


def register_routes(
    app: FastAPI, *, db_path: Path, templates: Jinja2Templates
) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        with db.connect(db_path) as conn:
            binders = db.list_binders(conn)
            jobs = db.list_jobs(conn)
        return templates.TemplateResponse(
            request,
            "index.html",
            {"binders": binders, "jobs": jobs},
        )

    @app.post("/binders", response_class=HTMLResponse)
    async def add_binder(
        request: Request,
        binder_input: str = Form(...),
    ) -> HTMLResponse:
        binder_id = extract_binder_id(binder_input)
        if not binder_id:
            raise HTTPException(400, "binder URL or ID required")
        with db.connect(db_path) as conn:
            if db.get_binder_by_moxfield_id(conn, binder_id) is not None:
                raise HTTPException(409, "binder already saved — use Refresh")
            if db.has_active_job(conn, binder_id):
                raise HTTPException(409, "already fetching this binder")
            job_id = db.create_job(
                conn,
                moxfield_id=binder_id,
                refresh_of_binder_id=None,
                created_at=iso_now(),
            )
            job = db.get_job(conn, job_id)
        scraper = make_scraper(binder_id)
        _spawn_background(
            app,
            run_fetch_job(
                db_path=db_path,
                job_id=job_id,
                binder_id=binder_id,
                scraper=scraper,
            ),
        )
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def get_job(request: Request, job_id: int) -> HTMLResponse:
        with db.connect(db_path) as conn:
            job = db.get_job(conn, job_id)
            if job is None:
                raise HTTPException(404, "job not found")
            binder = (
                db.get_binder_by_moxfield_id(conn, job.moxfield_id)
                if job.status == "done"
                else None
            )
        if binder is not None:
            return templates.TemplateResponse(
                request, "_binder_row.html", {"binder": binder}
            )
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.delete("/binders/{binder_id}")
    async def delete_binder(binder_id: int) -> str:
        with db.connect(db_path) as conn:
            ok = db.delete_binder(conn, binder_id)
        if not ok:
            raise HTTPException(404, "binder not found")
        return ""

    @app.post("/binders/{binder_id}/refresh", response_class=HTMLResponse)
    async def refresh_binder(request: Request, binder_id: int) -> HTMLResponse:
        with db.connect(db_path) as conn:
            existing = db.get_binder_by_id(conn, binder_id)
            if existing is None:
                raise HTTPException(404, "binder not found")
            mox_id = existing.moxfield_id
            if db.has_active_job(conn, mox_id):
                raise HTTPException(409, "already refreshing")
            job_id = db.create_job(
                conn,
                moxfield_id=mox_id,
                refresh_of_binder_id=binder_id,
                created_at=iso_now(),
            )
            job = db.get_job(conn, job_id)
        scraper = make_scraper(mox_id)
        _spawn_background(
            app,
            run_refresh_job(
                db_path=db_path,
                job_id=job_id,
                binder_id=mox_id,
                existing_binder_id=binder_id,
                scraper=scraper,
            ),
        )
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: int) -> str:
        with db.connect(db_path) as conn:
            job = db.get_job(conn, job_id)
            if job is None:
                raise HTTPException(404, "job not found")
            db.cancel_job(conn, job_id, updated_at=iso_now())
        return ""

    @app.post("/search", response_class=HTMLResponse)
    async def search(
        request: Request,
        wantlist_file: UploadFile | None = File(None),
        wantlist_text: str | None = Form(None),
    ) -> HTMLResponse:
        text: str | None = None
        file_overrode_text = False
        if wantlist_file is not None and wantlist_file.filename:
            content_bytes = await wantlist_file.read()
            text = content_bytes.decode("utf-8")
            if wantlist_text and wantlist_text.strip():
                file_overrode_text = True
        elif wantlist_text and wantlist_text.strip():
            text = wantlist_text
        if text is None:
            raise HTTPException(400, "provide a file or paste a list")
        try:
            wants = parse_list_text(text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        result = run_search(db_path, wants)
        return templates.TemplateResponse(
            request,
            "_search_results.html",
            {
                "binder_groups": result.binder_groups,
                "missing": result.missing,
                "total_wants": result.total_wants,
                "file_overrode_text": file_overrode_text,
            },
        )
