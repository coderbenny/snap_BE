import json
import queue
import threading


class _SSEManager:
    """In-process pub/sub for Server-Sent Events.

    Works with a single gunicorn worker (--workers 1 --threads N) or the
    Werkzeug dev server. For multi-worker deployments, replace the Queue
    storage with Redis pub/sub channels.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: dict[str, list[queue.Queue]] = {}

    def subscribe(self, user_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=20)
        with self._lock:
            self._queues.setdefault(user_id, []).append(q)
        return q

    def unsubscribe(self, user_id: str, q: queue.Queue) -> None:
        with self._lock:
            qs = self._queues.get(user_id, [])
            try:
                qs.remove(q)
            except ValueError:
                pass

    def publish(self, user_id: str, event: str, data: dict) -> None:
        payload = {'event': event, 'data': json.dumps(data)}
        with self._lock:
            qs = list(self._queues.get(user_id, []))
        for q in qs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass  # client fell behind — drop the message


sse_manager = _SSEManager()
