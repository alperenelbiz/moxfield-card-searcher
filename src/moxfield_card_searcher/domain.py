from dataclasses import dataclass
from enum import Enum, auto


class MatchTier(Enum):
    HIT_WITH_SET = auto()
    PARTIAL_HIT_WITH_SET = auto()
    HIT = auto()
    PARTIAL_HIT = auto()
    NON_HIT = auto()


class FoilKind(Enum):
    NONE = "none"
    FOIL = "foil"
    ETCHED = "etched"


@dataclass(frozen=True)
class WantEntry:
    qty: int
    name: str  # lowercased, NFC-normalised — used for matching
    display_name: str  # original casing, NFC-normalised, whitespace-collapsed — used for output
    set: str | None  # lowercased
    cn: str | None  # lowercased, kept as string
    foil_only: bool


@dataclass(frozen=True)
class CollectionEntry:
    name: str  # original casing as in CSV
    edition: str  # lowercased
    collector_number: str
    count: int
    foil: FoilKind


@dataclass(frozen=True)
class MatchResult:
    want: WantEntry
    tier: MatchTier
    specific_count: int  # qty owned of the specific (set, cn) printing
    total_count: int  # qty owned across all matched (post-foil-filter) printings
    also_has_foil: int  # foil count for non-foil requests; 0 otherwise
