from moxfield_card_searcher.domain import (
    CollectionEntry,
    FoilKind,
    MatchResult,
    MatchTier,
    WantEntry,
)


def test_match_tier_has_five_values() -> None:
    assert {t.name for t in MatchTier} == {
        "HIT_WITH_SET",
        "PARTIAL_HIT_WITH_SET",
        "HIT",
        "PARTIAL_HIT",
        "NON_HIT",
    }


def test_foil_kind_has_three_values_with_correct_strings() -> None:
    assert {(f.name, f.value) for f in FoilKind} == {
        ("NONE", "none"),
        ("FOIL", "foil"),
        ("ETCHED", "etched"),
    }


def test_want_entry_construction() -> None:
    w = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set="m21",
        cn="162",
        foil_only=False,
    )
    assert w.qty == 4
    assert w.name == "lightning bolt"
    assert w.display_name == "Lightning Bolt"
    assert w.set == "m21"
    assert w.cn == "162"
    assert w.foil_only is False


def test_collection_entry_construction() -> None:
    c = CollectionEntry(
        name="Lightning Bolt",
        edition="m21",
        collector_number="162",
        count=4,
        foil=FoilKind.NONE,
    )
    assert c.count == 4
    assert c.foil is FoilKind.NONE


def test_match_result_carries_tier_and_annotation_data() -> None:
    want = WantEntry(
        qty=4,
        name="lightning bolt",
        display_name="Lightning Bolt",
        set=None,
        cn=None,
        foil_only=False,
    )
    r = MatchResult(
        want=want,
        tier=MatchTier.HIT,
        specific_count=0,
        total_count=7,
        also_has_foil=1,
    )
    assert r.tier is MatchTier.HIT
    assert r.specific_count == 0
    assert r.total_count == 7
    assert r.also_has_foil == 1
