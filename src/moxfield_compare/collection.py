import csv
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from moxfield_compare.models import CollectionEntry, FoilKind

if TYPE_CHECKING:
    from moxfield_compare.web.db import CardRow

_FOIL_MAP = {
    "": FoilKind.NONE,
    "foil": FoilKind.FOIL,
    "etched": FoilKind.ETCHED,
}


def _normalise_name_key(raw: str) -> str:
    return unicodedata.normalize("NFC", raw.strip()).lower()


@dataclass
class Collection:
    by_name: dict[str, list[CollectionEntry]]

    @classmethod
    def load(cls, path: Path) -> "Collection":
        index: dict[str, list[CollectionEntry]] = defaultdict(list)
        with Path(path).open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["Name"]
                foil_raw = (row.get("Foil") or "").strip().lower()
                foil = _FOIL_MAP.get(foil_raw, FoilKind.NONE)
                entry = CollectionEntry(
                    name=name,
                    edition=row["Edition"].strip().lower(),
                    collector_number=row["Collector Number"].strip().lower(),
                    count=int(row["Count"]),
                    foil=foil,
                )
                index[_normalise_name_key(name)].append(entry)
        return cls(by_name=dict(index))

    @classmethod
    def from_db_rows(cls, rows: "list[CardRow]") -> "Collection":
        index: dict[str, list[CollectionEntry]] = {}
        for r in rows:
            entry = CollectionEntry(
                name=r.name,
                edition=r.edition,
                collector_number=r.collector_number,
                count=r.count,
                foil=_FOIL_MAP.get(r.foil, FoilKind.NONE),
            )
            index.setdefault(r.name_lower, []).append(entry)
        return cls(by_name=index)

    def lookup(self, name: str) -> list[CollectionEntry]:
        return list(self.by_name.get(_normalise_name_key(name), []))
