from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (MySQL DATETIME compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
