from moxfield_card_searcher.domain import MatchResult, MatchTier, WantEntry
from moxfield_card_searcher.formatting import narrative_status_for


def _want(qty: int = 4, name: str = "lightning bolt", set_: str | None = None,
          cn: str | None = None, foil_only: bool = False) -> WantEntry:
    return WantEntry(
        qty=qty, name=name, display_name=name.title(),
        set=set_, cn=cn, foil_only=foil_only,
    )


def test_hit_with_set() -> None:
    w = _want(qty=4, set_="m21", cn="162")
    r = MatchResult(want=w, tier=MatchTier.HIT_WITH_SET,
                    specific_count=4, total_count=6, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == "All 4 owned"
    assert "M21" in detail
    assert "162" in detail
    assert "exact printing" in detail


def test_hit_with_set_requested_but_other_printing() -> None:
    # User asked for (M21) 162 but we only have other printings.
    w = _want(qty=3, set_="m21", cn="162")
    r = MatchResult(want=w, tier=MatchTier.HIT,
                    specific_count=0, total_count=3, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == "All 3 owned"
    assert "other printing" in detail


def test_hit_no_set_requested() -> None:
    w = _want(qty=2)  # no set/cn
    r = MatchResult(want=w, tier=MatchTier.HIT,
                    specific_count=0, total_count=2, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == "All 2 owned"
    assert "total owned: 2" in detail


def test_partial_hit_with_set() -> None:
    w = _want(qty=4, set_="cmr", cn="263")
    r = MatchResult(want=w, tier=MatchTier.PARTIAL_HIT_WITH_SET,
                    specific_count=1, total_count=2, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == "Need 2 more"
    assert "CMR" in detail
    assert "263" in detail
    assert "have 1 of 4" in detail
    assert "exact printing" in detail


def test_partial_hit_other_printing() -> None:
    w = _want(qty=4, set_="cmr", cn="263")
    r = MatchResult(want=w, tier=MatchTier.PARTIAL_HIT,
                    specific_count=0, total_count=2, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == "Need 2 more"
    assert "other printing" in detail
    assert "have 2 of 4" in detail


def test_foil_overflow_appends_to_detail() -> None:
    w = _want(qty=4, set_="m21", cn="162")
    r = MatchResult(want=w, tier=MatchTier.HIT_WITH_SET,
                    specific_count=4, total_count=6, also_has_foil=2)
    _, detail = narrative_status_for(r)
    assert "also has 2 foil" in detail


def test_non_hit_returns_empty_strings() -> None:
    w = _want(qty=4)
    r = MatchResult(want=w, tier=MatchTier.NON_HIT,
                    specific_count=0, total_count=0, also_has_foil=0)
    headline, detail = narrative_status_for(r)
    assert headline == ""
    assert detail == ""


def test_foil_overflow_on_partial_hit() -> None:
    w = _want(qty=4, set_="cmr", cn="263")
    r = MatchResult(want=w, tier=MatchTier.PARTIAL_HIT_WITH_SET,
                    specific_count=1, total_count=2, also_has_foil=3)
    headline, detail = narrative_status_for(r)
    assert headline == "Need 2 more"
    assert "have 1 of 4 (exact printing)" in detail
    assert "also has 3 foil" in detail
