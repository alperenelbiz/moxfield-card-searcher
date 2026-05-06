import argparse
import sys
from pathlib import Path

from moxfield_compare.collection import Collection
from moxfield_compare.matcher import match
from moxfield_compare.models import MatchResult, MatchTier, WantEntry
from moxfield_compare.parser import parse_list

_TIER_FILENAMES: dict[MatchTier, str] = {
    MatchTier.HIT_WITH_SET: "hits-with-set.txt",
    MatchTier.PARTIAL_HIT_WITH_SET: "partial-hits-with-set.txt",
    MatchTier.HIT: "hits.txt",
    MatchTier.PARTIAL_HIT: "partial-hits.txt",
    MatchTier.NON_HIT: "non-hits.txt",
}


def _format_want(want: WantEntry) -> str:
    parts: list[str] = [str(want.qty), want.display_name]
    if want.set and want.cn:
        parts.append(f"({want.set}) {want.cn}")
    line = " ".join(parts)
    if want.foil_only:
        line = f"{line} *F*"
    return line


def _annotation(result: MatchResult) -> str:
    want = result.want
    has_set = want.set is not None and want.cn is not None
    pieces: list[str] = []
    match result.tier:
        case MatchTier.HIT_WITH_SET | MatchTier.NON_HIT:
            pass
        case MatchTier.PARTIAL_HIT_WITH_SET:
            need = want.qty - result.total_count
            pieces.append(
                f"owned this printing: {result.specific_count}, "
                f"total: {result.total_count} (need {need} more)"
            )
        case MatchTier.HIT:
            if has_set:
                pieces.append(
                    f"owned this printing: {result.specific_count}, total: {result.total_count}"
                )
            else:
                pieces.append(f"total owned: {result.total_count}")
        case MatchTier.PARTIAL_HIT:
            need = want.qty - result.total_count
            pieces.append(f"total owned: {result.total_count} (need {need} more)")
    if result.also_has_foil > 0:
        pieces.append(f"also has foil: {result.also_has_foil}")
    return f"  # {'; '.join(pieces)}" if pieces else ""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="moxfield-compare",
        description="Compare a card list against a Moxfield collection CSV.",
    )
    p.add_argument("list_path", type=Path)
    p.add_argument("collection_path", type=Path)
    p.add_argument("--out-dir", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out_dir: Path = args.out_dir or args.list_path.parent

    try:
        wants = parse_list(args.list_path)
        collection = Collection.load(args.collection_path)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    buckets: dict[MatchTier, list[str]] = {t: [] for t in MatchTier}
    counts: dict[MatchTier, int] = {t: 0 for t in MatchTier}

    for want in wants:
        result = match(want, collection)
        line = _format_want(want) + _annotation(result)
        buckets[result.tier].append(line)
        counts[result.tier] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for tier, fname in _TIER_FILENAMES.items():
        target = out_dir / fname
        target.write_text(
            "\n".join(buckets[tier]) + ("\n" if buckets[tier] else ""),
            encoding="utf-8",
        )
        written.append(target)

    width = max(len(t.name.lower()) for t in MatchTier)
    for t in MatchTier:
        print(f"{t.name.lower():<{width}}: {counts[t]:>4}")
    print()
    print("Wrote:")
    for p in written:
        print(f"  {p}")

    return 0
