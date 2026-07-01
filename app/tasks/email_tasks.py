import logging
from datetime import timedelta

from sqlalchemy import select

from app.celery_app import celery
from app.extensions import db
from app.models.subscription import Subscription
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_WARNING_WINDOW_DAYS = 4  # warn when expiry is within this many days
_WARNING_FLOOR_DAYS = 1   # don't warn on the last day (let expiry email handle it)


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    name='app.tasks.email_tasks.send_expiry_warnings',
)
def send_expiry_warnings(self):
    """Send a one-time expiry-warning email to subscribers expiring in 2–4 days."""
    from app.services.email_service import EmailService

    now = utcnow()
    window_start = now + timedelta(days=_WARNING_FLOOR_DAYS)
    window_end = now + timedelta(days=_WARNING_WINDOW_DAYS)

    subs = db.session.execute(
        select(Subscription).where(
            Subscription.status == 'active',
            Subscription.expires_at >= window_start,
            Subscription.expires_at <= window_end,
            Subscription.expiry_warning_sent_at.is_(None),
        )
    ).scalars().all()

    sent = 0
    for sub in subs:
        try:
            EmailService.send_expiry_warning(sub.user.email, sub.expires_at)
            sub.expiry_warning_sent_at = now
            db.session.commit()
            sent += 1
        except Exception:
            logger.exception(
                'Failed to send expiry warning for sub=%s user=%s', sub.id, sub.user_id
            )
            db.session.rollback()

    logger.info('send_expiry_warnings: sent=%d checked=%d', sent, len(subs))
    return {'sent': sent, 'checked': len(subs)}


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    name='app.tasks.email_tasks.send_broadcast',
)
def send_broadcast(self, emails: list, subject: str, body_html: str):
    """Send a broadcast email to the given list of addresses."""
    from app.services.email_service import EmailService

    sent = 0
    failed = 0
    for email in emails:
        try:
            EmailService._send(email, subject, body_html)
            sent += 1
        except Exception:
            logger.exception('broadcast: failed to send to %s', email)
            failed += 1

    logger.info('send_broadcast: sent=%d failed=%d subject=%r', sent, failed, subject)
    return {'sent': sent, 'failed': failed}
