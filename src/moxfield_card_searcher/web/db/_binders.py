"""CRUD for the `binders` and `cards` tables. Cards live with their binder
because they're cascade-deleted together and always queried by binder_id."""

from __future__ import annotations

import sqlite3

from moxfield_card_searcher.web.db._rows import BinderRow, CardRow


def create_binder(
    conn: sqlite3.Connection,
    *,
    moxfield_id: str,
    name: str,
    fetched_at: str,
    entry_count: int,
    total_cards: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO binders(moxfield_id, name, fetched_at, entry_count, total_cards) "
        "VALUES (?, ?, ?, ?, ?)",
        (moxfield_id, name, fetched_at, entry_count, total_cards),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def list_binders(conn: sqlite3.Connection) -> list[BinderRow]:
    cur = conn.execute(
        "SELECT id, moxfield_id, name, fetched_at, entry_count, total_cards "
        "FROM binders ORDER BY fetched_at DESC"
    )
    return [
        BinderRow(
            id=r["id"],
            moxfield_id=r["moxfield_id"],
            name=r["name"],
            fetched_at=r["fetched_at"],
            entry_count=r["entry_count"],
            total_cards=r["total_cards"],
        )
        for r in cur.fetchall()
    ]


def delete_binder(conn: sqlite3.Connection, binder_id: int) -> bool:
    cur = conn.execute("DELETE FROM binders WHERE id=?", (binder_id,))
    conn.commit()
    return cur.rowcount > 0


def insert_cards(conn: sqlite3.Connection, binder_id: int, cards: list[CardRow]) -> None:
    conn.executemany(
        "INSERT INTO cards(binder_id, name, name_lower, edition, "
        "collector_number, count, foil, scryfall_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                binder_id,
                c.name,
                c.name_lower,
                c.edition,
                c.collector_number,
                c.count,
                c.foil,
                c.scryfall_id,
            )
            for c in cards
        ],
    )
    conn.commit()


def list_cards(conn: sqlite3.Connection, binder_id: int) -> list[CardRow]:
    cur = conn.execute(
        "SELECT name, name_lower, edition, collector_number, count, foil, scryfall_id "
        "FROM cards WHERE binder_id=? ORDER BY id",
        (binder_id,),
    )
    return [
        CardRow(
            name=r["name"],
            name_lower=r["name_lower"],
            edition=r["edition"],
            collector_number=r["collector_number"],
            count=r["count"],
            foil=r["foil"],
            scryfall_id=r["scryfall_id"],
        )
        for r in cur.fetchall()
    ]
