import logging
from functools import wraps

import jwt
from flask import current_app, g, request
from sqlalchemy import select

from app.extensions import db
from app.models.device import Device
from app.models.user import User
from app.utils.errors import unauthorized
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return unauthorized()

        token = auth_header[7:]
        try:
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256'],
            )
        except jwt.ExpiredSignatureError:
            return unauthorized('Token has expired')
        except jwt.InvalidTokenError:
            return unauthorized('Invalid token')

        user = db.session.get(User, payload['sub'])
        if not user:
            return unauthorized()

        g.current_user = user

        device_id = request.headers.get('X-Device-ID')
        if device_id:
            g.device_id = device_id
            _touch_device(user.id, device_id)

        return f(*args, **kwargs)

    return decorated


def _touch_device(user_id: str, device_id: str) -> None:
    """Update last_seen_at for the device, throttled to once per 5 minutes via Redis."""
    try:
        from app.utils.redis_client import get_redis
        r = get_redis()
        redis_key = f'device_seen:{device_id}'
        # nx=True means "only set if not already present" — acts as the cooldown gate
        if r.set(redis_key, '1', ex=300, nx=True):
            device = db.session.execute(
                select(Device).where(Device.id == device_id, Device.user_id == user_id)
            ).scalar_one_or_none()
            if device:
                device.last_seen_at = utcnow()
                db.session.commit()
    except Exception:
        logger.debug('Failed to touch device last_seen_at for device=%s', device_id)
        try:
            db.session.rollback()
        except Exception:
            pass
