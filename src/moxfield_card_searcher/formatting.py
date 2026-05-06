"""Shared formatters that turn WantEntry / MatchResult into display strings.

Both the CLI (writing tier-bucketed text files) and the web UI (rendering
HTMX templates) use these. Keep the public functions purely text-shaping —
no I/O, no template-engine knowledge."""

from __future__ import annotations

from moxfield_card_searcher.domain import MatchResult, MatchTier, WantEntry

_TIER_MARKERS: dict[MatchTier, str] = {
    MatchTier.HIT_WITH_SET: "★",
    MatchTier.PARTIAL_HIT_WITH_SET: "★⚠",
    MatchTier.HIT: "○",
    MatchTier.PARTIAL_HIT: "○⚠",
    MatchTier.NON_HIT: "",
}


def marker_for(tier: MatchTier) -> str:
    return _TIER_MARKERS[tier]


def format_want_line(w: WantEntry) -> str:
    """Reconstruct a want-list line in the same shape `parse_list` accepts."""
    parts = [str(w.qty), w.display_name]
    if w.set and w.cn:
        parts.append(f"({w.set}) {w.cn}")
    line = " ".join(parts)
    if w.foil_only:
        line = f"{line} *F*"
    return line


def annotation_for(r: MatchResult) -> str:
    """Owned-quantity hint suffix for a match result. Empty when nothing useful
    can be said (HIT_WITH_SET with no foil overflow, NON_HIT)."""
    has_set = r.want.set is not None and r.want.cn is not None
    parts: list[str] = []
    if r.tier is MatchTier.PARTIAL_HIT_WITH_SET:
        parts.append(
            f"owned this printing: {r.specific_count}, "
            f"total: {r.total_count} (need {r.want.qty - r.total_count} more)"
        )
    elif r.tier is MatchTier.HIT and has_set:
        parts.append(f"owned this printing: {r.specific_count}, total: {r.total_count}")
    elif r.tier is MatchTier.HIT:
        parts.append(f"total owned: {r.total_count}")
    elif r.tier is MatchTier.PARTIAL_HIT:
        parts.append(f"total owned: {r.total_count} (need {r.want.qty - r.total_count} more)")
    if r.also_has_foil > 0:
        parts.append(f"also has foil: {r.also_has_foil}")
    return "; ".join(parts)
