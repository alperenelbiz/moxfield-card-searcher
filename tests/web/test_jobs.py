import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moxfield_card_searcher.binder_fetcher import PageResult
from moxfield_card_searcher.web import db
from moxfield_card_searcher.web.jobs import run_fetch_job, run_refresh_job

FIXTURES = Path(__file__).parent / "fixtures"


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _load_pages() -> list[PageResult]:
    p1 = json.loads((FIXTURES / "binder_page_1.json").read_text(encoding="utf-8"))
    p2 = json.loads((FIXTURES / "binder_page_2.json").read_text(encoding="utf-8"))
    return [
        PageResult(
            page_number=1,
            total_pages=2,
            binder_name="Test Binder",
            entries=list(p1["data"]),
        ),
        PageResult(
            page_number=2,
            total_pages=2,
            binder_name="Test Binder",
            entries=list(p2["data"]),
        ),
    ]


def test_run_fetch_job_happy_path(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    pages = _load_pages()

    def fake_pages_iter(_scraper: Any, _binder_id: str) -> Any:
        yield from pages

    with db.connect(db_path) as conn:
        job_id = db.create_job(
            conn, moxfield_id="TESTBINDER", refresh_of_binder_id=None, created_at=_now()
        )

    asyncio.run(
        run_fetch_job(
            db_path=db_path,
            job_id=job_id,
            binder_id="TESTBINDER",
            scraper=object(),  # unused: fake_pages_iter ignores it
            pages_iter=fake_pages_iter,
        )
    )

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        binders = db.list_binders(conn)
    assert job is not None
    assert job.status == "done"
    assert len(binders) == 1
    assert binders[0].name == "Test Binder"
    assert binders[0].entry_count == 3
    assert binders[0].total_cards == 7  # 4 + 1 + 2


def test_run_fetch_job_records_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)

    def boom(_scraper: Any, _binder_id: str) -> Any:
        if False:
            yield  # generator
        raise RuntimeError("network down")

    with db.connect(db_path) as conn:
        job_id = db.create_job(conn, moxfield_id="X", refresh_of_binder_id=None, created_at=_now())

    asyncio.run(
        run_fetch_job(
            db_path=db_path,
            job_id=job_id,
            binder_id="X",
            scraper=object(),
            pages_iter=boom,
        )
    )

    with db.connect(db_path) as conn:
        job = db.get_job(conn, job_id)
        binders = db.list_binders(conn)
    assert job is not None
    assert job.status == "failed"
    assert job.error_message == "network down"
    assert binders == []  # nothing committed


def test_run_fetch_job_respects_cancellation(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    pages = _load_pages()

    def slow_pages(_scraper: Any, _binder_id: str) -> Any:
        yield from pages

    with db.connect(db_path) as conn:
        job_id = db.create_job(conn, moxfield_id="C", refresh_of_binder_id=None, created_at=_now())
        # pre-cancel before the job runs - first iteration of the worker loop
        # should observe the cancelled status and exit before insert.
        db.cancel_job(conn, job_id, updated_at=_now())

    asyncio.run(
        run_fetch_job(
            db_path=db_path,
            job_id=job_id,
            binder_id="C",
            scraper=object(),
            pages_iter=slow_pages,
        )
    )

    with db.connect(db_path) as conn:
        binders = db.list_binders(conn)
        job = db.get_job(conn, job_id)
    assert binders == []
    assert job is not None
    assert job.status == "cancelled"


def test_run_refresh_job_replaces_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    pages = _load_pages()

    def fake_pages_iter(_scraper: Any, _binder_id: str) -> Any:
        yield from pages

    # Seed: existing binder with one stale card.
    with db.connect(db_path) as conn:
        bid = db.create_binder(
            conn,
            moxfield_id="TESTBINDER",
            name="Stale Name",
            fetched_at=_now(),
            entry_count=1,
            total_cards=1,
        )
        db.insert_cards(
            conn,
            bid,
            [
                db.CardRow(
                    name="Stale Card",
                    name_lower="stale card",
                    edition="x",
                    collector_number="1",
                    count=1,
                    foil="",
                    scryfall_id="stale",
                )
            ],
        )
        job_id = db.create_job(
            conn,
            moxfield_id="TESTBINDER",
            refresh_of_binder_id=bid,
            created_at=_now(),
        )

    asyncio.run(
        run_refresh_job(
            db_path=db_path,
            job_id=job_id,
            binder_id="TESTBINDER",
            existing_binder_id=bid,
            scraper=object(),
            pages_iter=fake_pages_iter,
        )
    )

    with db.connect(db_path) as conn:
        binders = db.list_binders(conn)
        cards = db.list_cards(conn, bid)
        job = db.get_job(conn, job_id)
    assert len(binders) == 1
    assert binders[0].id == bid  # same row, atomic swap
    assert binders[0].name == "Test Binder"
    assert binders[0].entry_count == 3
    assert {c.name for c in cards} == {"Lightning Bolt", "Sol Ring"}
    assert "Stale Card" not in {c.name for c in cards}
    assert job is not None
    assert job.status == "done"


def test_run_refresh_job_failure_preserves_old_data(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)

    def boom(_scraper: Any, _binder_id: str) -> Any:
        if False:
            yield
        raise RuntimeError("api boom")

    with db.connect(db_path) as conn:
        bid = db.create_binder(
            conn,
            moxfield_id="REF",
            name="Original",
            fetched_at=_now(),
            entry_count=1,
            total_cards=4,
        )
        db.insert_cards(
            conn,
            bid,
            [
                db.CardRow(
                    name="Original Card",
                    name_lower="original card",
                    edition="x",
                    collector_number="1",
                    count=4,
                    foil="",
                    scryfall_id="orig",
                )
            ],
        )
        job_id = db.create_job(
            conn,
            moxfield_id="REF",
            refresh_of_binder_id=bid,
            created_at=_now(),
        )

    asyncio.run(
        run_refresh_job(
            db_path=db_path,
            job_id=job_id,
            binder_id="REF",
            existing_binder_id=bid,
            scraper=object(),
            pages_iter=boom,
        )
    )

    with db.connect(db_path) as conn:
        binders = db.list_binders(conn)
        cards = db.list_cards(conn, bid)
        job = db.get_job(conn, job_id)
    assert binders[0].name == "Original"
    assert binders[0].entry_count == 1
    assert cards[0].name == "Original Card"
    assert job is not None
    assert job.status == "failed"
    assert job.error_message == "api boom"
