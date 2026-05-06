from __future__ import annotations

from datetime import UTC, datetime


def iso_now() -> str:
    """ISO 8601 UTC timestamp used as `created_at`/`updated_at` everywhere."""
    return datetime.now(tz=UTC).isoformat()
