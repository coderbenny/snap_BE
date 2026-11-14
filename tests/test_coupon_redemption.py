"""F-03: free-coupon redemption must be single-use per user, bounded by
max_uses, and must never clobber a paying Paystack subscription."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.coupon import Coupon, CouponUse
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_service import BillingService
from app.utils.time import utcnow
from tests.test_sync import register_and_login


@pytest.fixture
def user(client):
    register_and_login(client)
    return db.session.execute(
        select(User).where(User.email == 'test@example.com')
    ).scalar_one()


def _coupon(code='FREE100', max_uses=None, tier=None):
    c = Coupon(
        code=code, discount_type='percentage', discount_value=100,
        max_uses=max_uses, tier_restriction=tier,
        valid_from=utcnow() - timedelta(days=1),
    )
    db.session.add(c)
    db.session.commit()
    return c


def _redeem(user, code='FREE100', tier='pro'):
    with patch('app.services.billing_service.sse_manager'), \
         patch('app.services.email_service.EmailService.send_subscription_confirmed'):
        return BillingService.initialize_transaction(user, tier, None, coupon_code=code)


@pytest.fixture(autouse=True)
def plans(app):
    app.config['PAYSTACK_PLANS'] = {'pro': 'PLN_pro', 'pro_ai': 'PLN_ai', 'team': 'PLN_team'}


class TestReuse:
    def test_same_user_cannot_redeem_twice(self, user):
        c = _coupon()
        assert _redeem(user)['free'] is True
        with pytest.raises(ValueError, match='already'):
            _redeem(user, tier='pro_ai')
        db.session.expire_all()
        assert db.session.get(Coupon, c.id).current_uses == 1
        assert db.session.get(User, user.id).plan_tier == 'pro'

    def test_max_uses_enforced_for_distinct_users(self, user):
        c = _coupon(max_uses=1)
        c.current_uses = 1
        db.session.commit()
        with pytest.raises(ValueError, match='usage limit'):
            _redeem(user)


class TestPaidSubscriptionProtected:
    def test_active_paystack_sub_is_not_overwritten(self, user):
        _coupon()
        user.plan_tier = 'pro_ai'
        db.session.add(Subscription(
            user_id=user.id, tier='pro_ai', status='active',
            paystack_sub_code='SUB_real', expires_at=utcnow() + timedelta(days=20),
        ))
        db.session.commit()
        with pytest.raises(ValueError, match='active subscription'):
            _redeem(user)
        db.session.expire_all()
        sub = db.session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one()
        assert sub.paystack_sub_code == 'SUB_real'
        assert sub.tier == 'pro_ai'
        assert db.session.execute(select(CouponUse)).first() is None

    def test_cancelled_paystack_sub_may_use_coupon(self, user):
        _coupon()
        db.session.add(Subscription(
            user_id=user.id, tier='pro', status='cancelled',
            paystack_sub_code='SUB_old', expires_at=utcnow() - timedelta(days=10),
        ))
        db.session.commit()
        assert _redeem(user)['free'] is True


class TestAtomicAndConstrained:
    def test_unique_constraint_on_coupon_user(self, user):
        c = _coupon()
        db.session.add(CouponUse(coupon_id=c.id, user_id=user.id, tier='pro'))
        db.session.commit()
        db.session.add(CouponUse(coupon_id=c.id, user_id=user.id, tier='pro'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_stale_read_cannot_exceed_max_uses(self, user):
        """Validation passes on a stale row (the race); the conditional
        UPDATE at redemption time must still refuse."""
        c = _coupon(max_uses=1)
        other = User(email='other@example.com', password_hash='x')
        db.session.add(other)
        db.session.commit()
        stale_validate = BillingService._validate_coupon_for_tier
        with patch.object(
            BillingService, '_validate_coupon_for_tier',
            side_effect=lambda *a, **k: stale_validate(*a, **k),
        ):
            _redeem(other)  # takes the only slot
            with patch.object(
                BillingService, '_validate_coupon_for_tier',
                return_value=db.session.get(Coupon, c.id),
            ):
                with pytest.raises(ValueError, match='usage limit'):
                    _redeem(user)
        db.session.expire_all()
        assert db.session.get(Coupon, c.id).current_uses == 1
        assert db.session.get(User, user.id).plan_tier == 'free'
