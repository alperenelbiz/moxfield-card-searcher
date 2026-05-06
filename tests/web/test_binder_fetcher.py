import json
from pathlib import Path
from typing import Any

from moxfield_card_searcher.binder_fetcher import (
    PageResult,
    entry_to_card_row,
    extract_binder_id,
    fetch_pages,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class StubScraper:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> "_StubResponse":
        self.calls.append({"url": url, "params": params})
        idx = int(params["pageNumber"]) - 1
        return _StubResponse(self._pages[idx])


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._payload


def test_extract_binder_id_from_url() -> None:
    assert extract_binder_id("https://moxfield.com/binders/ABC123") == "ABC123"
    assert extract_binder_id("https://moxfield.com/binders/ABC123/") == "ABC123"
    assert extract_binder_id("ABC123") == "ABC123"
    assert extract_binder_id("  ABC123  ") == "ABC123"


def test_fetch_pages_yields_per_page() -> None:
    scraper = StubScraper([_load("binder_page_1.json"), _load("binder_page_2.json")])
    results: list[PageResult] = list(fetch_pages(scraper, "TESTBINDER", pacing_seconds=0))
    assert len(results) == 2
    assert results[0].page_number == 1
    assert results[0].total_pages == 2
    assert results[0].binder_name == "Test Binder"
    assert len(results[0].entries) == 2
    assert results[1].page_number == 2
    assert len(results[1].entries) == 1


def test_entry_to_card_row_non_foil() -> None:
    page = _load("binder_page_1.json")
    entry = page["data"][0]
    row = entry_to_card_row(entry)
    assert row.name == "Lightning Bolt"
    assert row.name_lower == "lightning bolt"
    assert row.edition == "m21"
    assert row.collector_number == "162"
    assert row.count == 4
    assert row.foil == ""
    assert row.scryfall_id == "abc-001"


def test_entry_to_card_row_foil() -> None:
    page = _load("binder_page_1.json")
    entry = page["data"][1]
    row = entry_to_card_row(entry)
    assert row.foil == "foil"


def test_entry_to_card_row_etched() -> None:
    page = _load("binder_page_2.json")
    entry = page["data"][0]
    row = entry_to_card_row(entry)
    assert row.foil == "etched"


def test_entry_to_card_row_lowercases_set_and_cn() -> None:
    entry = {
        "quantity": 1,
        "finish": "nonFoil",
        "card": {
            "scryfall_id": "x",
            "set": "M21",
            "name": "Foo",
            "cn": "162A",
        },
    }
    row = entry_to_card_row(entry)
    assert row.edition == "m21"
    assert row.collector_number == "162a"
