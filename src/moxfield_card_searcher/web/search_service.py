"""Pure search logic — turn a parsed want-list into a SearchResult shape
the search-results template can render. Lives outside the HTTP layer so
the route handler stays thin (parse the request, call this, render the
response) and so the matching pipeline is independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moxfield_card_searcher.collection import Collection
from moxfield_card_searcher.domain import MatchTier, WantEntry
from moxfield_card_searcher.formatting import (
    annotation_for,
    format_want_line,
    marker_for,
)
from moxfield_card_searcher.matcher import match
from moxfield_card_searcher.web import db


@dataclass(frozen=True)
class BinderGroup:
    binder: db.BinderRow
    results: list[dict[str, Any]]
    found_count: int


@dataclass(frozen=True)
class SearchResult:
    binder_groups: list[BinderGroup]
    missing: list[str]
    total_wants: int


def run_search(db_path: Path, wants: list[WantEntry]) -> SearchResult:
    """Run the want-list against every saved binder and group the results."""
    with db.connect(db_path) as conn:
        binders = db.list_binders(conn)
        per_binder_results: dict[int, list[dict[str, Any]]] = {}
        binder_to_name: dict[int, str] = {}
        for b in binders:
            binder_to_name[b.id] = b.name
            cards = db.list_cards(conn, b.id)
            per_binder_results[b.id] = _match_binder(wants, cards)

    _annotate_cross_binder(per_binder_results, binder_to_name)

    missing_lines = [
        format_want_line(w)
        for w in wants
        if not any(
            any(r["name"] == w.display_name for r in per_binder_results[b.id])
            for b in binders
        )
    ]

    binder_groups = [
        BinderGroup(
            binder=b,
            results=per_binder_results[b.id],
            found_count=len(per_binder_results[b.id]),
        )
        for b in binders
    ]
    return SearchResult(
        binder_groups=binder_groups,
        missing=missing_lines,
        total_wants=len(wants),
    )


def _match_binder(
    wants: list[WantEntry], cards: list[db.CardRow]
) -> list[dict[str, Any]]:
    collection = Collection.from_db_rows(cards)
    scryfall_index: dict[tuple[str, str, str], str | None] = {
        (c.name_lower, c.edition, c.collector_number): c.scryfall_id for c in cards
    }
    results: list[dict[str, Any]] = []
    for w in wants:
        res = match(w, collection)
        if res.tier is MatchTier.NON_HIT:
            continue
        sid: str | None = None
        if w.set and w.cn:
            sid = scryfall_index.get((w.name, w.set, w.cn))
        if sid is None:
            sid = next(
                (sc for (n, _, _), sc in scryfall_index.items() if n == w.name),
                None,
            )
        results.append(
            {
                "tier": res.tier,
                "marker": marker_for(res.tier),
                "name": w.display_name,
                "scryfall_id": sid,
                "annotation": annotation_for(res),
                "also_in": [],
            }
        )
    return results


def _annotate_cross_binder(
    per_binder_results: dict[int, list[dict[str, Any]]],
    binder_to_name: dict[int, str],
) -> None:
    """Fill in the `also_in` list on each result based on which OTHER binders
    contain the same display_name."""
    name_to_binders: dict[str, set[int]] = {}
    for bid, results in per_binder_results.items():
        for r in results:
            name_to_binders.setdefault(r["name"], set()).add(bid)
    for bid, results in per_binder_results.items():
        for r in results:
            others = name_to_binders.get(r["name"], set()) - {bid}
            r["also_in"] = sorted(binder_to_name[oid] for oid in others)
