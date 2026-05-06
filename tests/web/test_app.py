import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from moxfield_card_searcher.web import db
from moxfield_card_searcher.web._util import iso_now as _now
from moxfield_card_searcher.web.app import build_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = build_app(db_path=tmp_path / "test.db")
    return TestClient(app)


def test_get_index_returns_200(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert 'id="binders"' in r.text
    assert 'id="search"' in r.text


def test_get_static_css(client: TestClient) -> None:
    r = client.get("/static/app.css")
    assert r.status_code == 200
    assert "body" in r.text


def test_post_binders_creates_pending_job_and_starts_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "test.db"

    started: list[int] = []

    async def fake_runner(
        *, db_path: Path, job_id: int, binder_id: str, scraper: Any, **_: Any
    ) -> None:
        started.append(job_id)

    from moxfield_card_searcher.web import app as app_module
    from moxfield_card_searcher.web import routes as routes_module

    monkeypatch.setattr(routes_module, "run_fetch_job", fake_runner)

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)

    r = client.post("/binders", data={"binder_input": "https://moxfield.com/binders/ABC"})
    assert r.status_code == 200
    assert "ABC" in r.text or "fetching" in r.text.lower() or "pending" in r.text.lower()

    # The fake runner is scheduled — we run the loop briefly to let it execute.
    asyncio.run(asyncio.sleep(0))  # allow scheduled task to start (best effort)

    with db.connect(db_path) as conn:
        jobs = db.list_jobs(conn)
    assert len(jobs) == 1
    assert jobs[0].moxfield_id == "ABC"


def test_post_binders_rejects_existing_binder(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        db.create_binder(
            conn,
            moxfield_id="DUP",
            name="Dup",
            fetched_at=_now(),
            entry_count=0,
            total_cards=0,
        )

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)

    r = client.post("/binders", data={"binder_input": "DUP"})
    assert r.status_code == 409
    assert "already" in r.text.lower()


