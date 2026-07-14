import base64
import json
import logging
import time
import uuid

import jwt as pyjwt
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select

from app.extensions import db, sock
from app.middleware.auth_middleware import require_auth
from app.models.device import Device
from app.models.user import User
from app.services.sse_manager import sse_manager
from app.utils.errors import bad_request, forbidden, not_found
from app.utils.feature_gate import can_use_file_transfer
from app.utils.redis_client import get_redis
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

transfer_bp = Blueprint('transfer', __name__, url_prefix='/transfer')

# ── Tier limits ───────────────────────────────────────────────────────────────
_MAX_FILE_SIZE = {
    'pro':    100 * 1024 * 1024,   # 100 MB
    'pro_ai': 100 * 1024 * 1024,   # 100 MB
    'team':   500 * 1024 * 1024,   # 500 MB
}
_DAILY_QUOTA = {
    'pro':    1 * 1024 * 1024 * 1024,    # 1 GB
    'pro_ai': 1 * 1024 * 1024 * 1024,    # 1 GB
    'team':   10 * 1024 * 1024 * 1024,   # 10 GB
}
_SESSION_TTL = 600   # 10 minutes
# Per-chunk blpop timeout. Shorter than SESSION_TTL so the loop can re-check
# liveness without holding a blocking call for the full session duration.
_BLPOP_TIMEOUT = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _session_key(session_id: str) -> str:
    return f'transfer:{session_id}'


def _data_key(session_id: str) -> str:
    return f'transfer:{session_id}:data'


def _quota_key(user_id: str) -> str:
    return f'transfer:quota:{user_id}:{utcnow().strftime("%Y-%m-%d")}'


def _load_session(session_id: str, user_id: str) -> dict | None:
    raw = get_redis().get(_session_key(session_id))
    if not raw:
        return None
    session = json.loads(raw)
    return session if session.get('user_id') == user_id else None


def _device_name(user_id: str, device_id: str) -> str:
    if not device_id:
        return 'Unknown Device'
    device = db.session.execute(
        select(Device).where(Device.id == device_id, Device.user_id == user_id)
    ).scalar_one_or_none()
    return device.name if device else 'Unknown Device'



def _ws_auth():
    """Authenticate a WebSocket connection via ?token= query param."""
    token = request.args.get('token', '')
    if not token:
        return None
    try:
        payload = pyjwt.decode(
            token, current_app.config['SECRET_KEY'], algorithms=['HS256']
        )
    except pyjwt.InvalidTokenError:
        return None
    user = db.session.get(User, payload['sub'])
    if not user or not user.is_active:
        return None
    return user


# ── HTTP routes ───────────────────────────────────────────────────────────────

@transfer_bp.post('/start')
@require_auth
def start_transfer():
    user = g.current_user

    if not can_use_file_transfer(user):
        return forbidden('File transfer requires a Team plan or the File Transfer addon.')

    data = request.get_json(silent=True) or {}
    file_name = (data.get('file_name') or '').strip()
    file_size = data.get('file_size')
    mime_type = (data.get('mime_type') or 'application/octet-stream').strip()
    target_device_id = (data.get('target_device_id') or '').strip()
    sender_device_id = request.headers.get('X-Device-ID', '')

    if not file_name:
        return bad_request('file_name is required')
    if not isinstance(file_size, int) or file_size <= 0:
        return bad_request('file_size must be a positive integer')
    if not target_device_id:
        return bad_request('target_device_id is required')
    if target_device_id == sender_device_id:
        return bad_request('Cannot transfer to the same device')

    target_device = db.session.execute(
        select(Device).where(
            Device.id == target_device_id,
            Device.user_id == user.id,
        )
    ).scalar_one_or_none()
    if not target_device:
        return not_found('Target device not found')

    tier = user.subscription.tier if user.subscription else 'free'
    max_size = _MAX_FILE_SIZE.get(tier, 0)
    if file_size > max_size:
        mb = max_size // (1024 * 1024)
        return bad_request(f'File exceeds the {mb} MB limit for your plan')

    r = get_redis()
    used = int(r.get(_quota_key(user.id)) or 0)
    if used + file_size > _DAILY_QUOTA.get(tier, 0):
        return bad_request('Daily transfer quota exceeded. Try again tomorrow.')

    session_id = str(uuid.uuid4())
    sender_name = _device_name(user.id, sender_device_id)
    session_data = {
        'user_id': user.id,
        'file_name': file_name,
        'file_size': file_size,
        'mime_type': mime_type,
        'sender_device_id': sender_device_id,
        'target_device_id': target_device_id,
        'sender_device_name': sender_name,
    }
    r.set(_session_key(session_id), json.dumps(session_data), ex=_SESSION_TTL)

    sse_manager.publish(user.id, 'transfer_incoming', {
        'session_id': session_id,
        'file_name': file_name,
        'file_size': file_size,
        'mime_type': mime_type,
        'sender_device_name': sender_name,
        'target_device_id': target_device_id,
    })

    # FCM fallback: wakes the app when backgrounded/killed and SSE is down.
    if target_device.fcm_token:
        from app.services.fcm_service import send_transfer_incoming
        send_transfer_incoming(
            fcm_token=target_device.fcm_token,
            session_id=session_id,
            file_name=file_name,
            file_size=file_size,
            sender_device_name=sender_name,
            mime_type=mime_type,
            target_device_id=target_device_id,
        )

    logger.info(
        'transfer_start: session=%s user=%s size=%d target=%s',
        session_id, user.id, file_size, target_device_id,
    )
    return jsonify({'session_id': session_id}), 201


