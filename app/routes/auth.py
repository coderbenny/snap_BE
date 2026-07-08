from flask import Blueprint, g, request
from marshmallow import ValidationError

from app.extensions import limiter
from app.middleware.auth_middleware import require_auth
from app.schemas.auth_schemas import (
    ForgotPasswordSchema,
    LoginSchema,
    LogoutSchema,
    RefreshSchema,
    RegisterSchema,
    ResetPasswordSchema,
    VerifyEmailSchema,
)
from app.services.auth_service import AuthService
from app.utils.errors import bad_request, conflict, unauthorized, validation_failed
from app.utils.feature_gate import can_use_file_transfer

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

_register_schema = RegisterSchema()
_login_schema = LoginSchema()
_refresh_schema = RefreshSchema()
_logout_schema = LogoutSchema()
_forgot_schema = ForgotPasswordSchema()
_reset_schema = ResetPasswordSchema()
_verify_schema = VerifyEmailSchema()


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
    except ValueError as e:
        if str(e) == 'EMAIL_NOT_VERIFIED':
            return bad_request(
                'Please verify your email before signing in. '
                'Check your inbox for the verification link.'
            )
        if str(e) == 'ACCOUNT_DISABLED':
            return bad_request('Your account has been disabled. Contact support@snapit.ink.')
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


@auth_bp.get('/me')
@require_auth
def me():
    user = g.current_user
    sub = user.subscription
    return {
        'id': user.id,
        'email': user.email,
        'plan': user.plan_tier,
        'verified': user.verified_at is not None,
        'is_admin': user.is_admin,
        'file_transfer_addon': can_use_file_transfer(user),
    }


# ── Password reset ────────────────────────────────────────────────────────────

@auth_bp.post('/resend-verification')
@limiter.limit('5 per hour')
def resend_verification():
    try:
        data = _forgot_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    AuthService.resend_verification(data['email'])
    return {'message': 'If that address is unverified you will receive a new link shortly.'}


@auth_bp.post('/forgot-password')
@limiter.limit('5 per hour')
def forgot_password():
    try:
        data = _forgot_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    # Always succeeds — never reveals whether the email exists.
    AuthService.forgot_password(data['email'])
    return {'message': 'If that email is registered you will receive a reset link shortly.'}


@auth_bp.post('/reset-password')
@limiter.limit('10 per hour')
def reset_password():
    try:
        data = _reset_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        AuthService.reset_password(data['token'], data['password'])
    except ValueError:
        return bad_request('This reset link is invalid or has expired. Please request a new one.')

    return {'message': 'Password updated successfully. You can now sign in.'}


# ── Email verification ────────────────────────────────────────────────────────

@auth_bp.post('/send-verification')
@require_auth
@limiter.limit('5 per hour')
def send_verification():
    user = g.current_user
    if user.verified_at is not None:
        return {'message': 'Email already verified.'}

    AuthService.send_verification(user)
    return {'message': 'Verification email sent.'}


@auth_bp.post('/verify-email')
@limiter.limit('20 per hour')
def verify_email():
    try:
        data = _verify_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        AuthService.verify_email(data['token'])
    except ValueError:
        return bad_request('This verification link is invalid or has expired.')

    return {'message': 'Email verified successfully.'}
