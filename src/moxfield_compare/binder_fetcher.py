from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, cast

import cloudscraper  # pyright: ignore[reportMissingTypeStubs]

from moxfield_compare.web.db import CardRow

_API_TEMPLATE = "https://api2.moxfield.com/v1/trade-binders/{binder_id}"
_PAGE_SIZE = 100
_PACING_SECONDS = 0.4
_REQUEST_TIMEOUT = 30

_FINISH_TO_FOIL = {
    "nonFoil": "",
    "foil": "foil",
    "etched": "etched",
}

_BINDER_URL_RE = re.compile(r"/binders/([A-Za-z0-9_-]+)")


def make_scraper(binder_id: str) -> Any:
    """Build a cloudscraper session pre-configured with the headers Moxfield's
    Cloudflare challenge expects. Both the standalone script and the in-process
    web worker use this."""
    s: Any = cloudscraper.create_scraper(  # pyright: ignore[reportUnknownMemberType]
        browser={"browser": "chrome", "platform": "darwin", "desktop": True},
    )
    s.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://moxfield.com",
            "Referer": f"https://moxfield.com/binders/{binder_id}",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
        }
    )
    return s


@dataclass(frozen=True)
class PageResult:
    page_number: int
    total_pages: int
    binder_name: str
    entries: list[dict[str, Any]]


class Scraper(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: int) -> Any: ...


def extract_binder_id(raw: str) -> str:
    """Accept a full Moxfield URL or a bare ID; return the bare ID."""
    s = raw.strip().rstrip("/")
    m = _BINDER_URL_RE.search(s)
    if m:
        return m.group(1)
    return s


def fetch_pages(
    scraper: Scraper, binder_id: str, *, pacing_seconds: float = _PACING_SECONDS
) -> Iterator[PageResult]:
    """Yield one PageResult per Moxfield API page. Caller decides what to do
    with each page (write to DB, accumulate in memory, etc.)."""
    url = _API_TEMPLATE.format(binder_id=binder_id)
    page = 1
    total_pages = 1
    binder_name = ""
    while page <= total_pages:
        if page > 1:
            time.sleep(pacing_seconds)
        r = scraper.get(
            url,
            params={"pageNumber": page, "pageSize": _PAGE_SIZE},
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        payload = cast(dict[str, Any], r.json())
        if page == 1:
            total_pages = int(payload.get("totalPages") or 0) or 1
            trade_binder = cast(dict[str, Any], payload.get("tradeBinder") or {})
            binder_name = str(trade_binder.get("name", ""))
        entries = cast(list[dict[str, Any]], payload.get("data") or [])
        yield PageResult(
            page_number=page,
            total_pages=total_pages,
            binder_name=binder_name,
            entries=list(entries),
        )
        page += 1


def entry_to_card_row(entry: dict[str, Any]) -> CardRow:
    """Map one Moxfield API entry to a CardRow ready for SQLite insertion."""
    card = cast(dict[str, Any], entry.get("card") or {})
    finish = str(entry.get("finish", "nonFoil"))
    name = str(card.get("name", ""))
    scryfall_id_raw = card.get("scryfall_id")
    scryfall_id = str(scryfall_id_raw) if scryfall_id_raw is not None else None
    return CardRow(
        name=name,
        name_lower=unicodedata.normalize("NFC", name.strip()).lower(),
        edition=str(card.get("set", "")).lower(),
        collector_number=str(card.get("cn", "")).lower(),
        count=int(entry.get("quantity") or 0),
        foil=_FINISH_TO_FOIL.get(finish, ""),
        scryfall_id=scryfall_id,
    )
