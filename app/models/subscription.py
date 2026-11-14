import uuid
from datetime import timedelta

from app.extensions import db
from app.utils.time import utcnow

# Grace for Paystack webhook lag before a lapsed subscription loses access.
EXPIRY_GRACE = timedelta(days=3)


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        nullable=False,
        index=True,
    )
    tier = db.Column(
        db.Enum('pro', 'pro_ai', 'team', name='sub_tier'),
        nullable=False,
    )
    status = db.Column(
        db.Enum('active', 'past_due', 'cancelled', 'trialing', name='sub_status'),
        nullable=False,
        default='active',
    )
    paystack_customer_code = db.Column(db.String(100), nullable=True)   # CUS_xxx
    paystack_sub_code = db.Column(db.String(100), nullable=True, index=True)  # SUB_xxx
    expires_at = db.Column(db.DateTime, nullable=False)
    expiry_warning_sent_at = db.Column(db.DateTime, nullable=True)
    file_transfer_addon = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship('User', back_populates='subscription')

    def is_lapsed(self, now=None) -> bool:
        """True when the period ended past the grace window and Paystack is not
        carrying the subscription (no sub code, or it is past_due/cancelled)."""
        now = now or utcnow()
        if self.expires_at >= now - EXPIRY_GRACE:
            return False
        return self.paystack_sub_code is None or self.status in ('past_due', 'cancelled')