@transfer_bp.delete('/<session_id>')
@require_auth
def cancel_transfer(session_id):
    user = g.current_user
    session = _load_session(session_id, user.id)
    if not session:
        return not_found('Transfer session not found')

    r = get_redis()
    r.delete(_session_key(session_id))
    r.delete(_data_key(session_id))
    sse_manager.publish(user.id, 'transfer_cancelled', {'session_id': session_id})
    return '', 204


# ── WebSocket routes ──────────────────────────────────────────────────────────
# Registered directly on `sock` (flask-sock doesn't support blueprint-scoped
# WebSocket routes). The /snap prefix must be included explicitly.

@sock.route('/snap/transfer/<session_id>/send')
def transfer_send(ws, session_id):
    user = _ws_auth()
    if not user:
        ws.send(json.dumps({'error': 'Authentication required'}))
        return

    if not can_use_file_transfer(user):
        ws.send(json.dumps({'error': 'File transfer not available on your plan'}))
        return

    session = _load_session(session_id, user.id)
    if not session:
        ws.send(json.dumps({'error': 'Session not found or expired'}))
        return

    sender_device_id = request.args.get('device_id', '')
    if sender_device_id and session['sender_device_id'] and \
            sender_device_id != session['sender_device_id']:
        ws.send(json.dumps({'error': 'Device not authorised for this session'}))
        return

    r = get_redis()
    data_key = _data_key(session_id)
    bytes_relayed = 0

    try:
        while True:
            chunk = ws.receive()
            if chunk is None:
                break

            encoded = (
                base64.b64encode(chunk).decode('ascii')
                if isinstance(chunk, (bytes, bytearray))
                else chunk
            )

            # Buffer chunk in a Redis list so the receiver can read it at any
            # time — even after the sender has finished. This eliminates the
            # race condition inherent in pub/sub (fire-and-forget).
            pipe = r.pipeline()
            pipe.rpush(data_key, encoded)
            pipe.expire(data_key, _SESSION_TTL)
            pipe.execute()

            if isinstance(chunk, (bytes, bytearray)):
                bytes_relayed += len(chunk)

            if bytes_relayed >= session['file_size']:
                break

        # Push EOF sentinel so the receiver knows the stream ended.
        pipe = r.pipeline()
        pipe.rpush(data_key, '__EOF__')
        pipe.expire(data_key, _SESSION_TTL)
        pipe.execute()

        # Increment daily quota counter
        qk = _quota_key(session['user_id'])
        pipe = r.pipeline()
        pipe.incrby(qk, bytes_relayed)
        pipe.expire(qk, 86400)
        pipe.execute()

        # Do NOT delete the session key here: the receiver may connect after
        # the sender finishes (race window) and needs _load_session to succeed.
        # The key has ex=_SESSION_TTL so it expires automatically.
        logger.info(
            'transfer_send: complete session=%s bytes=%d', session_id, bytes_relayed
        )

    except Exception:
        logger.exception('transfer_send: error session=%s', session_id)
        try:
            pipe = r.pipeline()
            pipe.rpush(data_key, '__ERROR__')
            pipe.expire(data_key, _SESSION_TTL)
            pipe.execute()
        except Exception:
            pass


@sock.route('/snap/transfer/<session_id>/recv')
def transfer_recv(ws, session_id):
    user = _ws_auth()
    if not user:
        ws.send(json.dumps({'error': 'Authentication required'}))
        return

    session = _load_session(session_id, user.id)
    if not session:
        ws.send(json.dumps({'error': 'Session not found or expired'}))
        return

    device_id = request.args.get('device_id', '')
    if device_id != session['target_device_id']:
        ws.send(json.dumps({'error': 'Device not authorised to receive this transfer'}))
        return

    data_key = _data_key(session_id)
    r = get_redis()
    deadline = time.monotonic() + _SESSION_TTL

    try:
        while True:
            # BLPOP blocks until a chunk is available or the timeout expires.
            # Short timeout (30 s) allows the loop to re-check the deadline
            # without holding up the thread for the full session duration.
            result = r.blpop([data_key], timeout=_BLPOP_TIMEOUT)

            if result is None:
                # No chunk arrived within the window.
                if time.monotonic() >= deadline:
                    ws.send(json.dumps({'error': 'Transfer timed out'}))
                    break
                # Sender hasn't started yet — keep waiting.
                continue

            _, raw = result
            data = raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw

            if data == '__EOF__':
                break
            if data == '__ERROR__':
                ws.send(json.dumps({'error': 'Sender encountered an error'}))
                break

            ws.send(base64.b64decode(data))

    except Exception:
        logger.exception('transfer_recv: error session=%s', session_id)
    finally:
        # Remove any unconsumed chunks (cancelled / error path).
        try:
            r.delete(data_key)
        except Exception:
            pass
