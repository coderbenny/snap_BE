"""Tests for billing endpoints and Paystack webhook handling."""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from tests.conftest import VALID_EMAIL, VALID_PASSWORD

WEBHOOK_SECRET = 'test-webhook-secret'

# ── Helpers ───────────────────────────────────────────────────────────────────


def register_and_login(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    client.post('/auth/register', json={'email': email, 'password': password})
    res = client.post('/auth/login', json={'email': email, 'password': password})
    return {'Authorization': f"Bearer {res.get_json()['access_token']}"}


def get_user_id(app, email=VALID_EMAIL):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        user = db.session.execute(select(User).where(User.email == email)).scalar_one()
        return user.id


def get_user_tier(app, email=VALID_EMAIL):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        user = db.session.execute(select(User).where(User.email == email)).scalar_one()
        return user.plan_tier


def get_subscription(app, email=VALID_EMAIL):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.subscription import Subscription
    from app.models.user import User
    with app.app_context():
        user = db.session.execute(select(User).where(User.email == email)).scalar_one()
        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        if sub is None:
            return None
        return {
            'tier': sub.tier,
            'status': sub.status,
            'paystack_sub_code': sub.paystack_sub_code,
            'paystack_customer_code': sub.paystack_customer_code,
        }


def send_webhook(client, payload: dict):
    """Send a webhook request with a valid HMAC-SHA512 signature."""
    body = json.dumps(payload).encode()
    sig = hmac.new(
        key=WEBHOOK_SECRET.encode(),
        msg=body,
        digestmod=hashlib.sha512,
    ).hexdigest()
    return client.post(
        '/webhooks/paystack',
        data=body,
        content_type='application/json',
        headers={'x-paystack-signature': sig},
    )


def charge_success_payload(email=VALID_EMAIL, plan_code='PLN_test_pro', customer_code='CUS_test'):
    return {
        'event': 'charge.success',
        'data': {
            'reference': 'ref_test123',
            'status': 'success',
            'customer': {'email': email, 'customer_code': customer_code},
            'plan': {'plan_code': plan_code},
            'metadata': {},
        },
    }


def subscription_create_payload(
    email=VALID_EMAIL,
    sub_code='SUB_test123',
    customer_code='CUS_test',
    next_payment_date='2026-07-22T00:00:00.000Z',
):
    return {
        'event': 'subscription.create',
        'data': {
            'subscription_code': sub_code,
            'next_payment_date': next_payment_date,
            'customer': {'email': email, 'customer_code': customer_code},
        },
    }


def subscription_disable_payload(sub_code='SUB_test123'):
    return {
        'event': 'subscription.disable',
        'data': {'subscription_code': sub_code},
    }


def invoice_failed_payload(sub_code='SUB_test123'):
    return {
        'event': 'invoice.payment_failed',
        'data': {'subscription': {'subscription_code': sub_code}},
    }


# ── GET /billing/plans ────────────────────────────────────────────────────────

class TestGetPlans:
    def test_returns_three_plans(self, client):
        res = client.get('/billing/plans')
        assert res.status_code == 200
        plans = res.get_json()['plans']
        assert len(plans) == 3
        tiers = [p['tier'] for p in plans]
        assert 'pro' in tiers
        assert 'pro_ai' in tiers
        assert 'team' in tiers

    def test_no_auth_required(self, client):
        res = client.get('/billing/plans')
        assert res.status_code == 200

    def test_each_plan_has_required_fields(self, client):
        plans = client.get('/billing/plans').get_json()['plans']
        for plan in plans:
            assert 'tier' in plan
            assert 'name' in plan
            assert 'features' in plan
            assert isinstance(plan['features'], list)


# ── POST /billing/subscribe ───────────────────────────────────────────────────

class TestSubscribe:
    def test_returns_authorization_url(self, client, app):
        headers = register_and_login(client)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            'status': True,
            'data': {'authorization_url': 'https://paystack.com/pay/testref'},
        }
        with patch('app.services.billing_service.requests.post', return_value=mock_resp):
            res = client.post('/billing/subscribe', json={'tier': 'pro'}, headers=headers)

        assert res.status_code == 200
        assert res.get_json()['authorization_url'] == 'https://paystack.com/pay/testref'

    def test_with_callback_url(self, client):
        headers = register_and_login(client)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            'status': True,
            'data': {'authorization_url': 'https://paystack.com/pay/testref'},
        }
        target = 'app.services.billing_service.requests.post'
        with patch(target, return_value=mock_resp) as mock_post:
            client.post(
                '/billing/subscribe',
                json={'tier': 'pro', 'callback_url': 'https://snapapp.io/billing/success'},
                headers=headers,
            )
            call_kwargs = mock_post.call_args
            payload_sent = call_kwargs.kwargs.get('json') or call_kwargs.args[1]
            assert payload_sent.get('callback_url') == 'https://snapapp.io/billing/success'

    def test_invalid_tier(self, client):
        headers = register_and_login(client)
        res = client.post('/billing/subscribe', json={'tier': 'enterprise'}, headers=headers)
        assert res.status_code == 422

    def test_missing_tier(self, client):
        headers = register_and_login(client)
        res = client.post('/billing/subscribe', json={}, headers=headers)
        assert res.status_code == 422

    def test_unauthenticated(self, client):
        res = client.post('/billing/subscribe', json={'tier': 'pro'})
        assert res.status_code == 401

    def test_paystack_api_failure_returns_500(self, client):
        headers = register_and_login(client)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception('Network error')
        with patch('app.services.billing_service.requests.post', return_value=mock_resp):
            res = client.post('/billing/subscribe', json={'tier': 'pro'}, headers=headers)
        assert res.status_code == 500


