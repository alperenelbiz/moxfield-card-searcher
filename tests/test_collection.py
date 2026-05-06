from pathlib import Path

import pytest

from moxfield_compare.collection import Collection
from moxfield_compare.models import FoilKind
from moxfield_compare.web.db import CardRow

FIXTURE = Path(__file__).parent / "fixtures" / "sample-collection.csv"


def test_lookup_returns_all_printings_of_a_name() -> None:
    c = Collection.load(FIXTURE)
    entries = c.lookup("Lightning Bolt")
    assert len(entries) == 3
    editions = {e.edition for e in entries}
    assert editions == {"m21", "2x2", "sld"}


def test_lookup_is_case_insensitive() -> None:
    c = Collection.load(FIXTURE)
    assert c.lookup("LIGHTNING BOLT") == c.lookup("lightning bolt")


def test_edition_is_lowercased() -> None:
    c = Collection.load(FIXTURE)
    for e in c.lookup("Lightning Bolt"):
        assert e.edition == e.edition.lower()


def test_foil_column_parses_correctly() -> None:
    c = Collection.load(FIXTURE)
    bolts = {(e.edition, e.foil) for e in c.lookup("Lightning Bolt")}
    assert (("m21", FoilKind.NONE)) in bolts
    assert (("sld", FoilKind.FOIL)) in bolts


def test_etched_is_distinct_foil_kind() -> None:
    c = Collection.load(FIXTURE)
    sols = c.lookup("Sol Ring")
    foils = {e.foil for e in sols}
    assert foils == {FoilKind.NONE, FoilKind.ETCHED}


def test_diacritic_names_match() -> None:
    c = Collection.load(FIXTURE)
    assert len(c.lookup("Lim-Dûl's Vault")) == 1


def test_unknown_name_returns_empty_list() -> None:
    c = Collection.load(FIXTURE)
    assert c.lookup("Black Lotus") == []


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        Collection.load(Path("/no/such/file.csv"))


def test_from_db_rows_builds_lookup_index() -> None:
    rows = [
        CardRow(
            name="Lightning Bolt",
            name_lower="lightning bolt",
            edition="m21",
            collector_number="162",
            count=2,
            foil="",
            scryfall_id=None,
        ),
        CardRow(
            name="Lightning Bolt",
            name_lower="lightning bolt",
            edition="2x2",
            collector_number="117",
            count=5,
            foil="",
            scryfall_id=None,
        ),
        CardRow(
            name="Sol Ring",
            name_lower="sol ring",
            edition="cmm",
            collector_number="410",
            count=1,
            foil="etched",
            scryfall_id=None,
        ),
    ]
    c = Collection.from_db_rows(rows)
    bolts = c.lookup("lightning bolt")
    assert len(bolts) == 2
    editions = {e.edition for e in bolts}
    assert editions == {"m21", "2x2"}
    sols = c.lookup("Sol Ring")
    assert len(sols) == 1
    assert sols[0].foil is FoilKind.ETCHED


def test_from_db_rows_handles_empty_input() -> None:
    c = Collection.from_db_rows([])
    assert c.lookup("anything") == []
