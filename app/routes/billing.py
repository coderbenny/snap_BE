from flask import Blueprint, g, request
from marshmallow import ValidationError

from app.middleware.auth_middleware import require_auth
from app.schemas.billing_schemas import SubscribeSchema
from app.services.billing_service import BillingService
from app.utils.errors import bad_request, not_found, server_error, validation_failed

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

_subscribe_schema = SubscribeSchema()


@billing_bp.get('/plans')
def get_plans():
    return {'plans': BillingService.PLANS}


@billing_bp.post('/subscribe')
@require_auth
def subscribe():
    try:
        data = _subscribe_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        url = BillingService.initialize_transaction(
            g.current_user,
            data['tier'],
            data.get('callback_url'),
        )
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Failed to initialize payment. Please try again.')

    return {'authorization_url': url}, 200


@billing_bp.post('/portal')
@require_auth
def portal():
    try:
        link = BillingService.get_portal_link(g.current_user)
    except LookupError:
        return not_found('No active subscription found')
    except Exception:
        return server_error('Failed to retrieve portal link. Please try again.')

    return {'portal_url': link}, 200
