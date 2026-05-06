"""Fetch a public Moxfield trade binder and emit a CSV in the format
moxfield-card-searcher's CLI consumes (Moxfield collection export shape).

Run after `uv sync --group ui`:

    uv run scripts/fetch_binder.py <binder-public-id> <output.csv> [--limit-pages N]

Where <binder-public-id> is the trailing path segment of a binder URL like
https://moxfield.com/binders/YR6dKVcP8UK9Hg2qnSOsbA — the ID is "YR6...bA".

This script delegates the API + Cloudflare handshake to
`moxfield_card_searcher.binder_fetcher`; the only script-specific code here is the
mapping from a Moxfield API entry to a Moxfield CSV row.
"""

from __future__ import annotations

import argparse
import csv
import sys
from typing import Any

from moxfield_card_searcher.binder_fetcher import (
    extract_binder_id,
    fetch_pages,
    make_scraper,
)

CONDITION_TO_CSV = {
    "nearMint": "NM",
    "lightlyPlayed": "LP",
    "moderatelyPlayed": "MP",
    "heavilyPlayed": "HP",
    "damaged": "DMG",
}

FINISH_TO_CSV_FOIL = {
    "nonFoil": "",
    "foil": "foil",
    "etched": "etched",
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


def entry_to_csv_row(entry: dict[str, Any]) -> dict[str, str]:
    """Map one Moxfield API entry to a Moxfield collection CSV row."""
    card = entry.get("card") or {}
    finish = entry.get("finish", "nonFoil")
    foil = FINISH_TO_CSV_FOIL.get(finish, "")

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
        help="Binder public ID or full URL (https://moxfield.com/binders/<id>)",
    )
    ap.add_argument("output_csv", help="Path to write CSV")
    ap.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Optional cap on pages fetched (useful for smoke tests)",
    )
    args = ap.parse_args()

    binder_id = extract_binder_id(args.binder_id)
    scraper = make_scraper(binder_id)

    print("Fetching page 1 to discover total pages...", file=sys.stderr)
    rows: list[dict[str, str]] = []
    binder_name = ""
    pages_total = 0
    try:
        for page in fetch_pages(scraper, binder_id):
            if args.limit_pages is not None and page.page_number > args.limit_pages:
                break
            if page.page_number == 1:
                binder_name = page.binder_name
                pages_total = page.total_pages
                if args.limit_pages is not None:
                    pages_total = min(pages_total, args.limit_pages)
                print(
                    f"Binder: {binder_name!r} ({pages_total} pages to fetch)",
                    file=sys.stderr,
                )
            rows.extend(entry_to_csv_row(e) for e in page.entries)
            print(
                f"\r  page {page.page_number}/{pages_total} ({len(rows)} rows so far)",
                end="",
                file=sys.stderr,
                flush=True,
            )
    except Exception as exc:
        print(f"\n  ERROR: {exc}", file=sys.stderr)
        print("  Aborting; partial CSV will not be written.", file=sys.stderr)
        return 2
    print("", file=sys.stderr)

    with open(args.output_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output_csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
