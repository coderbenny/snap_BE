import hashlib
import hmac
import logging
from datetime import datetime, timedelta

import requests
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models.coupon import Coupon, CouponUse
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
                'File transfer between devices',
            ],
        },
        {
            'tier': 'pro_ai',
            'name': 'Pro + AI',
            'price_usd_cents': 900,
            'interval': 'monthly',
            'features': [
                'Everything in Pro',
                'File transfer between devices',
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
                'File transfer between devices',
                'Shared snippet libraries',
                'Team management dashboard',
                'Per-seat billing',
            ],
        },
    ]

    # Default price — override with ADDON_FILE_TRANSFER_PRICE_CENTS in Flask config / env.
    ADDON_FILE_TRANSFER_PRICE_CENTS = 200

    ADDONS = [
        {
            'id': 'file_transfer',
            'name': 'File Transfer',
            'description': (
                'Drag & drop files between your devices instantly. '
                'Server-relayed, nothing stored on disk.'
            ),
            'type': 'one_time',
            # price_usd_cents is injected at request time from config — see get_addon_prices()
        },
    ]

    @staticmethod
    def get_addon_prices() -> list[dict]:
        """Return ADDONS with live price_usd_cents resolved from config."""
        price_map = {
            'file_transfer': current_app.config.get(
                'ADDON_FILE_TRANSFER_PRICE_CENTS',
                BillingService.ADDON_FILE_TRANSFER_PRICE_CENTS,
            ),
        }
        return [
            {**addon, 'price_usd_cents': price_map.get(addon['id'], 0)}
            for addon in BillingService.ADDONS
        ]

    @staticmethod
    def initialize_addon_transaction(user: User, addon: str, callback_url: str | None) -> dict:
        """Initialize a one-time Paystack charge for an addon.

        Unlike plan subscriptions, addons are one-time payments (no `plan`
        field).  The metadata `addon` key is used by the webhook and verify
        handlers to route the activation.
        """
        if addon != 'file_transfer':
            raise ValueError(f"Unknown addon '{addon}'")

        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        # File transfer is now bundled into every paid tier — nothing to purchase.
        if sub and sub.status == 'active':
            raise ValueError('File transfer is already included in your plan')
        if not sub or sub.status != 'active':
            raise ValueError('An active subscription is required to purchase addons')

        prices = {a['id']: a['price_usd_cents'] for a in BillingService.get_addon_prices()}
        amount = prices.get(addon, 0)
        payload: dict = {
            'email': user.email,
            'amount': amount,
            'metadata': {'user_id': user.id, 'addon': addon},
        }
        if callback_url:
            payload['callback_url'] = callback_url

        body = _paystack_post('/transaction/initialize', payload)
        d = body['data']
        return {
            'authorization_url': d['authorization_url'],
            'access_code': d['access_code'],
            'reference': d['reference'],
        }

    @staticmethod
    def verify_addon_transaction(user: User, reference: str) -> dict:
        """Verify a one-time addon payment and activate the addon."""
        body = _paystack_get(f'/transaction/verify/{reference}')
        d = body['data']

        if d.get('status') != 'success':
            raise ValueError(f"Transaction not successful: {d.get('status')}")

        addon = (d.get('metadata') or {}).get('addon')
        if addon != 'file_transfer':
            raise ValueError('Reference is not for a file-transfer addon purchase')

        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        if not sub:
            raise ValueError('No subscription found')

        if not sub.file_transfer_addon:
            sub.file_transfer_addon = True
            db.session.commit()
            logger.info('File transfer addon activated via verify: user=%s', user.id)

        return {'status': 'success', 'addon': 'file_transfer', 'reference': reference}

    @staticmethod
    def initialize_transaction(
        user: User,
        tier: str,
        callback_url: str | None,
        coupon_code: str | None = None,
    ) -> dict:
        """Initialize a Paystack transaction.

        Returns a dict with authorization_url, access_code, and reference so
        the frontend can choose between inline popup (access_code) or redirect
        (authorization_url).

        When coupon_code is provided it is re-validated server-side (never
        trust the frontend alone), the discounted amount is passed to Paystack
        so the first charge reflects the discount, and the coupon id is stored
        in metadata so verify_transaction can record the use.
        """
        plan_code = current_app.config.get('PAYSTACK_PLANS', {}).get(tier)
        if not plan_code:
            raise ValueError(f"No Paystack plan configured for tier '{tier}'")

        plan = next((p for p in BillingService.PLANS if p['tier'] == tier), None)
        original_amount = plan['price_usd_cents'] if plan else 0

        coupon = None
        discounted_amount = original_amount

        if coupon_code:
            coupon = BillingService._validate_coupon_for_tier(
                coupon_code.strip().upper(), tier
            )
            if coupon.discount_type == 'percentage':
                discount = int(original_amount * coupon.discount_value / 100)
            else:
                discount = min(coupon.discount_value, original_amount)
            discounted_amount = max(0, original_amount - discount)

        metadata: dict = {'user_id': user.id, 'tier': tier}
        if coupon:
            metadata['coupon_id'] = coupon.id

        payload: dict = {
            'email': user.email,
            'amount': discounted_amount,
            'plan': plan_code,
            'metadata': metadata,
        }
        if callback_url:
            payload['callback_url'] = callback_url

        body = _paystack_post('/transaction/initialize', payload)
        d = body['data']
        return {
            'authorization_url': d['authorization_url'],
            'access_code': d['access_code'],
            'reference': d['reference'],
        }

    @staticmethod
    def _validate_coupon_for_tier(code: str, tier: str) -> 'Coupon':
        """Validate a coupon server-side and return it. Raises ValueError on any failure."""
        coupon = db.session.execute(
            select(Coupon).where(Coupon.code == code)
        ).scalar_one_or_none()

        if not coupon or not coupon.is_active:
            raise ValueError('Invalid or inactive coupon code')

        now = utcnow()
        if coupon.valid_from and coupon.valid_from > now:
            raise ValueError('This coupon is not yet valid')
        if coupon.valid_until and coupon.valid_until < now:
            raise ValueError('This coupon has expired')
        if coupon.max_uses is not None and coupon.current_uses >= coupon.max_uses:
            raise ValueError('This coupon has reached its usage limit')
        if coupon.tier_restriction and coupon.tier_restriction != tier:
            raise ValueError(f'This coupon is only valid for the {coupon.tier_restriction} plan')

        return coupon

    @staticmethod
    def verify_transaction(user: User, reference: str) -> dict:
        """Verify a Paystack transaction and activate the plan in the DB.

        This is the authoritative activation path for dev/staging where
        Paystack webhooks cannot reach localhost.  The webhook handler runs
        the same logic, so concurrent updates are idempotent.
        """
        body = _paystack_get(f'/transaction/verify/{reference}')
        d = body['data']

        if d.get('status') != 'success':
            raise ValueError(f"Transaction not successful: {d.get('status')}")

        # Paystack returns `plan` as a plain string (the plan code) in the
        # verify response, NOT as a nested object.  Calling .get() on a str
        # raises AttributeError — guard with isinstance before using it.
        raw_plan = d.get('plan') or ''
        if isinstance(raw_plan, dict):
            plan_code = raw_plan.get('plan_code', '')
        else:
            plan_code = raw_plan  # already the plan code string

        # plan_object carries the canonical plan details; use as fallback.
        if not plan_code:
            plan_code = (d.get('plan_object') or {}).get('plan_code', '')

        tier = BillingService._tier_from_plan_code(plan_code) if plan_code else None

        # Activate the plan in the DB so the UI reflects immediately, even
        # when the Paystack webhook hasn't arrived yet (e.g. on localhost).
        if tier and user.plan_tier != tier:
            now = utcnow()
            customer_code = (d.get('customer') or {}).get('customer_code')

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
            logger.info('Plan activated via verify: user=%s tier=%s', user.id, tier)

        # Record coupon use if one was applied (idempotent — skip if already recorded)
        coupon_id = (d.get('metadata') or {}).get('coupon_id')
        if coupon_id and tier:
            BillingService._record_coupon_use(coupon_id, user.id, tier)

        return {'status': d['status'], 'tier': tier or user.plan_tier, 'reference': reference}

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
        if not secret:
            logger.error('PAYSTACK_WEBHOOK_SECRET is not set — rejecting all webhooks')
            return False
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
        metadata = data.get('metadata') or {}
        addon = metadata.get('addon')
        if addon == 'file_transfer':
            BillingService._on_addon_charge_success(data, addon)
            return

        plan_code = (data.get('plan') or {}).get('plan_code')
        if not plan_code:
            return  # one-time charge with no recognised addon — ignore

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

        coupon_id = (data.get('metadata') or {}).get('coupon_id')
        if coupon_id:
            BillingService._record_coupon_use(coupon_id, user.id, tier)

        try:
            from app.services.email_service import EmailService
            EmailService.send_subscription_confirmed(user.email, tier)
        except Exception:
            logger.exception('Failed to send subscription email to %s', user.email)

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
        user = sub.user
        user.plan_tier = 'free'
        db.session.commit()
        sse_manager.publish(user.id, 'plan_changed', {'plan': 'free'})

        try:
            from app.services.email_service import EmailService
            EmailService.send_subscription_cancelled(user.email)
        except Exception:
            logger.exception('Failed to send cancellation email for sub=%s', sub_code)

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
            try:
                from app.services.email_service import EmailService
                EmailService.send_payment_failed(sub.user.email)
            except Exception:
                logger.exception('Failed to send payment-failed email for sub=%s', sub_code)

    @staticmethod
    def _on_addon_charge_success(data: dict, addon: str) -> None:
        metadata = data.get('metadata') or {}
        user_id = metadata.get('user_id')
        if not user_id:
            return

        user = db.session.get(User, user_id)
        if not user:
            return

        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        ).scalar_one_or_none()
        if not sub:
            return

        if addon == 'file_transfer' and not sub.file_transfer_addon:
            sub.file_transfer_addon = True
            db.session.commit()
            logger.info('File transfer addon activated via webhook: user=%s', user_id)
            sse_manager.publish(user_id, 'addon_activated', {'addon': addon})

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _record_coupon_use(coupon_id: str, user_id: str, tier: str) -> None:
        """Increment coupon.current_uses and write a CouponUse row. Idempotent."""
        try:
            existing = db.session.execute(
                select(CouponUse).where(
                    CouponUse.coupon_id == coupon_id,
                    CouponUse.user_id == user_id,
                )
            ).scalar_one_or_none()
            if existing:
                return  # already recorded (verify + webhook both fire)

            coupon = db.session.get(Coupon, coupon_id)
            if not coupon:
                return

            db.session.add(CouponUse(coupon_id=coupon_id, user_id=user_id, tier=tier))
            coupon.current_uses += 1
            db.session.commit()
            logger.info('Coupon use recorded: coupon=%s user=%s tier=%s', coupon_id, user_id, tier)
        except Exception:
            logger.exception('Failed to record coupon use: coupon=%s user=%s', coupon_id, user_id)

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
