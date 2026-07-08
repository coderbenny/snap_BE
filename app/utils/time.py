from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (MySQL DATETIME compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def from_unix_ms(ts_ms: int) -> datetime:
    """Convert a Unix millisecond timestamp to a naive UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def to_unix_ms(dt: datetime) -> int:
    """Convert a naive UTC datetime to a Unix millisecond timestamp."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
