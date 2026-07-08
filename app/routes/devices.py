from flask import Blueprint, g, request
from marshmallow import ValidationError

from app.middleware.auth_middleware import require_auth
from app.schemas.device_schemas import RegisterDeviceSchema
from app.services.device_service import DeviceService
from app.utils.errors import not_found, validation_failed

devices_bp = Blueprint('devices', __name__, url_prefix='/devices')

_register_device_schema = RegisterDeviceSchema()


@devices_bp.post('/register')
@require_auth
def register_device():
    try:
        data = _register_device_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    device = DeviceService.register(
        g.current_user,
        data['device_id'],
        data['name'],
        data['platform'],
        data.get('app_version'),
    )
    return _serialize(device), 201


@devices_bp.get('')
@require_auth
def list_devices():
    devices = DeviceService.list_for_user(g.current_user)
    return {'devices': [_serialize(d) for d in devices]}


@devices_bp.patch('/fcm-token')
@require_auth
def update_fcm_token():
    data = request.get_json(silent=True) or {}
    device_id = (data.get('device_id') or '').strip()
    token = (data.get('fcm_token') or '').strip()
    if not device_id or not token:
        from app.utils.errors import bad_request
        return bad_request('device_id and fcm_token are required')
    if not DeviceService.update_fcm_token(g.current_user, device_id, token):
        return not_found('Device not found')
    return '', 204


@devices_bp.delete('/<device_id>')
@require_auth
def delete_device(device_id):
    if not DeviceService.delete(g.current_user, device_id):
        return not_found('Device not found')
    return '', 204


def _serialize(device) -> dict:
    return {
        'id': device.id,
        'name': device.name,
        'platform': device.platform,
        'app_version': device.app_version,
        'last_seen_at': device.last_seen_at.isoformat() if device.last_seen_at else None,
        'created_at': device.created_at.isoformat(),
    }
