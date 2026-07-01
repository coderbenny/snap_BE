from functools import wraps

from flask import g

from app.middleware.auth_middleware import require_auth
from app.utils.errors import forbidden


def require_admin(f):
    """Require the caller to be authenticated AND have is_admin=True."""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not g.current_user.is_admin:
            return forbidden('Admin access required')
        return f(*args, **kwargs)
    return decorated
