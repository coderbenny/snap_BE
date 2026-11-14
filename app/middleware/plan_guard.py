from functools import wraps

from flask import g

from app.utils.errors import forbidden

TIER_RANK = {'free': 0, 'pro': 1, 'pro_ai': 2, 'team': 3}


def require_plan(*tiers: str):
    """Gate a route behind one or more plan tiers.

    Usage: @require_plan('pro', 'pro_ai', 'team')
    The decorated route must also be wrapped with @require_auth.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = g.current_user
            user_tier = user.plan_tier
            sub = user.subscription
            if user_tier != 'free' and sub is not None and sub.is_lapsed():
                user_tier = 'free'  # expires_at is authoritative; the task catches up
            if user_tier not in tiers:
                return forbidden(
                    'This feature requires a Pro subscription — '
                    'upgrade at https://snapit.ink/billing'
                )
            return f(*args, **kwargs)
        return decorated
    return decorator
