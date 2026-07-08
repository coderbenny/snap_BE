from app.extensions import db
from app.utils.time import utcnow


class ClipboardItem(db.Model):
    __tablename__ = 'clipboard_items'

    id = db.Column(db.String(36), primary_key=True)  # UUID assigned by client
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    device_id = db.Column(
        db.String(36),
        db.ForeignKey('devices.id', ondelete='SET NULL'),
        nullable=True,
    )
    ciphertext = db.Column(db.Text, nullable=False)         # base64-encoded AES-256-GCM ciphertext
    iv = db.Column(db.String(24), nullable=False)           # base64-encoded 12-byte nonce
    content_type = db.Column(
        db.Enum('text', 'image', 'url', 'file', name='content_type'),
        nullable=False,
        default='text',
    )
    tags = db.Column(db.JSON, nullable=True)
    pinned = db.Column(db.Boolean, nullable=False, default=False)
    client_created_at = db.Column(db.BigInteger, nullable=False)  # Unix ms, client-assigned
    synced_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index('ix_clipboard_items_user_synced', 'user_id', 'synced_at'),
        db.Index('ix_clipboard_items_user_deleted', 'user_id', 'deleted_at'),
    )
