import json
import logging

from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)


class _SSEManager:
    """Redis pub/sub-backed SSE manager.

    Each SSE connection subscribes to a per-user Redis channel (sse:{user_id}).
    publish() broadcasts to all of that user's connected devices across all
    gunicorn workers.

    publish() never raises — if Redis is unavailable the event is dropped and
    a warning is logged, so callers (billing webhooks etc.) don't crash.
    """

    def subscribe(self, user_id: str):
        """Return a Redis PubSub subscribed to this user's SSE channel."""
        ps = get_redis().pubsub(ignore_subscribe_messages=True)
        ps.subscribe(f'sse:{user_id}')
        return ps

    def unsubscribe(self, ps) -> None:
        try:
            ps.unsubscribe()
            ps.close()
        except Exception:
            pass

    def publish(self, user_id: str, event: str, data: dict) -> None:
        payload = json.dumps({'event': event, 'data': json.dumps(data)})
        try:
            get_redis().publish(f'sse:{user_id}', payload)
        except Exception:
            logger.warning(
                'sse_manager.publish: redis unavailable, event dropped',
                extra={'user_id': user_id, 'event': event},
            )

    def get_message(self, ps, timeout: float = 25.0) -> dict | None:
        """Return parsed {'event': str, 'data': str} or None on timeout."""
        msg = ps.get_message(timeout=timeout)
        if msg is None:
            return None
        try:
            return json.loads(msg['data'])
        except Exception:
            return None


sse_manager = _SSEManager()
