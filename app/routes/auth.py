from flask import Blueprint, request
from marshmallow import ValidationError

from app.extensions import limiter
from app.schemas.auth_schemas import LoginSchema, LogoutSchema, RefreshSchema, RegisterSchema
from app.services.auth_service import AuthService
from app.utils.errors import conflict, unauthorized, validation_failed

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

_register_schema = RegisterSchema()
_login_schema = LoginSchema()
_refresh_schema = RefreshSchema()
_logout_schema = LogoutSchema()


@auth_bp.post('/register')
@limiter.limit('10 per minute')
def register():
    try:
        data = _register_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        user = AuthService.register(data['email'], data['password'])
    except ValueError as e:
        if str(e) == 'EMAIL_EXISTS':
            return conflict('Email already in use — sign in instead')
        raise

    return {'message': 'Account created successfully', 'user_id': user.id}, 201


@auth_bp.post('/login')
@limiter.limit('10 per minute')
def login():
    try:
        data = _login_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        access_token, refresh_token = AuthService.login(data['email'], data['password'])
    except ValueError:
        return unauthorized('Invalid email or password')

    return {'access_token': access_token, 'refresh_token': refresh_token}


@auth_bp.post('/refresh')
@limiter.limit('30 per minute')
def refresh():
    try:
        data = _refresh_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        access_token = AuthService.refresh(data['refresh_token'])
    except ValueError:
        return unauthorized('Invalid or expired refresh token')

    return {'access_token': access_token}


@auth_bp.post('/logout')
def logout():
    try:
        data = _logout_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    AuthService.logout(data['refresh_token'])
    return '', 204
