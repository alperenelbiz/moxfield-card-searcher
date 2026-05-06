from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from moxfield_card_searcher.web import db
from moxfield_card_searcher.web.app import build_app


def test_search_via_textarea(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
    r = client.post(
        "/search",
        data={"wantlist_text": "4 Lightning Bolt (M21) 162\n1 Black Lotus\n"},
    )
    assert r.status_code == 200
    assert "Bulk" in r.text
    assert "Lightning Bolt" in r.text
    assert "Black Lotus" in r.text  # in missing bucket
    assert "lb-m21" in r.text  # image URL pattern uses scryfall_id
    assert 'href="https://moxfield.com/binders/BULK"' in r.text


def test_search_via_file_upload(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
    file_content = b"1 Goblin Guide\n"
    r = client.post(
        "/search",
        files={"wantlist_file": ("want.txt", BytesIO(file_content), "text/plain")},
    )
    assert r.status_code == 200
    assert "Goblin Guide" in r.text
    assert "Sell" in r.text


def test_search_file_overrides_textarea(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
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


def test_search_rejects_empty_input(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
    r = client.post("/search", data={"wantlist_text": "   "})
    assert r.status_code == 400


def test_search_returns_400_on_parse_error(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
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


def test_search_missing_entry_with_set_and_foil_renders_set_cell(seeded_db: Path) -> None:
    client = TestClient(build_app(db_path=seeded_db))
    # Seed a clearly-missing card with set+cn+foil so the missing-table
    # set cell exercises the (set, cn) and foil_only branches.
    r = client.post(
        "/search",
        data={"wantlist_text": "1 Imaginary Card (XYZ) 999 *F*\n"},
    )
    assert r.status_code == 200
    assert "Imaginary Card" in r.text
    # Set cell renders "(XYZ) 999 *F*" — uppercase set, then CN, then foil marker.
    assert "(XYZ) 999 *F*" in r.text