def test_post_binders_rejects_empty_input(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.post("/binders", data={"binder_input": "   "})
    assert r.status_code == 400


def test_get_jobs_returns_job_row_when_in_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        job_id = db.create_job(
            conn,
            moxfield_id="X",
            refresh_of_binder_id=None,
            created_at=_now(),
        )
        db.update_job_progress(
            conn,
            job_id,
            status="fetching",
            pages_done=2,
            pages_total=10,
            updated_at=_now(),
        )

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "20" in r.text  # 2/10 = 20%
    assert "fetching" in r.text.lower() or "20%" in r.text


def test_get_jobs_returns_binder_row_when_done(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        job_id = db.create_job(
            conn,
            moxfield_id="DONE",
            refresh_of_binder_id=None,
            created_at=_now(),
        )
        db.create_binder(
            conn,
            moxfield_id="DONE",
            name="Done Binder",
            fetched_at=_now(),
            entry_count=10,
            total_cards=20,
        )
        db.finish_job(conn, job_id, updated_at=_now())

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "Done Binder" in r.text
    assert ">20<" in r.text  # total_cards rendered as plain numeric in <td class="num">
    assert 'href="https://moxfield.com/binders/DONE"' in r.text


def test_delete_binder_removes_row_and_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        bid = db.create_binder(
            conn,
            moxfield_id="DEL",
            name="To Delete",
            fetched_at=_now(),
            entry_count=1,
            total_cards=1,
        )
        db.insert_cards(
            conn,
            bid,
            [
                db.CardRow(
                    name="X",
                    name_lower="x",
                    edition="x",
                    collector_number="1",
                    count=1,
                    foil="",
                    scryfall_id=None,
                )
            ],
        )

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)

    r = client.delete(f"/binders/{bid}")
    assert r.status_code == 200

    with db.connect(db_path) as conn:
        binders = db.list_binders(conn)
        cards = db.list_cards(conn, bid)
    assert binders == []
    assert cards == []


def test_delete_nonexistent_binder_returns_404(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.delete("/binders/9999")
    assert r.status_code == 404


def test_refresh_binder_creates_refresh_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        bid = db.create_binder(
            conn,
            moxfield_id="RB",
            name="Refresh Me",
            fetched_at=_now(),
            entry_count=1,
            total_cards=1,
        )

    started: list[tuple[int, int]] = []

    async def fake_refresh(
        *,
        db_path: Path,
        job_id: int,
        binder_id: str,
        existing_binder_id: int,
        scraper: Any,
        **_: Any,
    ) -> None:
        started.append((job_id, existing_binder_id))

    from moxfield_card_searcher.web import app as app_module
    from moxfield_card_searcher.web import routes as routes_module

    monkeypatch.setattr(routes_module, "run_refresh_job", fake_refresh)
    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)

    r = client.post(f"/binders/{bid}/refresh")
    assert r.status_code == 200

    with db.connect(db_path) as conn:
        jobs = db.list_jobs(conn)
    assert len(jobs) == 1
    assert jobs[0].refresh_of_binder_id == bid


def test_refresh_conflict_when_job_already_active(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        bid = db.create_binder(
            conn,
            moxfield_id="RB2",
            name="x",
            fetched_at=_now(),
            entry_count=0,
            total_cards=0,
        )
        db.create_job(
            conn,
            moxfield_id="RB2",
            refresh_of_binder_id=bid,
            created_at=_now(),
        )

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.post(f"/binders/{bid}/refresh")
    assert r.status_code == 409


def test_refresh_404_for_nonexistent_binder(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.post("/binders/9999/refresh")
    assert r.status_code == 404


def test_cancel_job_marks_cancelled(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        job_id = db.create_job(
            conn,
            moxfield_id="CXL",
            refresh_of_binder_id=None,
            created_at=_now(),
        )
        db.update_job_progress(
            conn,
            job_id,
            status="fetching",
            pages_done=2,
            pages_total=10,
            updated_at=_now(),
        )

    from moxfield_card_searcher.web import app as app_module

    app = app_module.build_app(db_path=db_path)
    client = TestClient(app)
    r = client.post(f"/jobs/{job_id}/cancel")
    assert r.status_code == 200
    # Fresh-fetch cancel: no binder to restore, response is empty so HTMX
    # outerHTML swap removes the cancelled row from the table.
    assert r.text == ""

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
    assert job is not None
    assert job.status == "cancelled"


def test_cancel_refresh_restores_binder_row(tmp_path: Path) -> None:
    """Cancelling a refresh returns the original binder row markup so the UI
    swaps back from the cancelled job row to the (untouched) binder row
    without requiring a page reload."""
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        binder_id = db.create_binder(
            conn,
            moxfield_id="REFRESHME",
            name="Refresh Me",
            fetched_at=_now(),
            entry_count=3,
            total_cards=12,
        )
        job_id = db.create_job(
            conn,
            moxfield_id="REFRESHME",
            refresh_of_binder_id=binder_id,
            created_at=_now(),
        )
        db.update_job_progress(
            conn,
            job_id,
            status="fetching",
            pages_done=1,
            pages_total=4,
            updated_at=_now(),
        )

    client = TestClient(build_app(db_path=db_path))
    r = client.post(f"/jobs/{job_id}/cancel")
    assert r.status_code == 200
    # Response is the binder row, not empty / not the cancelled job row.
    assert "Refresh Me" in r.text
    assert 'href="https://moxfield.com/binders/REFRESHME"' in r.text
    assert 'class="binder-row"' in r.text
    assert "cancelled" not in r.text


def test_get_cancelled_refresh_job_renders_binder_row(tmp_path: Path) -> None:
    """If an HTMX poll wins the race against the cancel response, the GET
    endpoint must also resolve a cancelled-refresh job to the binder row."""
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        binder_id = db.create_binder(
            conn,
            moxfield_id="POLLED",
            name="Polled Binder",
            fetched_at=_now(),
            entry_count=2,
            total_cards=5,
        )
        job_id = db.create_job(
            conn,
            moxfield_id="POLLED",
            refresh_of_binder_id=binder_id,
            created_at=_now(),
        )
        db.cancel_job(conn, job_id, updated_at=_now())

    client = TestClient(build_app(db_path=db_path))
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "Polled Binder" in r.text
    assert 'class="binder-row"' in r.text


def test_get_cancelled_fresh_fetch_renders_job_row(tmp_path: Path) -> None:
    """A cancelled fresh fetch (no refresh_of_binder_id) has no binder to
    restore — the GET endpoint should still return the job row markup so the
    poll's existing swap logic resolves it (poll attribute is not emitted in
    cancelled state, so polling stops naturally)."""
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        job_id = db.create_job(
            conn,
            moxfield_id="ORPHAN",
            refresh_of_binder_id=None,
            created_at=_now(),
        )
        db.cancel_job(conn, job_id, updated_at=_now())

    client = TestClient(build_app(db_path=db_path))
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "cancelled" in r.text
    assert "ORPHAN" in r.text
    assert 'class="binder-row"' not in r.text


def test_run_argument_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    from moxfield_card_searcher.web import app as app_module

    captured: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, **kwargs: Any) -> None:
        captured["host"] = kwargs.get("host")
        captured["port"] = kwargs.get("port")

    import sys

    fake_module = type(sys)("uvicorn")
    fake_module.run = fake_uvicorn_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_module)

    app_module.run(["--host", "0.0.0.0", "--port", "9000", "--db", "/tmp/x.db"])
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000


def test_run_uses_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    from moxfield_card_searcher.web import app as app_module

    captured: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, **kwargs: Any) -> None:
        captured["host"] = kwargs.get("host")
        captured["port"] = kwargs.get("port")

    import sys

    fake_module = type(sys)("uvicorn")
    fake_module.run = fake_uvicorn_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_module)

    monkeypatch.setenv("MOXFIELD_CARD_SEARCHER_HOST", "10.0.0.1")
    monkeypatch.setenv("MOXFIELD_CARD_SEARCHER_PORT", "9100")
    monkeypatch.setenv("MOXFIELD_CARD_SEARCHER_DB", "/tmp/y.db")
    app_module.run([])
    assert captured["host"] == "10.0.0.1"
    assert captured["port"] == 9100
