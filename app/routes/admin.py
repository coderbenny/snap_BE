import logging
import uuid
from datetime import datetime

from flask import Blueprint, g, request
from sqlalchemy import func, select

from app.extensions import db
from app.middleware.admin_middleware import require_admin
from app.models.coupon import Coupon, CouponUse
from app.models.device import Device
from app.models.subscription import Subscription
from app.models.user import User
from app.utils.errors import bad_request, conflict, not_found, server_error

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_TIER_PRICES = {'pro': 500, 'pro_ai': 900, 'team': 800}  # USD cents / month


# ── Overview ──────────────────────────────────────────────────────────────────

@admin_bp.get('/stats')
@require_admin
def get_stats():
    total_users = db.session.scalar(select(func.count(User.id)))
    active_users = db.session.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
    verified_users = db.session.scalar(
        select(func.count(User.id)).where(User.verified_at.isnot(None))
    )

    by_plan = db.session.execute(
        select(User.plan_tier, func.count(User.id)).group_by(User.plan_tier)
    ).all()
    plan_counts = {row[0]: row[1] for row in by_plan}

    active_subs = db.session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == 'active')
    )
    past_due_subs = db.session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == 'past_due')
    )

    # Estimated MRR from active subscriptions
    mrr = 0
    active_sub_rows = db.session.execute(
        select(Subscription.tier).where(Subscription.status == 'active')
    ).scalars().all()
    for tier in active_sub_rows:
        mrr += _TIER_PRICES.get(tier, 0)

    total_devices = db.session.scalar(select(func.count(Device.id)))

    return {
        'users': {
            'total': total_users,
            'active': active_users,
            'verified': verified_users,
            'by_plan': plan_counts,
        },
        'subscriptions': {
            'active': active_subs,
            'past_due': past_due_subs,
            'mrr_usd_cents': mrr,
        },
        'devices': {
            'total': total_devices,
        },
    }


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.get('/users')
@require_admin
def list_users():
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 25)))
    search = (request.args.get('search') or '').strip()
    plan_filter = request.args.get('plan')
    verified_filter = request.args.get('verified')

    q = select(User).order_by(User.created_at.desc())

    if search:
        q = q.where(User.email.ilike(f'%{search}%'))
    if plan_filter:
        q = q.where(User.plan_tier == plan_filter)
    if verified_filter == 'true':
        q = q.where(User.verified_at.isnot(None))
    elif verified_filter == 'false':
        q = q.where(User.verified_at.is_(None))

    total = db.session.scalar(select(func.count()).select_from(q.subquery()))
    users = db.session.execute(q.limit(per_page).offset((page - 1) * per_page)).scalars().all()

    return {
        'users': [_serialize_user(u) for u in users],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


@admin_bp.get('/users/<user_id>')
@require_admin
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return not_found('User not found')

    sub = db.session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    ).scalar_one_or_none()

    devices = db.session.execute(
        select(Device).where(Device.user_id == user_id).order_by(Device.last_seen_at.desc())
    ).scalars().all()

    return {
        'user': _serialize_user(user),
        'subscription': _serialize_sub(sub) if sub else None,
        'devices': [_serialize_device(d) for d in devices],
    }


@admin_bp.patch('/users/<user_id>')
@require_admin
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return not_found('User not found')

    # Prevent self-demotion (admin removing their own admin flag)
    body = request.get_json(silent=True) or {}

    if 'is_active' in body:
        user.is_active = bool(body['is_active'])

    if 'is_admin' in body:
        if user.id == g.current_user.id and not body['is_admin']:
            return bad_request('You cannot remove your own admin privileges')
        user.is_admin = bool(body['is_admin'])

    if 'plan_tier' in body:
        tier = body['plan_tier']
        if tier not in ('free', 'pro', 'pro_ai', 'team'):
            return bad_request(f"Invalid tier '{tier}'")
        user.plan_tier = tier

    db.session.commit()
    logger.info('admin.update_user: admin=%s target=%s body=%s', g.current_user.id, user_id, body)
    return {'user': _serialize_user(user)}


