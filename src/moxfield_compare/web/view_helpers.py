"""Jinja-bound formatters that turn MatchResult/WantEntry into the strings
the search-results template renders. Kept separate from the route handlers
so the formatting logic is unit-testable in isolation."""

from __future__ import annotations

from moxfield_compare.models import MatchResult, MatchTier, WantEntry


def marker_for(tier: MatchTier) -> str:
    return {
        MatchTier.HIT_WITH_SET: "★",
        MatchTier.PARTIAL_HIT_WITH_SET: "★⚠",
        MatchTier.HIT: "○",
        MatchTier.PARTIAL_HIT: "○⚠",
        MatchTier.NON_HIT: "",
    }[tier]


def annotation_for(r: MatchResult) -> str:
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


def format_want_line(w: WantEntry) -> str:
    """Reconstruct a want-list line for the missing bucket (text-only output)."""
    parts = [str(w.qty), w.display_name]
    if w.set and w.cn:
        parts.append(f"({w.set}) {w.cn}")
    out = " ".join(parts)
    if w.foil_only:
        out = f"{out} *F*"
    return out
