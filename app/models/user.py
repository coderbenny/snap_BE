import uuid
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    plan_tier = db.Column(
        db.Enum('free', 'pro', 'pro_ai', 'team', name='plan_tier'),
        nullable=False,
        default='free',
    )
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    devices = db.relationship('Device', back_populates='user', cascade='all, delete-orphan')
    refresh_tokens = db.relationship('RefreshToken', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:260000')

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
