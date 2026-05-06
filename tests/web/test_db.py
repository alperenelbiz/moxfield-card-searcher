import sqlite3
from pathlib import Path

from moxfield_card_searcher.web._util import iso_now as _now
from moxfield_card_searcher.web.db import (
    BinderRow,
    CardRow,
    JobRow,
    cancel_job,
    connect,
    create_binder,
    create_job,
    delete_binder,
    fail_job,
    finish_job,
    get_job,
    has_active_job,
    init_schema,
    insert_cards,
    list_binders,
    list_cards,
    list_jobs,
    update_job_progress,
)


def test_init_schema_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"binders", "cards", "fetch_jobs"} <= names


def test_connect_uses_wal_mode_and_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert journal.lower() == "wal"
    assert fk == 1


def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    init_schema(db_path)  # second call must not raise
    with connect(db_path) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"binders", "cards", "fetch_jobs"} <= names


def test_card_cascade_delete(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO binders(moxfield_id, name, fetched_at, entry_count, total_cards) "
            "VALUES (?, ?, ?, ?, ?)",
            ("abc", "Test", "2026-05-06T00:00:00", 1, 1),
        )
        binder_id = conn.execute("SELECT id FROM binders").fetchone()[0]
        conn.execute(
            "INSERT INTO cards(binder_id, name, name_lower, edition, "
            "collector_number, count, foil, scryfall_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (binder_id, "Lightning Bolt", "lightning bolt", "m21", "162", 4, "", "abc-123"),
        )
        conn.execute("DELETE FROM binders WHERE id=?", (binder_id,))
        conn.commit()
        cards_left = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    assert cards_left == 0


def test_unique_moxfield_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO binders(moxfield_id, name, fetched_at, entry_count, total_cards) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dup", "First", "2026-05-06T00:00:00", 0, 0),
        )
        try:
            conn.execute(
                "INSERT INTO binders(moxfield_id, name, fetched_at, entry_count, total_cards) "
                "VALUES (?, ?, ?, ?, ?)",
                ("dup", "Second", "2026-05-06T00:00:00", 0, 0),
            )
            conn.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
    assert raised


def test_create_and_list_binders(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        bid = create_binder(
            conn,
            moxfield_id="abc",
            name="Test Binder",
            fetched_at=_now(),
            entry_count=2,
            total_cards=5,
        )
        rows = list_binders(conn)
    assert isinstance(bid, int) and bid > 0
    assert len(rows) == 1
    assert isinstance(rows[0], BinderRow)
    assert rows[0].moxfield_id == "abc"
    assert rows[0].entry_count == 2


def test_insert_and_list_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        bid = create_binder(
            conn,
            moxfield_id="b1",
            name="B1",
            fetched_at=_now(),
            entry_count=2,
            total_cards=6,
        )
        insert_cards(
            conn,
            bid,
            [
                CardRow(
                    name="Lightning Bolt",
                    name_lower="lightning bolt",
                    edition="m21",
                    collector_number="162",
                    count=4,
                    foil="",
                    scryfall_id="abc-123",
                ),
                CardRow(
                    name="Sol Ring",
                    name_lower="sol ring",
                    edition="cmm",
                    collector_number="410",
                    count=2,
                    foil="foil",
                    scryfall_id="def-456",
                ),
            ],
        )
        cards = list_cards(conn, bid)
    assert len(cards) == 2
    assert {c.name for c in cards} == {"Lightning Bolt", "Sol Ring"}


def test_delete_binder_removes_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        bid = create_binder(
            conn,
            moxfield_id="b2",
            name="B2",
            fetched_at=_now(),
            entry_count=1,
            total_cards=1,
        )
        insert_cards(
            conn,
            bid,
            [
                CardRow(
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
        deleted = delete_binder(conn, bid)
        cards = list_cards(conn, bid)
    assert deleted is True
    assert cards == []


def test_delete_nonexistent_binder_returns_false(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        assert delete_binder(conn, 999) is False


def test_create_and_get_job(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        jid = create_job(conn, moxfield_id="abc", refresh_of_binder_id=None, created_at=_now())
        job = get_job(conn, jid)
    assert job is not None
    assert isinstance(job, JobRow)
    assert job.moxfield_id == "abc"
    assert job.status == "pending"
    assert job.refresh_of_binder_id is None
    assert job.pages_total == 0
    assert job.pages_done == 0


def test_update_job_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        jid = create_job(conn, moxfield_id="abc", refresh_of_binder_id=None, created_at=_now())
        update_job_progress(
            conn,
            jid,
            status="fetching",
            pages_done=3,
            pages_total=10,
            updated_at=_now(),
        )
        job = get_job(conn, jid)
    assert job is not None
    assert job.status == "fetching"
    assert job.pages_done == 3
    assert job.pages_total == 10
    assert job.progress_pct == 30


def test_finish_job_marks_done(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        jid = create_job(conn, moxfield_id="abc", refresh_of_binder_id=None, created_at=_now())
        finish_job(conn, jid, updated_at=_now())
        job = get_job(conn, jid)
    assert job is not None
    assert job.status == "done"
    assert job.progress_pct == 100


def test_fail_job_records_error(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        jid = create_job(conn, moxfield_id="abc", refresh_of_binder_id=None, created_at=_now())
        fail_job(conn, jid, error="network timeout", updated_at=_now())
        job = get_job(conn, jid)
    assert job is not None
    assert job.status == "failed"
    assert job.error_message == "network timeout"


def test_cancel_job(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        jid = create_job(conn, moxfield_id="abc", refresh_of_binder_id=None, created_at=_now())
        cancel_job(conn, jid, updated_at=_now())
        job = get_job(conn, jid)
    assert job is not None
    assert job.status == "cancelled"


def test_has_active_job(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        assert has_active_job(conn, "x") is False
        jid = create_job(conn, moxfield_id="x", refresh_of_binder_id=None, created_at=_now())
        assert has_active_job(conn, "x") is True
        update_job_progress(
            conn, jid, status="fetching", pages_done=1, pages_total=10, updated_at=_now()
        )
        assert has_active_job(conn, "x") is True
        finish_job(conn, jid, updated_at=_now())
        # done jobs do NOT count as active
        assert has_active_job(conn, "x") is False


def test_list_jobs_returns_only_unfinished(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_schema(db_path)
    with connect(db_path) as conn:
        active = create_job(conn, moxfield_id="a", refresh_of_binder_id=None, created_at=_now())
        done = create_job(conn, moxfield_id="b", refresh_of_binder_id=None, created_at=_now())
        finish_job(conn, done, updated_at=_now())
        jobs = list_jobs(conn)
    assert {j.id for j in jobs} == {active}
