import json
import secrets

from flask import Blueprint, current_app, g, request
from marshmallow import ValidationError

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_auth
from app.models.user import User
from app.schemas.billing_schemas import SubscribeSchema
from app.services.billing_service import BillingService
from app.utils.errors import bad_request, not_found, server_error, validation_failed
from app.utils.redis_client import get_redis

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
        result = BillingService.initialize_transaction(
            g.current_user,
            data['tier'],
            data.get('callback_url'),
        )
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Failed to initialize payment. Please try again.')

    # Return all three fields so the frontend can use the inline popup
    # (access_code) or fall back to a redirect (authorization_url).
    return result, 200


@billing_bp.get('/verify/<reference>')
@require_auth
def verify(reference: str):
    """
    Called by the frontend after the Paystack popup reports success.
    Verifies with Paystack and activates the plan in the DB so the UI
    updates immediately, even on localhost where webhooks can't arrive.
    """
    try:
        result = BillingService.verify_transaction(g.current_user, reference)
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Verification failed. Please refresh the page.')

    return result, 200


@billing_bp.post('/upgrade-link')
@require_auth
def upgrade_link():
    """Generate a short-lived upgrade URL for the desktop app to open in a browser."""
    body = request.get_json(silent=True) or {}
    tier = body.get('tier', 'pro')
    if tier not in ('pro', 'pro_ai', 'team'):
        return bad_request(f"Invalid tier '{tier}'")

    token = secrets.token_urlsafe(16)
    payload = json.dumps({'user_id': g.current_user.id, 'tier': tier})
    get_redis().set(f'upgrade_token:{token}', payload, ex=900)  # 15-minute TTL

    base = current_app.config.get('FRONTEND_URL', 'https://snapit.ink')
    return {'url': f'{base}/upgrade?token={token}&tier={tier}'}, 200


@billing_bp.post('/init-upgrade')
@limiter.limit('10 per minute')
def init_upgrade():
    """Validate a desktop upgrade token and initialise a Paystack transaction.

    Called by the web upgrade page (no browser session required — the token
    proves identity).  The token is single-use and expires after 15 minutes.
    """
    body = request.get_json(silent=True) or {}
    token = (body.get('token') or '').strip()
    callback_url = body.get('callback_url')

    if not token:
        return bad_request('Token is required')

    r = get_redis()
    pipe = r.pipeline()
    pipe.get(f'upgrade_token:{token}')
    pipe.delete(f'upgrade_token:{token}')
    payload_str, _ = pipe.execute()

    if not payload_str:
        return bad_request(
            'Invalid or expired upgrade link. Please generate a new one from the app.'
        )

    try:
        payload = json.loads(payload_str)
        user_id = payload['user_id']
        tier = payload['tier']
    except (KeyError, json.JSONDecodeError):
        return bad_request('Malformed upgrade token')

    user = db.session.get(User, user_id)
    if not user:
        return bad_request('User not found')

    try:
        result = BillingService.initialize_transaction(user, tier, callback_url)
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Failed to initialise payment. Please try again.')

    return result, 200


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
