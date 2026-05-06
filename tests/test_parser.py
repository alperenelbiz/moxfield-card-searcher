from pathlib import Path

import pytest

from moxfield_compare.parser import parse_list


def write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "list.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_parses_quantity_and_name(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt\n")
    entries = parse_list(p)
    assert len(entries) == 1
    e = entries[0]
    assert e.qty == 4
    assert e.name == "lightning bolt"
    assert e.set is None
    assert e.cn is None
    assert e.foil_only is False


def test_quantity_defaults_to_one(tmp_path: Path) -> None:
    p = write(tmp_path, "Lightning Bolt\n")
    entries = parse_list(p)
    assert len(entries) == 1
    assert entries[0].qty == 1


def test_name_is_lowercased_and_nfc_normalised(tmp_path: Path) -> None:
    # "Lim-Dûl's Vault" — Dûl uses U+00FB (already NFC); ensure it survives.
    p = write(tmp_path, "1 Lim-Dûl's Vault\n")
    entries = parse_list(p)
    assert entries[0].name == "lim-dûl's vault"


def test_strips_surrounding_whitespace(tmp_path: Path) -> None:
    p = write(tmp_path, "  4   Lightning  Bolt  \n")
    entries = parse_list(p)
    assert entries[0].name == "lightning bolt"  # collapsed
    assert entries[0].qty == 4


def test_parses_set_and_collector_number(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt (M21) 162\n")
    e = parse_list(p)[0]
    assert e.qty == 4
    assert e.name == "lightning bolt"
    assert e.set == "m21"
    assert e.cn == "162"


def test_collector_number_can_have_suffix(tmp_path: Path) -> None:
    p = write(tmp_path, "1 Goblin Guide (2X2) 117★\n")
    e = parse_list(p)[0]
    assert e.set == "2x2"
    assert e.cn == "117★"


def test_set_without_collector_number_is_rejected(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt (M21)\n")
    with pytest.raises(ValueError, match="set code without collector number"):
        parse_list(p)


def test_parses_foil_marker(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt *F*\n")
    e = parse_list(p)[0]
    assert e.foil_only is True
    assert e.name == "lightning bolt"


def test_foil_marker_with_set_and_cn(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt (M21) 162 *F*\n")
    e = parse_list(p)[0]
    assert e.foil_only is True
    assert e.set == "m21"
    assert e.cn == "162"


def test_skips_comments_and_blanks(tmp_path: Path) -> None:
    content = "# Burn deck\n\n4 Lightning Bolt\n   \n# end\n2 Goblin Guide\n"
    p = write(tmp_path, content)
    entries = parse_list(p)
    assert len(entries) == 2
    assert entries[0].name == "lightning bolt"
    assert entries[1].name == "goblin guide"


def test_aggregates_duplicate_lines(tmp_path: Path) -> None:
    p = write(tmp_path, "4 Lightning Bolt\n2 Lightning Bolt\n")
    entries = parse_list(p)
    assert len(entries) == 1
    assert entries[0].qty == 6


def test_aggregation_is_case_insensitive(tmp_path: Path) -> None:
    p = write(tmp_path, "1 Lightning Bolt\n1 lightning bolt\n")
    entries = parse_list(p)
    assert len(entries) == 1
    assert entries[0].qty == 2


def test_different_printings_stay_separate(tmp_path: Path) -> None:
    content = "1 Lightning Bolt\n1 Lightning Bolt (M21) 162\n1 Lightning Bolt (M21) 162 *F*\n"
    p = write(tmp_path, content)
    entries = parse_list(p)
    assert len(entries) == 3
    keys = {(e.set, e.cn, e.foil_only) for e in entries}
    assert keys == {(None, None, False), ("m21", "162", False), ("m21", "162", True)}


def test_aggregation_preserves_first_seen_order(tmp_path: Path) -> None:
    p = write(tmp_path, "1 Goblin Guide\n1 Lightning Bolt\n1 Goblin Guide\n")
    entries = parse_list(p)
    assert [e.name for e in entries] == ["goblin guide", "lightning bolt"]


def test_display_name_preserves_original_casing(tmp_path: Path) -> None:
    p = write(tmp_path, "1 Lim-Dûl's Vault\n4 Lightning Bolt\n")
    entries = parse_list(p)
    assert entries[0].display_name == "Lim-Dûl's Vault"
    assert entries[0].name == "lim-dûl's vault"
    assert entries[1].display_name == "Lightning Bolt"


def test_display_name_uses_first_seen_casing_after_aggregation(tmp_path: Path) -> None:
    p = write(tmp_path, "1 Lightning Bolt\n1 LIGHTNING bolt\n")
    entries = parse_list(p)
    assert len(entries) == 1
    assert entries[0].qty == 2
    assert entries[0].display_name == "Lightning Bolt"  # first-seen casing wins
