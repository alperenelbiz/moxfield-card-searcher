"""HTTP route handlers for the moxfield-compare web UI.

`register_routes` attaches all routes to a given FastAPI app. Tests that
need to stub the background workers monkeypatch `run_fetch_job` /
`run_refresh_job` on this module — that's why both names are imported at
module scope rather than locally inside `register_routes`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from moxfield_compare.binder_fetcher import extract_binder_id, make_scraper
from moxfield_compare.collection import Collection
from moxfield_compare.matcher import match
from moxfield_compare.models import MatchTier
from moxfield_compare.parser import parse_list_text
from moxfield_compare.web import db
from moxfield_compare.web._util import iso_now
from moxfield_compare.web.jobs import run_fetch_job, run_refresh_job
from moxfield_compare.web.view_helpers import (
    annotation_for,
    format_want_line,
    marker_for,
)


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
            existing = conn.execute(
                "SELECT 1 FROM binders WHERE moxfield_id=?", (binder_id,)
            ).fetchone()
            if existing is not None:
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
        asyncio.create_task(
            run_fetch_job(
                db_path=db_path,
                job_id=job_id,
                binder_id=binder_id,
                scraper=scraper,
            )
        )
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def get_job(request: Request, job_id: int) -> HTMLResponse:
        with db.connect(db_path) as conn:
            job = db.get_job(conn, job_id)
            if job is None:
                raise HTTPException(404, "job not found")
            if job.status == "done":
                row = conn.execute(
                    "SELECT id, moxfield_id, name, fetched_at, entry_count, total_cards "
                    "FROM binders WHERE moxfield_id=?",
                    (job.moxfield_id,),
                ).fetchone()
                if row is not None:
                    binder = db.BinderRow(
                        id=row["id"],
                        moxfield_id=row["moxfield_id"],
                        name=row["name"],
                        fetched_at=row["fetched_at"],
                        entry_count=row["entry_count"],
                        total_cards=row["total_cards"],
                    )
                    return templates.TemplateResponse(
                        request,
                        "_binder_row.html",
                        {"binder": binder},
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
            row = conn.execute(
                "SELECT moxfield_id FROM binders WHERE id=?", (binder_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "binder not found")
            mox_id = row["moxfield_id"]
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
        asyncio.create_task(
            run_refresh_job(
                db_path=db_path,
                job_id=job_id,
                binder_id=mox_id,
                existing_binder_id=binder_id,
                scraper=scraper,
            )
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

        with db.connect(db_path) as conn:
            binders = db.list_binders(conn)
            per_binder_results: dict[int, list[dict[str, Any]]] = {}
            binder_to_name: dict[int, str] = {}
            for b in binders:
                binder_to_name[b.id] = b.name
                cards = db.list_cards(conn, b.id)
                collection = Collection.from_db_rows(cards)
                scryfall_index: dict[tuple[str, str, str], str | None] = {
                    (c.name_lower, c.edition, c.collector_number): c.scryfall_id for c in cards
                }
                results: list[dict[str, Any]] = []
                for w in wants:
                    res = match(w, collection)
                    if res.tier is MatchTier.NON_HIT:
                        continue
                    sid: str | None = None
                    if w.set and w.cn:
                        sid = scryfall_index.get((w.name, w.set, w.cn))
                    if sid is None:
                        sid = next(
                            (sc for (n, _, _), sc in scryfall_index.items() if n == w.name),
                            None,
                        )
                    results.append(
                        {
                            "tier": res.tier,
                            "marker": marker_for(res.tier),
                            "name": w.display_name,
                            "scryfall_id": sid,
                            "annotation": annotation_for(res),
                            "also_in": [],
                        }
                    )
                per_binder_results[b.id] = results

        name_to_binders: dict[str, set[int]] = {}
        for bid, results in per_binder_results.items():
            for r in results:
                name_to_binders.setdefault(r["name"], set()).add(bid)
        for bid, results in per_binder_results.items():
            for r in results:
                others = name_to_binders.get(r["name"], set()) - {bid}
                r["also_in"] = sorted(binder_to_name[oid] for oid in others)

        missing_lines: list[str] = []
        for w in wants:
            present = any(
                any(r["name"] == w.display_name for r in per_binder_results[b.id]) for b in binders
            )
            if not present:
                missing_lines.append(format_want_line(w))

        binder_groups = [
            {
                "binder": b,
                "results": per_binder_results[b.id],
                "found_count": len(per_binder_results[b.id]),
            }
            for b in binders
        ]
        return templates.TemplateResponse(
            request,
            "_search_results.html",
            {
                "binder_groups": binder_groups,
                "missing": missing_lines,
                "total_wants": len(wants),
                "file_overrode_text": file_overrode_text,
            },
        )
