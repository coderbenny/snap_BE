import hashlib
from datetime import timedelta

from sqlalchemy import select

from app.extensions import db
from app.models.team import SharedSnippet, Team, TeamInvite, TeamMember
from app.models.user import User
from app.utils.time import from_unix_ms, utcnow

_INVITE_EXPIRY_DAYS = 7


class TeamService:

    @staticmethod
    def create(user: User, name: str) -> Team:
        now = utcnow()
        team = Team(name=name, owner_id=user.id, created_at=now)
        db.session.add(team)
        db.session.flush()  # populate team.id before creating membership

        db.session.add(TeamMember(
            team_id=team.id,
            user_id=user.id,
            role='owner',
            joined_at=now,
        ))
        db.session.commit()
        return team

    @staticmethod
    def list_for_user(user: User) -> list[dict]:
        rows = db.session.execute(
            select(Team, TeamMember.role)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user.id)
            .order_by(Team.created_at.asc())
        ).all()
        return [{'team': team, 'role': role} for team, role in rows]

    @staticmethod
    def get_membership(user: User, team_id: str) -> TeamMember | None:
        return db.session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user.id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def invite(user: User, team_id: str, email: str) -> str:
        """Create an invite for email. Returns the raw token.

        Raises PermissionError if user is not the team owner.
        Raises LookupError if team not found or user is not a member.
        Raises ValueError if invitee is already a member.
        """
        membership = TeamService.get_membership(user, team_id)
        if not membership:
            raise LookupError('Team not found')
        if membership.role != 'owner':
            raise PermissionError('Only the team owner can invite members')

        existing_member = db.session.execute(
            select(TeamMember)
            .join(User, User.id == TeamMember.user_id)
            .where(
                TeamMember.team_id == team_id,
                User.email == email.lower(),
            )
        ).scalar_one_or_none()
        if existing_member:
            raise ValueError('User is already a member of this team')

        # Expire any outstanding open invite for this address to prevent token
        # accumulation (old tokens could be replayed if the member later leaves).
        open_invite = db.session.execute(
            select(TeamInvite).where(
                TeamInvite.team_id == team_id,
                TeamInvite.email == email.lower(),
                TeamInvite.accepted_at.is_(None),
                TeamInvite.expires_at > utcnow(),
            )
        ).scalar_one_or_none()
        if open_invite:
            open_invite.expires_at = utcnow()

        raw = TeamInvite.generate()
        token_hash = hashlib.sha256(raw.encode()).hexdigest()

        db.session.add(TeamInvite(
            team_id=team_id,
            email=email.lower(),
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(days=_INVITE_EXPIRY_DAYS),
        ))
        db.session.commit()
        return raw

    @staticmethod
    def accept_invite(user: User, raw_token: str) -> TeamMember:
        """Accept a pending invite. Returns the new TeamMember record.

        Raises LookupError if token is invalid/expired/already used.
        Raises ValueError if user is already a member.
        """
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invite = db.session.execute(
            select(TeamInvite).where(TeamInvite.token_hash == token_hash)
        ).scalar_one_or_none()

        if not invite or not invite.is_valid:
            raise LookupError('Invite token is invalid or has expired')

        if invite.email != user.email.lower():
            raise LookupError('Invite token is invalid or has expired')

        existing = TeamService.get_membership(user, invite.team_id)
        if existing:
            raise ValueError('You are already a member of this team')

        now = utcnow()
        invite.accepted_at = now
        membership = TeamMember(
            team_id=invite.team_id,
            user_id=user.id,
            role='member',
            joined_at=now,
        )
        db.session.add(membership)
        db.session.commit()
        return membership

    @staticmethod
    def list_members(user: User, team_id: str) -> list[dict]:
        """Returns member list. Raises LookupError if user is not a member."""
        if not TeamService.get_membership(user, team_id):
            raise LookupError('Team not found')

        rows = db.session.execute(
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.joined_at.asc())
        ).all()
        return [{'member': m, 'user': u} for m, u in rows]

    @staticmethod
    def list_snippets(
        user: User,
        team_id: str,
        since: int | None,
        limit: int,
    ) -> tuple[list[SharedSnippet], bool]:
        if not TeamService.get_membership(user, team_id):
            raise LookupError('Team not found')

        query = select(SharedSnippet).where(SharedSnippet.team_id == team_id)
        if since is not None:
            query = query.where(SharedSnippet.synced_at > from_unix_ms(since))

        query = query.order_by(SharedSnippet.synced_at.asc()).limit(limit + 1)
        items = db.session.execute(query).scalars().all()

        has_more = len(items) > limit
        return list(items[:limit]), has_more

    @staticmethod
    def create_snippet(
        user: User,
        team_id: str,
        title: str,
        ciphertext: str,
        iv: str,
        tags: list | None,
    ) -> SharedSnippet:
        if not TeamService.get_membership(user, team_id):
            raise LookupError('Team not found')

        snippet = SharedSnippet(
            team_id=team_id,
            title=title,
            ciphertext=ciphertext,
            iv=iv,
            tags=tags,
            created_by=user.id,
        )
        db.session.add(snippet)
        db.session.commit()
        return snippet

    @staticmethod
    def delete_snippet(user: User, team_id: str, snippet_id: str) -> bool:
        """Soft-delete a snippet. Only the team owner or snippet creator may delete.

        Returns False if snippet not found or user lacks permission.
        """
        membership = TeamService.get_membership(user, team_id)
        if not membership:
            return False

        snippet = db.session.execute(
            select(SharedSnippet).where(
                SharedSnippet.id == snippet_id,
                SharedSnippet.team_id == team_id,
                SharedSnippet.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        if not snippet:
            return False

        if membership.role != 'owner' and snippet.created_by != user.id:
            return False  # 404 — don't reveal the snippet exists

        now = utcnow()
        snippet.deleted_at = now
        snippet.synced_at = now
        db.session.commit()
        return True