# ── POST /billing/portal ──────────────────────────────────────────────────────

class TestPortal:
    def _create_subscription(self, app, email=VALID_EMAIL, sub_code='SUB_test123'):
        from datetime import timedelta

        from sqlalchemy import select

        from app.extensions import db
        from app.models.subscription import Subscription
        from app.models.user import User
        from app.utils.time import utcnow
        with app.app_context():
            user = db.session.execute(select(User).where(User.email == email)).scalar_one()
            db.session.add(Subscription(
                user_id=user.id,
                tier='pro',
                status='active',
                paystack_sub_code=sub_code,
                paystack_customer_code='CUS_test',
                expires_at=utcnow() + timedelta(days=30),
            ))
            db.session.commit()

    def test_returns_portal_url(self, client, app):
        headers = register_and_login(client)
        self._create_subscription(app)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            'status': True,
            'data': {'link': 'https://paystack.com/manage/subscriptions/test'},
        }
        with patch('app.services.billing_service.requests.get', return_value=mock_resp):
            res = client.post('/billing/portal', headers=headers)

        assert res.status_code == 200
        assert 'portal_url' in res.get_json()

    def test_no_subscription_returns_404(self, client):
        headers = register_and_login(client)
        res = client.post('/billing/portal', headers=headers)
        assert res.status_code == 404

    def test_unauthenticated(self, client):
        res = client.post('/billing/portal')
        assert res.status_code == 401


# ── POST /webhooks/paystack ───────────────────────────────────────────────────

