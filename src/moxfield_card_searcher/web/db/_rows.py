"""Row-shaped value objects for the three SQLite tables. Frozen dataclasses
so they can flow across module boundaries without accidental mutation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BinderRow:
    id: int
    moxfield_id: str
    name: str
    fetched_at: str
    entry_count: int
    total_cards: int
    created_by_username: str | None


@dataclass(frozen=True)
class CardRow:
    name: str
    name_lower: str
    edition: str
    collector_number: str
    count: int
    foil: str
    scryfall_id: str | None


@dataclass(frozen=True)
class JobRow:
    id: int
    moxfield_id: str
    status: str
    progress_pct: int
    pages_done: int
    pages_total: int
    error_message: str | None
    refresh_of_binder_id: int | None
    created_at: str
    updated_at: str
