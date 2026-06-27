import hashlib
import hmac
import logging
from datetime import datetime, timedelta

import requests
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models.subscription import Subscription
from app.models.user import User
from app.services.sse_manager import sse_manager
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_PAYSTACK_BASE = 'https://api.paystack.co'

# Days added to now when expires_at is set from charge.success (before
# subscription.create fires with the exact next_payment_date).
_PROVISIONAL_EXPIRY_DAYS = 35


class BillingService:

    PLANS = [
        {
            'tier': 'pro',
            'name': 'Pro',
            'price_usd_cents': 500,
            'interval': 'monthly',
            'features': [
                'Unlimited sync across all devices',
                'Cross-device clipboard history',
                '30-day history retention',
                'Up to 5 devices',
            ],
        },
        {
            'tier': 'pro_ai',
            'name': 'Pro + AI',
            'price_usd_cents': 900,
            'interval': 'monthly',
            'features': [
                'Everything in Pro',
                'OCR text extraction from images',
                'AI-powered clipboard actions',
                'Smart categorisation',
            ],
        },
        {
            'tier': 'team',
            'name': 'Team',
            'price_usd_cents': 800,
            'interval': 'monthly',
            'features': [
                'Everything in Pro',
                'Shared snippet libraries',
                'Team management dashboard',
                'Per-seat billing',
            ],
        },
    ]

    @staticmethod
    def initialize_transaction(user: User, tier: str, callback_url: str | None) -> str:
        """Initialize a Paystack transaction. Returns the authorization_url."""
        plan_code = current_app.config.get('PAYSTACK_PLANS', {}).get(tier)
        if not plan_code:
            raise ValueError(f"No Paystack plan configured for tier '{tier}'")

        payload: dict = {
            'email': user.email,
            'amount': 0,      # overridden by the plan
            'plan': plan_code,
            'metadata': {'user_id': user.id, 'tier': tier},
        }
        if callback_url:
            payload['callback_url'] = callback_url

        data = _paystack_post('/transaction/initialize', payload)
        return data['data']['authorization_url']

    @staticmethod
    def get_portal_link(user: User) -> str:
        """Return the Paystack subscription management link for the user."""
        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()

        if not sub or not sub.paystack_sub_code:
            raise LookupError('No active subscription found')

        data = _paystack_get(f'/subscription/{sub.paystack_sub_code}/manage/link')
        return data['data']['link']

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
        secret = current_app.config.get('PAYSTACK_WEBHOOK_SECRET', '')
        expected = hmac.new(
            key=secret.encode(),
            msg=raw_body,
            digestmod=hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def handle_event(event_type: str, data: dict) -> None:
        handlers = {
            'charge.success': BillingService._on_charge_success,
            'subscription.create': BillingService._on_subscription_create,
            'subscription.disable': BillingService._on_subscription_disable,
            'invoice.payment_failed': BillingService._on_invoice_payment_failed,
        }
        handler = handlers.get(event_type)
        if handler:
            try:
                handler(data)
            except Exception:
                logger.exception('Error handling Paystack event %s', event_type)

    # ── Event handlers ────────────────────────────────────────────────────────

    @staticmethod
    def _on_charge_success(data: dict) -> None:
        plan_code = (data.get('plan') or {}).get('plan_code')
        if not plan_code:
            return  # one-time charge, not a subscription

        customer = data.get('customer') or {}
        email = (customer.get('email') or '').lower()
        customer_code = customer.get('customer_code')
        tier = BillingService._tier_from_plan_code(plan_code)

        if not email or not tier:
            logger.warning(
                'charge.success: unresolvable email=%s or plan_code=%s', email, plan_code
            )
            return

        user = db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if not user:
            return

        now = utcnow()
        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()

        if sub:
            sub.tier = tier
            sub.status = 'active'
            sub.expires_at = now + timedelta(days=_PROVISIONAL_EXPIRY_DAYS)
            if customer_code:
                sub.paystack_customer_code = customer_code
        else:
            db.session.add(Subscription(
                user_id=user.id,
                tier=tier,
                status='active',
                paystack_customer_code=customer_code,
                expires_at=now + timedelta(days=_PROVISIONAL_EXPIRY_DAYS),
            ))

        user.plan_tier = tier
        db.session.commit()
        sse_manager.publish(user.id, 'plan_changed', {'plan': tier})

    @staticmethod
    def _on_subscription_create(data: dict) -> None:
        sub_code = data.get('subscription_code')
        customer = data.get('customer') or {}
        email = (customer.get('email') or '').lower()
        customer_code = customer.get('customer_code')
        next_payment_raw = data.get('next_payment_date')

        if not sub_code or not email:
            return

        user = db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if not user:
            return

        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        if not sub:
            return

        sub.paystack_sub_code = sub_code
        if customer_code:
            sub.paystack_customer_code = customer_code
        if next_payment_raw:
            try:
                sub.expires_at = (
                    datetime.fromisoformat(next_payment_raw.replace('Z', '+00:00'))
                    .replace(tzinfo=None)
                )
            except (ValueError, AttributeError):
                pass

        db.session.commit()

    @staticmethod
    def _on_subscription_disable(data: dict) -> None:
        sub_code = data.get('subscription_code')
        if not sub_code:
            return

        sub = db.session.execute(
            select(Subscription).where(Subscription.paystack_sub_code == sub_code)
        ).scalar_one_or_none()
        if not sub:
            return

        sub.status = 'cancelled'
        sub.user.plan_tier = 'free'
        db.session.commit()
        sse_manager.publish(sub.user.id, 'plan_changed', {'plan': 'free'})

    @staticmethod
    def _on_invoice_payment_failed(data: dict) -> None:
        sub_code = (data.get('subscription') or {}).get('subscription_code')
        if not sub_code:
            return

        sub = db.session.execute(
            select(Subscription).where(Subscription.paystack_sub_code == sub_code)
        ).scalar_one_or_none()
        if sub:
            sub.status = 'past_due'
            db.session.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _tier_from_plan_code(plan_code: str) -> str | None:
        plans = current_app.config.get('PAYSTACK_PLANS', {})
        for tier, code in plans.items():
            if code and code == plan_code:
                return tier
        return None


# ── Private Paystack HTTP helpers ─────────────────────────────────────────────

def _paystack_post(path: str, payload: dict) -> dict:
    resp = requests.post(
        f'{_PAYSTACK_BASE}{path}',
        json=payload,
        headers={'Authorization': f'Bearer {current_app.config["PAYSTACK_SECRET_KEY"]}'},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get('status'):
        raise RuntimeError(body.get('message', 'Paystack error'))
    return body


def _paystack_get(path: str) -> dict:
    resp = requests.get(
        f'{_PAYSTACK_BASE}{path}',
        headers={'Authorization': f'Bearer {current_app.config["PAYSTACK_SECRET_KEY"]}'},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get('status'):
        raise RuntimeError(body.get('message', 'Paystack error'))
    return body
