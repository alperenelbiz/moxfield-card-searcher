from moxfield_card_searcher.collection import Collection
from moxfield_card_searcher.domain import (
    FoilKind,
    MatchResult,
    MatchTier,
    WantEntry,
)


def match(want: WantEntry, collection: Collection) -> MatchResult:
    raw_entries = collection.lookup(want.name)

    if not raw_entries:
        return MatchResult(
            want=want,
            tier=MatchTier.NON_HIT,
            specific_count=0,
            total_count=0,
            also_has_foil=0,
        )

    if want.foil_only:
        filtered = [e for e in raw_entries if e.foil is FoilKind.FOIL]
        also_has_foil = 0
    else:
        filtered = list(raw_entries)
        also_has_foil = sum(e.count for e in raw_entries if e.foil is FoilKind.FOIL)

    if not filtered:
        return MatchResult(
            want=want,
            tier=MatchTier.NON_HIT,
            specific_count=0,
            total_count=0,
            also_has_foil=0,
        )

    has_specific_request = want.set is not None and want.cn is not None
    specific_count = (
        sum(e.count for e in filtered if e.edition == want.set and e.collector_number == want.cn)
        if has_specific_request
        else 0
    )
    total_count = sum(e.count for e in filtered)

    if has_specific_request and specific_count >= want.qty:
        tier = MatchTier.HIT_WITH_SET
    elif total_count >= want.qty:
        tier = MatchTier.HIT
    elif has_specific_request and specific_count > 0:
        tier = MatchTier.PARTIAL_HIT_WITH_SET
    elif total_count > 0:
        tier = MatchTier.PARTIAL_HIT
    else:
        tier = MatchTier.NON_HIT

    return MatchResult(
        want=want,
        tier=tier,
        specific_count=specific_count,
        total_count=total_count,
        also_has_foil=also_has_foil,
    )
