"""FastAPI app factory and console entry point.

Routes themselves live in `routes.py`; this module wires together the app,
templates, static files, and the argparse + uvicorn launcher.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from moxfield_card_searcher.web import db
from moxfield_card_searcher.web.routes import register_routes

_PACKAGE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
_STATIC_DIR = _PACKAGE_DIR / "static"


def build_app(*, db_path: Path) -> FastAPI:
    """Construct a FastAPI app bound to a specific SQLite path. Tests pass a
    tmp_path; the production runner passes the configured DB location."""
    db.init_schema(db_path)
    app = FastAPI()
    app.state.db_path = db_path
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    register_routes(app, db_path=db_path, templates=templates)
    return app


def run(argv: list[str] | None = None) -> None:
    """Console entry point: `moxfield-card-searcher-ui [--host ...] [--port ...] [--db ...]`."""
    p = argparse.ArgumentParser(prog="moxfield-card-searcher-ui")
    p.add_argument("--host", default=os.environ.get("MOXFIELD_CARD_SEARCHER_HOST", "127.0.0.1"))
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MOXFIELD_CARD_SEARCHER_PORT", "8000")),
    )
    p.add_argument(
        "--db", type=Path, default=Path(os.environ.get("MOXFIELD_CARD_SEARCHER_DB", "binders.db"))
    )
    args = p.parse_args(argv)

    import uvicorn

    app = build_app(db_path=args.db)
    uvicorn.run(app, host=args.host, port=args.port)
