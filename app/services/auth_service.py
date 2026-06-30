import logging

import jwt
from flask import current_app
from sqlalchemy import delete, select

from app.extensions import db
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class AuthService:

    @staticmethod
    def register(email: str, password: str) -> User:
        existing = db.session.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()
        if existing:
            raise ValueError('EMAIL_EXISTS')

        user = User(email=email.lower())
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        try:
            from app.services.email_service import EmailService
            EmailService.send_welcome(user.email)
        except Exception:
            logger.exception('Failed to send welcome email to %s', user.email)

        try:
            AuthService.send_verification(user)
        except Exception:
            logger.exception('Failed to send verification email to %s', user.email)

        return user

    @staticmethod
    def login(email: str, password: str) -> tuple[str, str]:
        user = db.session.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()

        if not user or not user.check_password(password):
            raise ValueError('INVALID_CREDENTIALS')

        access_token = AuthService._build_access_token(user)
        refresh_token = AuthService._create_refresh_token(user)
        return access_token, refresh_token

    @staticmethod
    def refresh(raw_token: str) -> str:
        token_hash = RefreshToken.hash(raw_token)
        record = db.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if not record or not record.is_valid:
            raise ValueError('INVALID_REFRESH_TOKEN')

        return AuthService._build_access_token(record.user)

    @staticmethod
    def logout(raw_token: str) -> None:
        token_hash = RefreshToken.hash(raw_token)
        record = db.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if record and record.revoked_at is None:
            record.revoked_at = utcnow()
            db.session.commit()

    # ── Password reset ────────────────────────────────────────────────────────

    @staticmethod
    def forgot_password(email: str) -> None:
        """Generate a reset token and send the email.

        Always returns silently — never reveals whether the email exists.
        """
        from datetime import timedelta

        from app.services.email_service import EmailService

        user = db.session.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()

        if not user:
            return  # silent — no enumeration

        raw = PasswordResetToken.generate()
        record = PasswordResetToken(
            user_id=user.id,
            token_hash=PasswordResetToken.hash(raw),
            expires_at=utcnow() + timedelta(hours=1),
        )
        db.session.add(record)
        db.session.commit()

        reset_url = (
            f"{current_app.config.get('FRONTEND_URL', 'https://snapit.ink')}"
            f"/reset-password?token={raw}"
        )
        EmailService.send_password_reset(user.email, reset_url)

    @staticmethod
    def reset_password(raw_token: str, new_password: str) -> None:
        token_hash = PasswordResetToken.hash(raw_token)
        record = db.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if not record or not record.is_valid:
            raise ValueError('INVALID_OR_EXPIRED_TOKEN')

        record.user.set_password(new_password)
        record.used_at = utcnow()

        # Revoke all existing refresh tokens — forces re-login on all devices.
        db.session.execute(
            delete(RefreshToken).where(RefreshToken.user_id == record.user_id)
        )
        db.session.commit()

    # ── Email verification ────────────────────────────────────────────────────

    @staticmethod
    def send_verification(user: User) -> None:
        from datetime import timedelta

        from app.services.email_service import EmailService

        # Replace any existing unused token for this user.
        db.session.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id
            )
        )

        raw = EmailVerificationToken.generate()
        record = EmailVerificationToken(
            user_id=user.id,
            token_hash=EmailVerificationToken.hash(raw),
            expires_at=utcnow() + timedelta(hours=24),
        )
        db.session.add(record)
        db.session.commit()

        verify_url = (
            f"{current_app.config.get('FRONTEND_URL', 'https://snapit.ink')}"
            f"/verify-email?token={raw}"
        )
        EmailService.send_verification(user.email, verify_url)

    @staticmethod
    def verify_email(raw_token: str) -> None:
        token_hash = EmailVerificationToken.hash(raw_token)
        record = db.session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash
            )
        ).scalar_one_or_none()

        if not record or not record.is_valid:
            raise ValueError('INVALID_OR_EXPIRED_TOKEN')

        record.user.verified_at = utcnow()
        record.used_at = utcnow()
        db.session.commit()

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_access_token(user: User) -> str:
        now = utcnow()
        payload = {
            'sub': user.id,
            'plan_tier': user.plan_tier,
            'iat': now,
            'exp': now + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
        }
        return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def _create_refresh_token(user: User) -> str:
        raw = RefreshToken.generate()
        record = RefreshToken(
            user_id=user.id,
            token_hash=RefreshToken.hash(raw),
            expires_at=utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'],
        )
        db.session.add(record)
        db.session.commit()
        return raw
