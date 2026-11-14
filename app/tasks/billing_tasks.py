import logging

from sqlalchemy import or_, select

from app.celery_app import celery
from app.extensions import db
from app.models.subscription import EXPIRY_GRACE, Subscription
from app.services.sse_manager import sse_manager
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    name='app.tasks.billing_tasks.downgrade_expired_subscriptions',
)
def downgrade_expired_subscriptions(self=None):
    """Downgrade users whose subscription lapsed and is not carried by Paystack."""
    cutoff = utcnow() - EXPIRY_GRACE
    subs = db.session.execute(
        select(Subscription).where(
            Subscription.expires_at < cutoff,
            or_(
                Subscription.paystack_sub_code.is_(None),
                Subscription.status.in_(('past_due', 'cancelled')),
            ),
        )
    ).scalars().all()

    downgraded = 0
    for sub in subs:
        user = sub.user
        if user.plan_tier == 'free' and sub.status == 'cancelled':
            continue
        sub.status = 'cancelled'
        user.plan_tier = 'free'
        db.session.commit()
        sse_manager.publish(user.id, 'plan_changed', {'plan': 'free'})
        downgraded += 1

    logger.info('downgrade_expired_subscriptions: downgraded=%d checked=%d', downgraded, len(subs))
    return {'downgraded': downgraded, 'checked': len(subs)}
