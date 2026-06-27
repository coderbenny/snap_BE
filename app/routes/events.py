import queue as queue_module

from flask import Blueprint, Response, g

from app.middleware.auth_middleware import require_auth
from app.services.sse_manager import sse_manager

events_bp = Blueprint('events', __name__, url_prefix='/events')


@events_bp.get('')
@require_auth
def stream():
    """Long-lived Server-Sent Events stream for the authenticated user.

    Sends a keepalive comment every 25 s to prevent proxies from closing
    idle connections. The client reconnects automatically on drop.

    Events emitted:
      plan_changed  {"plan": "pro"}   — fired when billing updates plan_tier
    """
    user_id = g.current_user.id
    q = sse_manager.subscribe(user_id)

    def generate():
        yield ': connected\n\n'
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                except queue_module.Empty:
                    yield ': keepalive\n\n'
        finally:
            sse_manager.unsubscribe(user_id, q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   # disable nginx response buffering
            'Connection': 'keep-alive',
        },
    )
