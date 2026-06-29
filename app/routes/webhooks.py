import json
import logging

from flask import Blueprint, request

from app.services.billing_service import BillingService
from app.utils.errors import bad_request

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')


@webhooks_bp.post('/paystack')
def paystack_webhook():
    raw_body = request.get_data()
    signature = request.headers.get('x-paystack-signature', '')

    if not BillingService.verify_webhook_signature(raw_body, signature):
        return bad_request('Invalid signature')

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error('Paystack webhook: malformed JSON body=%s', raw_body[:200])
        return {'status': 'ok'}, 200

    event_type = payload.get('event', '')
    data = payload.get('data') or {}
    try:
        BillingService.handle_event(event_type, data)
    except Exception:
        logger.exception('Paystack webhook: unhandled error for event=%s', event_type)

    # Always 200 — Paystack retries on non-2xx.
    return {'status': 'ok'}, 200
