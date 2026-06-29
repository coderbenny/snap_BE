from flask import Blueprint, g, request
from marshmallow import ValidationError

from app.extensions import limiter
from app.middleware.auth_middleware import require_auth
from app.middleware.plan_guard import require_plan
from app.schemas.sync_schemas import SyncDeleteSchema, SyncPushSchema
from app.services.sync_service import SyncService
from app.utils.errors import bad_request, validation_failed
from app.utils.time import to_unix_ms

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')

_push_schema = SyncPushSchema()
_delete_schema = SyncDeleteSchema()

_DEFAULT_LIMIT = 200
_MAX_LIMIT = 500


@sync_bp.get('')
@require_auth
@require_plan('pro', 'pro_ai', 'team')
@limiter.limit('60 per minute')
def pull():
    since_raw = request.args.get('since')
    limit_raw = request.args.get('limit', _DEFAULT_LIMIT)
    device_id = request.args.get('device_id')

    since: int | None = None
    if since_raw is not None:
        try:
            since = int(since_raw)
            if since < 0:
                raise ValueError
        except ValueError:
            return bad_request("'since' must be a non-negative integer (Unix ms)")

    try:
        limit = int(limit_raw)
        if not (1 <= limit <= _MAX_LIMIT):
            raise ValueError
    except ValueError:
        return bad_request(f"'limit' must be an integer between 1 and {_MAX_LIMIT}")

    items, has_more = SyncService.pull(g.current_user, since, limit)
    SyncService.update_device_last_seen(g.current_user, device_id)

    return {
        'items': [_serialize(item) for item in items],
        'has_more': has_more,
        'next_since': to_unix_ms(items[-1].synced_at) if items else (since or 0),
    }


@sync_bp.get('/stats')
@require_auth
@require_plan('pro', 'pro_ai', 'team')
@limiter.limit('30 per minute')
def stats():
    """Return the total number of non-deleted clips for the authenticated user."""
    count = SyncService.count_clips(g.current_user)
    return {'clip_count': count}


@sync_bp.post('/push')
@require_auth
@require_plan('pro', 'pro_ai', 'team')
@limiter.limit('60 per minute')
def push():
    device_id = request.args.get('device_id')

    try:
        data = _push_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    count = SyncService.push(g.current_user, data['items'])
    SyncService.update_device_last_seen(g.current_user, device_id)

    return {'accepted': count}, 200


@sync_bp.post('/delete')
@require_auth
@require_plan('pro', 'pro_ai', 'team')
@limiter.limit('60 per minute')
def soft_delete():
    try:
        data = _delete_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    deleted = SyncService.soft_delete(g.current_user, data['ids'])
    return {'deleted': deleted}, 200


def _serialize(item) -> dict:
    return {
        'id': item.id,
        'ciphertext': item.ciphertext,
        'iv': item.iv,
        'content_type': item.content_type,
        'tags': item.tags,
        'pinned': item.pinned,
        'device_id': item.device_id,
        'client_created_at': item.client_created_at,
        'synced_at': to_unix_ms(item.synced_at),
        'deleted_at': to_unix_ms(item.deleted_at) if item.deleted_at else None,
    }


