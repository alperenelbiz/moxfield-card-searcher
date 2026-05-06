from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from moxfield_card_searcher.web import db
from moxfield_card_searcher.web.app import build_app


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _seed(db_path: Path) -> None:
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        bulk = db.create_binder(
            conn,
            moxfield_id="BULK",
            name="Bulk",
            fetched_at=_now(),
            entry_count=2,
            total_cards=6,
        )
        db.insert_cards(
            conn,
            bulk,
            [
                db.CardRow(
                    name="Lightning Bolt",
                    name_lower="lightning bolt",
                    edition="m21",
                    collector_number="162",
                    count=4,
                    foil="",
                    scryfall_id="lb-m21",
                ),
                db.CardRow(
                    name="Sol Ring",
                    name_lower="sol ring",
                    edition="cmm",
                    collector_number="410",
                    count=2,
                    foil="",
                    scryfall_id="sr-cmm",
                ),
            ],
        )
        sell = db.create_binder(
            conn,
            moxfield_id="SELL",
            name="Sell",
            fetched_at=_now(),
            entry_count=1,
            total_cards=1,
        )
        db.insert_cards(
            conn,
            sell,
            [
                db.CardRow(
                    name="Goblin Guide",
                    name_lower="goblin guide",
                    edition="2x2",
                    collector_number="118",
                    count=1,
                    foil="",
                    scryfall_id="gg-2x2",
                ),
            ],
        )


def test_search_via_textarea(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed(db_path)
    client = TestClient(build_app(db_path=db_path))
    r = client.post(
        "/search",
        data={"wantlist_text": "4 Lightning Bolt (M21) 162\n1 Black Lotus\n"},
    )
    assert r.status_code == 200
    assert "Bulk" in r.text
    assert "Lightning Bolt" in r.text
    assert "Black Lotus" in r.text  # in missing bucket
    assert "lb-m21" in r.text  # image URL pattern uses scryfall_id


def test_search_via_file_upload(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed(db_path)
    client = TestClient(build_app(db_path=db_path))
    file_content = b"1 Goblin Guide\n"
    r = client.post(
        "/search",
        files={"wantlist_file": ("want.txt", BytesIO(file_content), "text/plain")},
    )
    assert r.status_code == 200
    assert "Goblin Guide" in r.text
    assert "Sell" in r.text


def test_search_file_overrides_textarea(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed(db_path)
    client = TestClient(build_app(db_path=db_path))
    file_content = b"1 Goblin Guide\n"
    r = client.post(
        "/search",
        files={"wantlist_file": ("want.txt", BytesIO(file_content), "text/plain")},
        data={"wantlist_text": "4 Lightning Bolt"},
    )
    assert r.status_code == 200
    assert "Goblin Guide" in r.text
    # Notice should mention textarea was ignored
    assert "ignored" in r.text.lower() or "textarea" in r.text.lower()


def test_search_rejects_empty_input(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed(db_path)
    client = TestClient(build_app(db_path=db_path))
    r = client.post("/search", data={"wantlist_text": "   "})
    assert r.status_code == 400


def test_search_returns_400_on_parse_error(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed(db_path)
    client = TestClient(build_app(db_path=db_path))
    # set without cn → parser raises
    r = client.post("/search", data={"wantlist_text": "4 Foo (M21)\n"})
    assert r.status_code == 400


def test_search_with_no_binders_renders_empty_results(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)  # no binders seeded
    client = TestClient(build_app(db_path=db_path))
    r = client.post("/search", data={"wantlist_text": "1 Lightning Bolt\n"})
    assert r.status_code == 200
    # Lightning Bolt shows up only in the "Not in any binder" bucket.
    assert "Lightning Bolt" in r.text
