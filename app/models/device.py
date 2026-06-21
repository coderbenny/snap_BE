import uuid
from datetime import datetime

from app.extensions import db


class Device(db.Model):
    __tablename__ = 'devices'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    platform = db.Column(
        db.Enum('macos', 'windows', 'android', 'ios', 'web', name='platform'),
        nullable=False,
    )
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', back_populates='devices')
