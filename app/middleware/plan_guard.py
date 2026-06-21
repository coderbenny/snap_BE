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
            user_tier = g.current_user.plan_tier
            if user_tier not in tiers:
                return forbidden(
                    'This feature requires a Pro subscription — '
                    'upgrade at https://snapapp.io/billing'
                )
            return f(*args, **kwargs)
        return decorated
    return decorator
