"""Shared pytest fixtures for the web-UI test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from moxfield_card_searcher.web import db
from moxfield_card_searcher.web._util import iso_now


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    """Two binders pre-populated for search tests:

    - Bulk: Lightning Bolt (m21/162, x4) + Sol Ring (cmm/410, x2)
    - Sell: Goblin Guide (2x2/118, x1)
    """
    db_path = tmp_path / "test.db"
    db.init_schema(db_path)
    with db.connect(db_path) as conn:
        bulk = db.create_binder(
            conn,
            moxfield_id="BULK",
            name="Bulk",
            fetched_at=iso_now(),
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
            fetched_at=iso_now(),
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
    return db_path
