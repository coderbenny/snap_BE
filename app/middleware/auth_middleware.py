from functools import wraps

import jwt
from flask import current_app, g, request

from app.extensions import db
from app.models.user import User
from app.utils.errors import unauthorized


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return unauthorized()

        token = auth_header[7:]
        try:
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256'],
            )
        except jwt.ExpiredSignatureError:
            return unauthorized('Token has expired')
        except jwt.InvalidTokenError:
            return unauthorized('Invalid token')

        user = db.session.get(User, payload['sub'])
        if not user:
            return unauthorized()

        g.current_user = user
        return f(*args, **kwargs)

    return decorated