@admin_bp.delete('/users/<user_id>')
@require_admin
def delete_user(user_id):
    if user_id == g.current_user.id:
        return bad_request('You cannot delete your own account from the admin panel')

    user = db.session.get(User, user_id)
    if not user:
        return not_found('User not found')

    db.session.delete(user)
    db.session.commit()
    logger.info('admin.delete_user: admin=%s deleted=%s', g.current_user.id, user_id)
    return '', 204


# ── Subscriptions ─────────────────────────────────────────────────────────────

@admin_bp.get('/subscriptions')
@require_admin
def list_subscriptions():
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 25)))
    status_filter = request.args.get('status')
    tier_filter = request.args.get('tier')

    q = select(Subscription).order_by(Subscription.created_at.desc())
    if status_filter:
        q = q.where(Subscription.status == status_filter)
    if tier_filter:
        q = q.where(Subscription.tier == tier_filter)

    total = db.session.scalar(select(func.count()).select_from(q.subquery()))
    subs = db.session.execute(q.limit(per_page).offset((page - 1) * per_page)).scalars().all()

    return {
        'subscriptions': [_serialize_sub_with_user(s) for s in subs],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


@admin_bp.patch('/subscriptions/<sub_id>')
@require_admin
def update_subscription(sub_id):
    sub = db.session.get(Subscription, sub_id)
    if not sub:
        return not_found('Subscription not found')

    body = request.get_json(silent=True) or {}

    if 'status' in body:
        valid_statuses = ('active', 'past_due', 'cancelled', 'trialing')
        if body['status'] not in valid_statuses:
            return bad_request(f"Invalid status '{body['status']}'")
        sub.status = body['status']
        if body['status'] == 'cancelled':
            sub.user.plan_tier = 'free'

    if 'expires_at' in body:
        try:
            sub.expires_at = datetime.fromisoformat(body['expires_at'])
        except (ValueError, TypeError):
            return bad_request('Invalid expires_at format. Use ISO 8601.')

    if 'tier' in body:
        if body['tier'] not in ('pro', 'pro_ai', 'team'):
            return bad_request(f"Invalid tier '{body['tier']}'")
        sub.tier = body['tier']
        sub.user.plan_tier = body['tier']

    if 'file_transfer_addon' in body:
        sub.file_transfer_addon = bool(body['file_transfer_addon'])

    db.session.commit()
    logger.info('admin.update_subscription: admin=%s sub=%s', g.current_user.id, sub_id)
    return {'subscription': _serialize_sub(sub)}


# ── Devices ───────────────────────────────────────────────────────────────────

@admin_bp.get('/devices')
@require_admin
def list_devices():
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 25)))
    user_id = request.args.get('user_id')
    platform_filter = request.args.get('platform')

    q = select(Device).order_by(Device.last_seen_at.desc())
    if user_id:
        q = q.where(Device.user_id == user_id)
    if platform_filter:
        q = q.where(Device.platform == platform_filter)

    total = db.session.scalar(select(func.count()).select_from(q.subquery()))
    devices = db.session.execute(q.limit(per_page).offset((page - 1) * per_page)).scalars().all()

    return {
        'devices': [_serialize_device_with_user(d) for d in devices],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


@admin_bp.delete('/devices/<device_id>')
@require_admin
def delete_device(device_id):
    device = db.session.get(Device, device_id)
    if not device:
        return not_found('Device not found')

    db.session.delete(device)
    db.session.commit()
    logger.info('admin.delete_device: admin=%s device=%s', g.current_user.id, device_id)
    return '', 204


# ── Coupons ───────────────────────────────────────────────────────────────────

@admin_bp.get('/coupons')
@require_admin
def list_coupons():
    coupons = db.session.execute(
        select(Coupon).order_by(Coupon.created_at.desc())
    ).scalars().all()
    return {'coupons': [_serialize_coupon(c) for c in coupons]}


@admin_bp.post('/coupons')
@require_admin
def create_coupon():
    body = request.get_json(silent=True) or {}

    code = (body.get('code') or '').strip().upper()
    if not code:
        return bad_request('code is required')
    if len(code) > 50:
        return bad_request('code must be 50 characters or fewer')

    discount_type = body.get('discount_type')
    if discount_type not in ('percentage', 'fixed_usd_cents'):
        return bad_request("discount_type must be 'percentage' or 'fixed_usd_cents'")

    try:
        discount_value = int(body['discount_value'])
    except (KeyError, TypeError, ValueError):
        return bad_request('discount_value must be an integer')
    if discount_type == 'percentage' and not (1 <= discount_value <= 100):
        return bad_request('Percentage discount must be 1–100')
    if discount_type == 'fixed_usd_cents' and discount_value < 1:
        return bad_request('Fixed discount must be at least 1 cent')

    # Check for code uniqueness
    existing = db.session.execute(
        select(Coupon).where(Coupon.code == code)
    ).scalar_one_or_none()
    if existing:
        return conflict(f"Coupon code '{code}' already exists")

    max_uses = body.get('max_uses')
    if max_uses is not None:
        try:
            max_uses = int(max_uses)
            if max_uses < 1:
                return bad_request('max_uses must be at least 1')
        except (TypeError, ValueError):
            return bad_request('max_uses must be an integer or null')

    tier_restriction = body.get('tier_restriction')
    if tier_restriction and tier_restriction not in ('pro', 'pro_ai', 'team'):
        return bad_request("tier_restriction must be 'pro', 'pro_ai', 'team', or null")

    valid_until = None
    if body.get('valid_until'):
        try:
            valid_until = datetime.fromisoformat(body['valid_until'])
        except (ValueError, TypeError):
            return bad_request('valid_until must be an ISO 8601 datetime or null')

    coupon = Coupon(
        id=str(uuid.uuid4()),
        code=code,
        description=body.get('description'),
        discount_type=discount_type,
        discount_value=discount_value,
        max_uses=max_uses,
        tier_restriction=tier_restriction,
        valid_until=valid_until,
        created_by=g.current_user.id,
        is_active=True,
    )
    db.session.add(coupon)
    db.session.commit()
    logger.info('admin.create_coupon: admin=%s code=%s', g.current_user.id, code)
    return {'coupon': _serialize_coupon(coupon)}, 201


@admin_bp.patch('/coupons/<coupon_id>')
@require_admin
def update_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return not_found('Coupon not found')

    body = request.get_json(silent=True) or {}

    if 'is_active' in body:
        coupon.is_active = bool(body['is_active'])

    if 'description' in body:
        coupon.description = body['description']

    if 'max_uses' in body:
        max_uses = body['max_uses']
        if max_uses is not None:
            try:
                max_uses = int(max_uses)
                if max_uses < coupon.current_uses:
                    return bad_request(
                        f"max_uses cannot be less than current_uses ({coupon.current_uses})"
                    )
            except (TypeError, ValueError):
                return bad_request('max_uses must be an integer or null')
        coupon.max_uses = max_uses

    if 'valid_until' in body:
        if body['valid_until'] is None:
            coupon.valid_until = None
        else:
            try:
                coupon.valid_until = datetime.fromisoformat(body['valid_until'])
            except (ValueError, TypeError):
                return bad_request('valid_until must be an ISO 8601 datetime or null')

    db.session.commit()
    return {'coupon': _serialize_coupon(coupon)}


@admin_bp.delete('/coupons/<coupon_id>')
@require_admin
def delete_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return not_found('Coupon not found')

    if coupon.current_uses > 0:
        return bad_request(
            f"Cannot delete a coupon that has been used {coupon.current_uses} time(s). "
            'Deactivate it instead.'
        )

    db.session.delete(coupon)
    db.session.commit()
    return '', 204


@admin_bp.get('/coupons/<coupon_id>/uses')
@require_admin
def coupon_uses(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return not_found('Coupon not found')

    uses = db.session.execute(
        select(CouponUse).where(CouponUse.coupon_id == coupon_id).order_by(CouponUse.used_at.desc())
    ).scalars().all()

    return {
        'coupon': _serialize_coupon(coupon),
        'uses': [
            {
                'id': u.id,
                'user_id': u.user_id,
                'tier': u.tier,
                'used_at': u.used_at.isoformat(),
            }
            for u in uses
        ],
    }


# ── Broadcast ─────────────────────────────────────────────────────────────────

@admin_bp.post('/broadcast')
@require_admin
def broadcast():
    """Send a custom email to all users or a filtered subset.

    Body:
      subject: str (required)
      body_html: str (required) — HTML email body
      plan_filter: 'free' | 'pro' | 'pro_ai' | 'team' | null — only this tier
      verified_only: bool (default true)
    """
    body = request.get_json(silent=True) or {}

    subject = (body.get('subject') or '').strip()
    body_html = (body.get('body_html') or '').strip()
    if not subject:
        return bad_request('subject is required')
    if not body_html:
        return bad_request('body_html is required')

    plan_filter = body.get('plan_filter')
    verified_only = body.get('verified_only', True)

    q = select(User).where(User.is_active.is_(True))
    if plan_filter:
        q = q.where(User.plan_tier == plan_filter)
    if verified_only:
        q = q.where(User.verified_at.isnot(None))

    users = db.session.execute(q).scalars().all()
    emails = [u.email for u in users]

    if not emails:
        return bad_request('No users match the specified filters')

    try:
        from app.tasks.email_tasks import send_broadcast
        send_broadcast.delay(emails, subject, body_html)
    except Exception:
        logger.exception('admin.broadcast: failed to enqueue task')
        return server_error('Failed to enqueue broadcast. Please try again.')

    logger.info(
        'admin.broadcast: admin=%s subject=%r recipients=%d',
        g.current_user.id, subject, len(emails),
    )
    return {'queued': len(emails), 'subject': subject}


# ── System health ─────────────────────────────────────────────────────────────

@admin_bp.get('/system')
@require_admin
def system_health():
    status = {}

    # DB check
    try:
        db.session.execute(db.text('SELECT 1'))
        status['db'] = 'ok'
    except Exception as exc:
        status['db'] = f'error: {exc}'

    # Redis check
    try:
        from app.utils.redis_client import get_redis
        r = get_redis()
        r.ping()
        status['redis'] = 'ok'
    except Exception as exc:
        status['redis'] = f'error: {exc}'

    status['overall'] = 'ok' if all(v == 'ok' for v in status.values()) else 'degraded'
    return status


# ── Serializers ───────────────────────────────────────────────────────────────

def _serialize_user(u: User) -> dict:
    return {
        'id': u.id,
        'email': u.email,
        'plan_tier': u.plan_tier,
        'is_admin': u.is_admin,
        'is_active': u.is_active,
        'verified': u.verified_at is not None,
        'verified_at': u.verified_at.isoformat() if u.verified_at else None,
        'created_at': u.created_at.isoformat(),
    }


def _serialize_sub(s: Subscription) -> dict:
    return {
        'id': s.id,
        'user_id': s.user_id,
        'tier': s.tier,
        'status': s.status,
        'paystack_customer_code': s.paystack_customer_code,
        'paystack_sub_code': s.paystack_sub_code,
        'file_transfer_addon': bool(s.file_transfer_addon),
        'expires_at': s.expires_at.isoformat(),
        'created_at': s.created_at.isoformat(),
    }


def _serialize_sub_with_user(s: Subscription) -> dict:
    d = _serialize_sub(s)
    d['user_email'] = s.user.email if s.user else None
    return d


def _serialize_device(d: Device) -> dict:
    return {
        'id': d.id,
        'user_id': d.user_id,
        'name': d.name,
        'platform': d.platform,
        'app_version': d.app_version,
        'last_seen_at': d.last_seen_at.isoformat(),
        'created_at': d.created_at.isoformat(),
    }


def _serialize_device_with_user(d: Device) -> dict:
    result = _serialize_device(d)
    result['user_email'] = d.user.email if d.user else None
    return result


def _serialize_coupon(c: Coupon) -> dict:
    return {
        'id': c.id,
        'code': c.code,
        'description': c.description,
        'discount_type': c.discount_type,
        'discount_value': c.discount_value,
        'max_uses': c.max_uses,
        'current_uses': c.current_uses,
        'tier_restriction': c.tier_restriction,
        'valid_from': c.valid_from.isoformat(),
        'valid_until': c.valid_until.isoformat() if c.valid_until else None,
        'is_active': c.is_active,
        'created_at': c.created_at.isoformat(),
    }
