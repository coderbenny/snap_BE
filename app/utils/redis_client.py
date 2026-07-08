import os

import redis

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a lazily-initialised Redis client (one per worker process)."""
    global _client
    if _client is None:
        url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        _client = redis.from_url(url, decode_responses=True)
    return _client
