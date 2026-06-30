
from app.extensions import db
from app.utils.time import utcnow


class Device(db.Model):
    __tablename__ = 'devices'

    # Client-supplied stable UUID (stored in Keychain / DPAPI on the device).
    # Used as the primary key so upserts are trivial.
    id = db.Column(db.String(36), primary_key=True)
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
    app_version = db.Column(db.String(20), nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship('User', back_populates='devices')
