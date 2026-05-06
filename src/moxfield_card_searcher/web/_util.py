from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_DISPLAY_TZ = ZoneInfo("Europe/Istanbul")


def iso_now() -> str:
    """ISO 8601 UTC timestamp used as `created_at`/`updated_at` everywhere."""
    return datetime.now(tz=UTC).isoformat()


def format_local_datetime(iso_timestamp: str) -> str:
    """Convert a UTC ISO 8601 timestamp into a user-readable Istanbul-local
    string like '06 May 2026, 17:11'. Returns the original string on parse
    failure so the UI degrades gracefully instead of raising."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_DISPLAY_TZ).strftime("%d %b %Y, %H:%M")
