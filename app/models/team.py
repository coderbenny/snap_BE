import secrets
import uuid

from app.extensions import db
from app.utils.time import utcnow


class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    members = db.relationship('TeamMember', back_populates='team', cascade='all, delete-orphan')
    snippets = db.relationship('SharedSnippet', back_populates='team', cascade='all, delete-orphan')
    invites = db.relationship('TeamInvite', back_populates='team', cascade='all, delete-orphan')


class TeamMember(db.Model):
    __tablename__ = 'team_members'

    team_id = db.Column(
        db.String(36),
        db.ForeignKey('teams.id', ondelete='CASCADE'),
        primary_key=True,
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    role = db.Column(
        db.Enum('owner', 'member', name='member_role'),
        nullable=False,
    )
    joined_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    team = db.relationship('Team', back_populates='members')


class SharedSnippet(db.Model):
    __tablename__ = 'shared_snippets'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = db.Column(
        db.String(36),
        db.ForeignKey('teams.id', ondelete='CASCADE'),
        nullable=False,
    )
    title = db.Column(db.String(255), nullable=False)
    ciphertext = db.Column(db.Text, nullable=False)   # base64-encoded AES-256-GCM
    iv = db.Column(db.String(24), nullable=False)      # base64-encoded 12-byte nonce
    tags = db.Column(db.JSON, nullable=True)
    created_by = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    synced_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    team = db.relationship('Team', back_populates='snippets')

    __table_args__ = (
        db.Index('ix_shared_snippets_team_synced', 'team_id', 'synced_at'),
    )


class TeamInvite(db.Model):
    __tablename__ = 'team_invites'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = db.Column(
        db.String(36),
        db.ForeignKey('teams.id', ondelete='CASCADE'),
        nullable=False,
    )
    email = db.Column(db.String(255), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    team = db.relationship('Team', back_populates='invites')

    @property
    def is_valid(self) -> bool:
        return self.accepted_at is None and utcnow() < self.expires_at

    @staticmethod
    def generate() -> str:
        return secrets.token_hex(32)
