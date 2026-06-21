import hashlib
import secrets
import uuid
from datetime import datetime

from app.extensions import db


class RefreshToken(db.Model):
    __tablename__ = 'refresh_tokens'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', back_populates='refresh_tokens')

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None and datetime.utcnow() < self.expires_at

    @staticmethod
    def generate() -> str:
        return secrets.token_hex(32)

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
