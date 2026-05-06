from moxfield_card_searcher.collection import Collection
from moxfield_card_searcher.domain import (
    CollectionEntry,
    FoilKind,
    MatchTier,
    WantEntry,
)
from moxfield_card_searcher.matcher import match


def make_collection(entries: list[CollectionEntry]) -> Collection:
    by_name: dict[str, list[CollectionEntry]] = {}
    for e in entries:
        by_name.setdefault(e.name.lower(), []).append(e)
    return Collection(by_name=by_name)


# ---- HIT_WITH_SET ----


def test_hit_with_set_when_specific_printing_has_enough() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 4, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT_WITH_SET
    assert result.specific_count == 4
    assert result.total_count == 4


# ---- HIT (best achievable beats partial-with-set) ----


def test_hit_when_specific_insufficient_but_total_enough() -> None:
    """Worked example from spec §4."""
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 2, FoilKind.NONE),
            CollectionEntry("Lightning Bolt", "2x2", "117", 5, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT
    assert result.specific_count == 2
    assert result.total_count == 7


def test_hit_when_no_set_specified_and_total_enough() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "2x2", "117", 5, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT
    assert result.specific_count == 0
    assert result.total_count == 5


# ---- PARTIAL_HIT_WITH_SET ----


def test_partial_hit_with_set_when_specific_partial_and_no_other_printings() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 2, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.PARTIAL_HIT_WITH_SET
    assert result.specific_count == 2
    assert result.total_count == 2


def test_partial_hit_with_set_when_total_still_insufficient() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 2, FoilKind.NONE),
            CollectionEntry("Lightning Bolt", "2x2", "117", 1, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=6,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.PARTIAL_HIT_WITH_SET
    assert result.specific_count == 2
    assert result.total_count == 3


# ---- PARTIAL_HIT ----


def test_partial_hit_when_no_set_match_and_total_insufficient() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "2x2", "117", 2, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.PARTIAL_HIT
    assert result.specific_count == 0
    assert result.total_count == 2


def test_partial_hit_when_no_set_specified_and_total_insufficient() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "2x2", "117", 2, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.PARTIAL_HIT
    assert result.total_count == 2


# ---- NON_HIT ----


def test_non_hit_when_name_absent() -> None:
    coll = make_collection([])
    want = WantEntry(
        qty=1,
        name="black lotus",
        display_name="Black Lotus",
        set=None,
        cn=None,
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.NON_HIT
    assert result.total_count == 0


def test_non_hit_when_foil_only_and_no_foil_printings() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 4, FoilKind.NONE),
        ]
    )
    want = WantEntry(
        qty=1,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=True,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.NON_HIT


# ---- Foil filter and also_has_foil annotation ----


def test_foil_only_request_matches_only_foil_entries() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 4, FoilKind.NONE),
            CollectionEntry("Lightning Bolt", "sld", "42", 2, FoilKind.FOIL),
        ]
    )
    want = WantEntry(
        qty=2,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=True,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT
    assert result.total_count == 2  # only foils counted
    assert result.also_has_foil == 0  # not annotated for foil-only


def test_also_has_foil_set_for_non_foil_request() -> None:
    coll = make_collection(
        [
            CollectionEntry("Lightning Bolt", "m21", "162", 4, FoilKind.NONE),
            CollectionEntry("Lightning Bolt", "sld", "42", 2, FoilKind.FOIL),
        ]
    )
    want = WantEntry(
        qty=2,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT
    assert result.total_count == 6  # all printings count
    assert result.also_has_foil == 2


def test_etched_does_not_count_as_foil_for_filter() -> None:
    """Foil-only request matches FOIL but not ETCHED."""
    coll = make_collection(
        [
            CollectionEntry("Sol Ring", "cmm", "410", 2, FoilKind.ETCHED),
        ]
    )
    want = WantEntry(
        qty=1,
        name="sol ring",
        display_name="Sol Ring",
        set=None,
        cn=None,
        foil_only=True,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.NON_HIT


def test_also_has_foil_does_not_count_etched() -> None:
    coll = make_collection(
        [
            CollectionEntry("Sol Ring", "cmm", "410", 1, FoilKind.NONE),
            CollectionEntry("Sol Ring", "cmm", "410", 2, FoilKind.ETCHED),
        ]
    )
    want = WantEntry(
        qty=1,
        name="sol ring",
        display_name="Sol Ring",
        set=None,
        cn=None,
        foil_only=False,
    )
    result = match(want, coll)
    assert result.tier is MatchTier.HIT
    assert result.also_has_foil == 0  # etched is not foil
