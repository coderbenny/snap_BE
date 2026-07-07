from flask import Blueprint, Response, g

from app.middleware.auth_middleware import require_auth
from app.services.sse_manager import sse_manager

events_bp = Blueprint('events', __name__, url_prefix='/events')


@events_bp.get('')
@require_auth
def stream():
    """Long-lived SSE stream for the authenticated user.

    Sends a keepalive comment every 25 s to prevent proxies from closing idle
    connections. The client reconnects automatically on drop.

    Events emitted:
      plan_changed      {"plan": "pro"}
      transfer_incoming {"session_id", "file_name", "file_size", "mime_type",
                         "sender_device_name"}
      transfer_cancelled {"session_id"}
    """
    user_id = g.current_user.id
    ps = sse_manager.subscribe(user_id)

    def generate():
        yield ': connected\n\n'
        try:
            while True:
                msg = sse_manager.get_message(ps, timeout=25.0)
                if msg is not None:
                    yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                else:
                    yield ': keepalive\n\n'
        finally:
            sse_manager.unsubscribe(ps)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
