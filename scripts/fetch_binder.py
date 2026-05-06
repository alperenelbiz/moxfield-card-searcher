# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "cloudscraper>=1.2.71",
# ]
# ///
"""Fetch a public Moxfield trade binder and emit a CSV in the format
moxfield-compare expects.

This script declares its own dependencies via PEP 723 inline metadata so it
does not pollute the core moxfield-compare package, which stays stdlib-only.
``uv run`` resolves the inline deps into an isolated environment automatically.

Usage:
    uv run scripts/fetch_binder.py <binder-public-id> <output.csv> [--limit-pages N]

Where <binder-public-id> is the trailing path segment of a binder URL like
https://moxfield.com/binders/YR6dKVcP8UK9Hg2qnSOsbA — the ID is "YR6...bA".

The Moxfield API sits behind Cloudflare, so we use cloudscraper to negotiate the
challenge. Pages are fetched at 100 entries each (the server cap) with a small
delay between requests.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from typing import Any

import cloudscraper

API_TEMPLATE = "https://api2.moxfield.com/v1/trade-binders/{binder_id}"
PAGE_SIZE = 100
PACING_SECONDS = 0.4
REQUEST_TIMEOUT = 30

FINISH_TO_FOIL = {
    "nonFoil": "",
    "foil": "foil",
    "etched": "etched",
}

CONDITION_TO_CSV = {
    "nearMint": "NM",
    "lightlyPlayed": "LP",
    "moderatelyPlayed": "MP",
    "heavilyPlayed": "HP",
    "damaged": "DMG",
}

CSV_COLUMNS = [
    "Count",
    "Tradelist Count",
    "Name",
    "Edition",
    "Condition",
    "Language",
    "Foil",
    "Tags",
    "Last Modified",
    "Collector Number",
    "Alter",
    "Proxy",
    "Purchase Price",
]


def make_scraper(binder_id: str) -> cloudscraper.CloudScraper:
    s = cloudscraper.create_scraper(
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


def fetch_page(scraper: cloudscraper.CloudScraper, binder_id: str, page: int) -> dict[str, Any]:
    r = scraper.get(
        API_TEMPLATE.format(binder_id=binder_id),
        params={"pageNumber": page, "pageSize": PAGE_SIZE},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def entry_to_row(entry: dict[str, Any]) -> dict[str, str]:
    card = entry.get("card") or {}
    finish = entry.get("finish", "nonFoil")
    foil = FINISH_TO_FOIL.get(finish, "")

    last_modified = entry.get("lastUpdatedAtUtc") or entry.get("createdAtUtc") or ""
    if last_modified.endswith("Z"):
        last_modified = last_modified.replace("T", " ").rstrip("Z")

    language_name = (entry.get("language") or {}).get("name", "English")
    condition = CONDITION_TO_CSV.get(entry.get("condition", ""), "NM")

    return {
        "Count": str(entry.get("quantity", 0)),
        "Tradelist Count": "0",
        "Name": card.get("name", ""),
        "Edition": card.get("set", ""),
        "Condition": condition,
        "Language": language_name,
        "Foil": foil,
        "Tags": "",
        "Last Modified": last_modified,
        "Collector Number": str(card.get("cn", "")),
        "Alter": "True" if entry.get("isAlter") else "False",
        "Proxy": "True" if entry.get("isProxy") else "False",
        "Purchase Price": str(entry.get("purchasePrice") or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a Moxfield binder as CSV.")
    ap.add_argument(
        "binder_id",
        help="Binder public ID (last path segment of /binders/<id>)",
    )
    ap.add_argument("output_csv", help="Path to write CSV")
    ap.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Optional cap on pages fetched (useful for smoke tests)",
    )
    args = ap.parse_args()

    scraper = make_scraper(args.binder_id)

    print("Fetching page 1 to discover total pages...", file=sys.stderr)
    first = fetch_page(scraper, args.binder_id, 1)
    binder_meta = first.get("tradeBinder") or {}
    total_pages = int(first.get("totalPages") or 0)
    total_results = int(first.get("totalResults") or 0)
    print(
        f"Binder: {binder_meta.get('name', '?')!r} "
        f"({total_results} entries across {total_pages} pages)",
        file=sys.stderr,
    )
    if args.limit_pages is not None:
        total_pages = min(total_pages, args.limit_pages)

    rows: list[dict[str, str]] = [entry_to_row(e) for e in first.get("data", [])]
    for page in range(2, total_pages + 1):
        time.sleep(PACING_SECONDS)
        try:
            payload = fetch_page(scraper, args.binder_id, page)
        except Exception as exc:
            print(f"\n  ERROR on page {page}: {exc}", file=sys.stderr)
            print("  Aborting; partial CSV will not be written.", file=sys.stderr)
            return 2
        rows.extend(entry_to_row(e) for e in payload.get("data", []))
        print(
            f"\r  page {page}/{total_pages} ({len(rows)} rows so far)",
            end="",
            file=sys.stderr,
            flush=True,
        )
    print("", file=sys.stderr)

    with open(args.output_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output_csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
