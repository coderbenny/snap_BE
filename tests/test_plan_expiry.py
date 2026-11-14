"""F-01: lapsed subscriptions must lose paid access."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models.subscription import Subscription
from app.models.user import User
from app.utils.time import utcnow
from tests.test_sync import register_and_login


def _make_pro(email='test@example.com', *, expires_in, status='active', sub_code=None):
    user = db.session.execute(select(User).where(User.email == email)).scalar_one()
    user.plan_tier = 'pro'
    db.session.add(Subscription(
        user_id=user.id, tier='pro', status=status,
        paystack_sub_code=sub_code, expires_at=utcnow() + expires_in,
    ))
    db.session.commit()
    return user.id


@pytest.fixture
def headers(client):
    return register_and_login(client)


def _tier(user_id):
    db.session.expire_all()
    return db.session.get(User, user_id).plan_tier


class TestExpiryTask:
    def test_lapsed_coupon_sub_is_downgraded(self, headers):
        from app.tasks.billing_tasks import downgrade_expired_subscriptions
        uid = _make_pro(expires_in=timedelta(days=-4))
        result = downgrade_expired_subscriptions()
        assert result['downgraded'] == 1
        assert _tier(uid) == 'free'
        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == uid)
        ).scalar_one()
        assert sub.status == 'cancelled'

    def test_within_grace_period_is_kept(self, headers):
        from app.tasks.billing_tasks import downgrade_expired_subscriptions
        uid = _make_pro(expires_in=timedelta(days=-1))
        downgrade_expired_subscriptions()
        assert _tier(uid) == 'pro'

    def test_unexpired_is_kept(self, headers):
        from app.tasks.billing_tasks import downgrade_expired_subscriptions
        uid = _make_pro(expires_in=timedelta(days=10))
        downgrade_expired_subscriptions()
        assert _tier(uid) == 'pro'

    def test_active_paystack_sub_is_left_to_paystack(self, headers):
        from app.tasks.billing_tasks import downgrade_expired_subscriptions
        uid = _make_pro(expires_in=timedelta(days=-10), sub_code='SUB_x')
        downgrade_expired_subscriptions()
        assert _tier(uid) == 'pro'

    def test_past_due_paystack_sub_is_downgraded(self, headers):
        from app.tasks.billing_tasks import downgrade_expired_subscriptions
        uid = _make_pro(expires_in=timedelta(days=-10), status='past_due', sub_code='SUB_x')
        downgrade_expired_subscriptions()
        assert _tier(uid) == 'free'

    def test_task_is_scheduled(self, app):
        from app.celery_app import celery
        tasks = {v['task'] for v in celery.conf.beat_schedule.values()}
        assert 'app.tasks.billing_tasks.downgrade_expired_subscriptions' in tasks


class TestRequirePlanHonoursExpiry:
    def test_sync_403_after_expiry_without_task_run(self, client, headers):
        _make_pro(expires_in=timedelta(days=-4))
        assert client.get('/snap/sync', headers=headers).status_code == 403

    def test_sync_ok_when_current(self, client, headers):
        _make_pro(expires_in=timedelta(days=10))
        assert client.get('/snap/sync', headers=headers).status_code == 200
