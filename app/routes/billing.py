import json
import logging
import secrets

from flask import Blueprint, current_app, g, request
from marshmallow import ValidationError

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_auth
from app.models.coupon import Coupon
from app.models.user import User
from app.schemas.billing_schemas import SubscribeSchema
from app.services.billing_service import BillingService
from app.utils.errors import (
    bad_request,
    not_found,
    server_error,
    service_unavailable,
    validation_failed,
)
from app.utils.redis_client import get_redis
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

_subscribe_schema = SubscribeSchema()


@billing_bp.get('/plans')
def get_plans():
    return {
        'plans': BillingService.PLANS,
        'addons': BillingService.get_addon_prices(),
    }


@billing_bp.post('/validate-coupon')
@require_auth
def validate_coupon():
    """Read-only coupon check. Returns discount preview with no side effects."""
    body = request.get_json(silent=True) or {}
    code = (body.get('code') or '').strip().upper()
    tier = (body.get('tier') or '').strip()

    if not code:
        return bad_request('code is required')
    if tier not in ('pro', 'pro_ai', 'team'):
        return bad_request('tier must be one of: pro, pro_ai, team')

    from sqlalchemy import select
    coupon = db.session.execute(
        select(Coupon).where(Coupon.code == code)
    ).scalar_one_or_none()

    if not coupon or not coupon.is_active:
        return bad_request('Invalid or inactive coupon code')

    now = utcnow()
    if coupon.valid_from and coupon.valid_from > now:
        return bad_request('This coupon is not yet valid')
    if coupon.valid_until and coupon.valid_until < now:
        return bad_request('This coupon has expired')
    if coupon.max_uses is not None and coupon.current_uses >= coupon.max_uses:
        return bad_request('This coupon has reached its usage limit')
    if coupon.tier_restriction and coupon.tier_restriction != tier:
        return bad_request(f'This coupon is only valid for the {coupon.tier_restriction} plan')

    plan = next((p for p in BillingService.PLANS if p['tier'] == tier), None)
    if not plan:
        return bad_request(f"Unknown tier '{tier}'")

    original = plan['price_usd_cents']
    if coupon.discount_type == 'percentage':
        discount_amount = int(original * coupon.discount_value / 100)
    else:
        discount_amount = min(coupon.discount_value, original)

    discounted = max(0, original - discount_amount)

    return {
        'valid': True,
        'code': coupon.code,
        'description': coupon.description or '',
        'discount_type': coupon.discount_type,
        'discount_value': coupon.discount_value,
        'original_price_cents': original,
        'discounted_price_cents': discounted,
    }, 200


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
            coupon_code=data.get('coupon_code'),
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
    try:
        get_redis().set(f'upgrade_token:{token}', payload, ex=900)  # 15-minute TTL
    except Exception:
        logger.error('upgrade_link: Redis unavailable — cannot store upgrade token')
        return service_unavailable(
            'Upgrade service is temporarily unavailable. Please try again in a moment.'
        )

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


@billing_bp.post('/addon/file-transfer')
@require_auth
def purchase_file_transfer_addon():
    """Initialize a one-time payment to activate the file-transfer addon."""
    body = request.get_json(silent=True) or {}
    try:
        result = BillingService.initialize_addon_transaction(
            g.current_user,
            'file_transfer',
            body.get('callback_url'),
        )
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Failed to initialize payment. Please try again.')

    return result, 200


@billing_bp.get('/addon/verify/<reference>')
@require_auth
def verify_addon(reference: str):
    """Verify an addon payment and activate the addon immediately."""
    try:
        result = BillingService.verify_addon_transaction(g.current_user, reference)
    except ValueError as e:
        return bad_request(str(e))
    except Exception:
        return server_error('Verification failed. Please try again.')

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
