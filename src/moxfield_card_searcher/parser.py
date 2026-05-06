import re
import unicodedata
from pathlib import Path

from moxfield_card_searcher.domain import WantEntry

_WS_RUN = re.compile(r"\s+")
_LINE = re.compile(
    r"^(?P<qty>\d+)?\s*"
    r"(?P<name>.+?)"
    r"(?:\s*\((?P<set>[A-Za-z0-9]+)\)\s+(?P<cn>\S+))?"
    r"(?:\s*\*F\*)?"
    r"\s*$"
)


def _collapse_and_nfc(raw: str) -> str:
    """Trim, collapse whitespace runs, NFC-normalise. Preserves casing.

    Lowercase the result to obtain the matching key used by `WantEntry.name`.
    """
    collapsed = _WS_RUN.sub(" ", raw.strip())
    return unicodedata.normalize("NFC", collapsed)


_NAME_HAS_PARENS = re.compile(r"\([A-Za-z0-9]+\)")
_FOIL_TAIL = re.compile(r"\s*\*F\*\s*$")


def parse_list(path: Path) -> list[WantEntry]:
    return _parse_lines(Path(path).read_text(encoding="utf-8").splitlines())


def parse_list_text(text: str) -> list[WantEntry]:
    """Same as parse_list but accepts the raw text directly. The web UI uses
    this so an uploaded file or a textarea string can both be parsed without
    writing to a temp file first."""
    return _parse_lines(text.splitlines())


def _parse_lines(lines: list[str]) -> list[WantEntry]:
    raw: list[WantEntry] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        foil_only = bool(_FOIL_TAIL.search(line))
        if foil_only:
            line = _FOIL_TAIL.sub("", line)

        m = _LINE.match(line)
        if m is None:
            raise ValueError(f"Cannot parse line: {raw_line!r}")
        qty = int(m["qty"]) if m["qty"] else 1
        display_name = _collapse_and_nfc(m["name"])
        name = display_name.lower()
        set_code = m["set"].lower() if m["set"] else None
        cn = m["cn"].lower() if m["cn"] else None

        if set_code is None and _NAME_HAS_PARENS.search(name):
            raise ValueError(f"Line has a set code without collector number: {raw_line!r}")

        raw.append(
            WantEntry(
                qty=qty,
                name=name,
                display_name=display_name,
                set=set_code,
                cn=cn,
                foil_only=foil_only,
            )
        )

    aggregated_qty: dict[tuple[str, str | None, str | None, bool], int] = {}
    aggregated_display: dict[tuple[str, str | None, str | None, bool], str] = {}
    order: list[tuple[str, str | None, str | None, bool]] = []
    for entry in raw:
        key = (entry.name, entry.set, entry.cn, entry.foil_only)
        if key not in aggregated_qty:
            aggregated_qty[key] = 0
            aggregated_display[key] = entry.display_name
            order.append(key)
        aggregated_qty[key] += entry.qty

    return [
        WantEntry(
            qty=aggregated_qty[k],
            name=k[0],
            display_name=aggregated_display[k],
            set=k[1],
            cn=k[2],
            foil_only=k[3],
        )
        for k in order
    ]