class TestWebhook:
    def test_invalid_signature_rejected(self, client):
        payload = charge_success_payload()
        body = json.dumps(payload).encode()
        res = client.post(
            '/webhooks/paystack',
            data=body,
            content_type='application/json',
            headers={'x-paystack-signature': 'badsignature'},
        )
        assert res.status_code == 400

    def test_missing_signature_rejected(self, client):
        payload = charge_success_payload()
        body = json.dumps(payload).encode()
        res = client.post('/webhooks/paystack', data=body, content_type='application/json')
        assert res.status_code == 400

    def test_unknown_event_returns_200(self, client):
        payload = {'event': 'some.unknown.event', 'data': {}}
        res = send_webhook(client, payload)
        assert res.status_code == 200

    # ── charge.success ────────────────────────────────────────────────────────

    def test_charge_success_creates_subscription(self, client, app):
        register_and_login(client)
        res = send_webhook(client, charge_success_payload())
        assert res.status_code == 200

        sub = get_subscription(app)
        assert sub is not None
        assert sub['tier'] == 'pro'
        assert sub['status'] == 'active'

    def test_charge_success_upgrades_user_tier(self, client, app):
        register_and_login(client)
        assert get_user_tier(app) == 'free'

        send_webhook(client, charge_success_payload())
        assert get_user_tier(app) == 'pro'

    def test_charge_success_pro_ai_tier(self, client, app):
        register_and_login(client)
        send_webhook(client, charge_success_payload(plan_code='PLN_test_pro_ai'))
        assert get_user_tier(app) == 'pro_ai'

    def test_charge_success_no_plan_is_ignored(self, client, app):
        register_and_login(client)
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'ref_oneoff',
                'customer': {'email': VALID_EMAIL, 'customer_code': 'CUS_test'},
                'metadata': {},
            },
        }
        send_webhook(client, payload)
        assert get_user_tier(app) == 'free'  # no change

    def test_charge_success_unknown_user_ignored(self, client, app):
        res = send_webhook(client, charge_success_payload(email='ghost@example.com'))
        assert res.status_code == 200

    def test_charge_success_updates_existing_subscription(self, client, app):
        register_and_login(client)
        send_webhook(client, charge_success_payload(plan_code='PLN_test_pro'))
        send_webhook(client, charge_success_payload(plan_code='PLN_test_pro_ai'))

        sub = get_subscription(app)
        assert sub['tier'] == 'pro_ai'
        assert get_user_tier(app) == 'pro_ai'

    # ── subscription.create ───────────────────────────────────────────────────

    def test_subscription_create_sets_sub_code(self, client, app):
        register_and_login(client)
        send_webhook(client, charge_success_payload())
        send_webhook(client, subscription_create_payload(sub_code='SUB_real123'))

        sub = get_subscription(app)
        assert sub['paystack_sub_code'] == 'SUB_real123'

    def test_subscription_create_updates_expires_at(self, client, app):
        from sqlalchemy import select

        from app.extensions import db
        from app.models.subscription import Subscription
        from app.models.user import User

        register_and_login(client)
        send_webhook(client, charge_success_payload())
        next_date = '2026-07-22T00:00:00.000Z'
        send_webhook(client, subscription_create_payload(next_payment_date=next_date))

        with app.app_context():
            user = db.session.execute(
                select(User).where(User.email == VALID_EMAIL)
            ).scalar_one()
            sub = db.session.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            ).scalar_one()
            assert sub.expires_at.year == 2026
            assert sub.expires_at.month == 7
            assert sub.expires_at.day == 22

    # ── subscription.disable ─────────────────────────────────────────────────

    def test_subscription_disable_cancels_and_downgrades(self, client, app):
        register_and_login(client)
        send_webhook(client, charge_success_payload())
        send_webhook(client, subscription_create_payload(sub_code='SUB_cancel'))

        assert get_user_tier(app) == 'pro'

        send_webhook(client, subscription_disable_payload(sub_code='SUB_cancel'))

        sub = get_subscription(app)
        assert sub['status'] == 'cancelled'
        assert get_user_tier(app) == 'free'

    def test_subscription_disable_unknown_sub_code_ignored(self, client):
        res = send_webhook(client, subscription_disable_payload(sub_code='SUB_ghost'))
        assert res.status_code == 200

    # ── invoice.payment_failed ────────────────────────────────────────────────

    def test_invoice_payment_failed_marks_past_due(self, client, app):
        register_and_login(client)
        send_webhook(client, charge_success_payload())
        send_webhook(client, subscription_create_payload(sub_code='SUB_fail'))

        send_webhook(client, invoice_failed_payload(sub_code='SUB_fail'))

        sub = get_subscription(app)
        assert sub['status'] == 'past_due'

    def test_invoice_payment_failed_unknown_sub_ignored(self, client):
        res = send_webhook(client, invoice_failed_payload(sub_code='SUB_ghost'))
        assert res.status_code == 200
