import uuid

from app.extensions import db
from app.utils.time import utcnow


class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    discount_type = db.Column(
        db.Enum('percentage', 'fixed_usd_cents', name='discount_type'),
        nullable=False,
    )
    # percentage: 0-100; fixed_usd_cents: amount in cents (e.g. 500 = $5.00)
    discount_value = db.Column(db.Integer, nullable=False)
    max_uses = db.Column(db.Integer, nullable=True)   # null = unlimited
    current_uses = db.Column(db.Integer, nullable=False, default=0)
    # null = applies to any tier
    tier_restriction = db.Column(
        db.Enum('pro', 'pro_ai', 'team', name='coupon_tier'),
        nullable=True,
    )
    valid_from = db.Column(db.DateTime, nullable=False, default=utcnow)
    valid_until = db.Column(db.DateTime, nullable=True)   # null = no expiry
    created_by = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    uses = db.relationship('CouponUse', back_populates='coupon', cascade='all, delete-orphan')


class CouponUse(db.Model):
    __tablename__ = 'coupon_uses'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    coupon_id = db.Column(
        db.String(36),
        db.ForeignKey('coupons.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    tier = db.Column(
        db.Enum('pro', 'pro_ai', 'team', name='coupon_use_tier'),
        nullable=True,
    )
    used_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    coupon = db.relationship('Coupon', back_populates='uses')
