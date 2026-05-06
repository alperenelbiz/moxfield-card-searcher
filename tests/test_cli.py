import shutil
from pathlib import Path

import pytest

from moxfield_card_searcher.cli import main

FIXTURE_LIST = Path(__file__).parent / "fixtures" / "sample-list.txt"
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample-collection.csv"


def test_end_to_end_writes_five_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    list_path = tmp_path / "list.txt"
    csv_path = tmp_path / "collection.csv"
    shutil.copy(FIXTURE_LIST, list_path)
    shutil.copy(FIXTURE_CSV, csv_path)

    exit_code = main([str(list_path), str(csv_path)])
    assert exit_code == 0

    for fname in (
        "hits-with-set.txt",
        "partial-hits-with-set.txt",
        "hits.txt",
        "partial-hits.txt",
        "non-hits.txt",
    ):
        assert (tmp_path / fname).exists(), f"Missing {fname}"

    # 4 Lightning Bolt (m21) 162: collection has 2 m21/162 + 5 2x2/117 (total 7) → HIT
    # (with also-has-foil annotation for 1 foil sld)
    hits = (tmp_path / "hits.txt").read_text(encoding="utf-8")
    assert "Lightning Bolt" in hits
    assert "also has foil: 1" in hits

    # 2 Lightning Bolt (m21) 162 *F*: only 1 foil printing → PARTIAL_HIT (foil filter)
    partial_hits = (tmp_path / "partial-hits.txt").read_text(encoding="utf-8")
    assert "*F*" in partial_hits

    # 4 Goblin Guide: collection has only 3 → PARTIAL_HIT
    assert "Goblin Guide" in partial_hits

    # 1 Sol Ring (cmm) 410: 1 non-foil exists → HIT_WITH_SET
    hits_with_set = (tmp_path / "hits-with-set.txt").read_text(encoding="utf-8")
    assert "Sol Ring" in hits_with_set

    # 1 Black Lotus: not in collection → NON_HIT
    non_hits = (tmp_path / "non-hits.txt").read_text(encoding="utf-8")
    assert "Black Lotus" in non_hits

    # Console summary mentions tier counts
    out = capsys.readouterr().out
    assert "hit_with_set" in out
    assert "non_hit" in out


def test_out_dir_flag_redirects_output(tmp_path: Path) -> None:
    list_path = tmp_path / "list.txt"
    csv_path = tmp_path / "collection.csv"
    out_dir = tmp_path / "results"
    out_dir.mkdir()
    shutil.copy(FIXTURE_LIST, list_path)
    shutil.copy(FIXTURE_CSV, csv_path)

    exit_code = main([str(list_path), str(csv_path), "--out-dir", str(out_dir)])
    assert exit_code == 0
    assert (out_dir / "non-hits.txt").exists()
    assert not (tmp_path / "non-hits.txt").exists()


def test_parse_error_returns_exit_code_2(tmp_path: Path) -> None:
    list_path = tmp_path / "list.txt"
    csv_path = tmp_path / "collection.csv"
    list_path.write_text("4 Lightning Bolt (m21)\n", encoding="utf-8")  # missing cn
    shutil.copy(FIXTURE_CSV, csv_path)

    exit_code = main([str(list_path), str(csv_path)])
    assert exit_code == 2
