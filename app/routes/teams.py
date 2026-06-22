from flask import Blueprint, g, request
from marshmallow import ValidationError

from app.middleware.auth_middleware import require_auth
from app.middleware.plan_guard import require_plan
from app.schemas.team_schemas import (
    AcceptInviteSchema,
    CreateTeamSchema,
    InviteSchema,
    SharedSnippetSchema,
)
from app.services.team_service import TeamService
from app.utils.errors import bad_request, forbidden, not_found, validation_failed
from app.utils.time import to_unix_ms

teams_bp = Blueprint('teams', __name__, url_prefix='/teams')

_create_schema = CreateTeamSchema()
_invite_schema = InviteSchema()
_accept_schema = AcceptInviteSchema()
_snippet_schema = SharedSnippetSchema()

_DEFAULT_LIMIT = 200
_MAX_LIMIT = 500


# ── Team management ───────────────────────────────────────────────────────────

@teams_bp.post('')
@require_auth
@require_plan('team')
def create_team():
    try:
        data = _create_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    team = TeamService.create(g.current_user, data['name'])
    return _serialize_team(team, role='owner'), 201


@teams_bp.get('')
@require_auth
@require_plan('team')
def list_teams():
    rows = TeamService.list_for_user(g.current_user)
    return {'teams': [
        {**_serialize_team(r['team']), 'role': r['role']}
        for r in rows
    ]}


@teams_bp.post('/join')
@require_auth
@require_plan('team')
def accept_invite():
    try:
        data = _accept_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        membership = TeamService.accept_invite(g.current_user, data['token'])
    except LookupError as e:
        return not_found(str(e))
    except ValueError as e:
        return bad_request(str(e))

    return {'team_id': membership.team_id, 'role': membership.role}, 200


# ── Per-team routes ───────────────────────────────────────────────────────────

@teams_bp.post('/<team_id>/invite')
@require_auth
@require_plan('team')
def invite_member(team_id):
    try:
        data = _invite_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        token = TeamService.invite(g.current_user, team_id, data['email'])
    except LookupError as e:
        return not_found(str(e))
    except PermissionError as e:
        return forbidden(str(e))
    except ValueError as e:
        return bad_request(str(e))

    return {
        'invite_token': token,
        'expires_in_days': 7,
        'note': 'Email delivery is not yet configured — pass this token to the invitee directly.',
    }, 201


@teams_bp.get('/<team_id>/members')
@require_auth
@require_plan('team')
def list_members(team_id):
    try:
        rows = TeamService.list_members(g.current_user, team_id)
    except LookupError:
        return not_found('Team not found')

    return {'members': [
        {
            'user_id': r['member'].user_id,
            'email': r['user'].email,
            'role': r['member'].role,
            'joined_at': r['member'].joined_at.isoformat(),
        }
        for r in rows
    ]}


# ── Snippets ──────────────────────────────────────────────────────────────────

@teams_bp.get('/<team_id>/snippets')
@require_auth
@require_plan('team')
def list_snippets(team_id):
    since_raw = request.args.get('since')
    limit_raw = request.args.get('limit', _DEFAULT_LIMIT)

    since: int | None = None
    if since_raw is not None:
        try:
            since = int(since_raw)
            if since < 0:
                raise ValueError
        except ValueError:
            return bad_request("'since' must be a non-negative integer (Unix ms)")

    try:
        limit = int(limit_raw)
        if not (1 <= limit <= _MAX_LIMIT):
            raise ValueError
    except ValueError:
        return bad_request(f"'limit' must be an integer between 1 and {_MAX_LIMIT}")

    try:
        items, has_more = TeamService.list_snippets(g.current_user, team_id, since, limit)
    except LookupError:
        return not_found('Team not found')

    return {
        'items': [_serialize_snippet(s) for s in items],
        'has_more': has_more,
        'next_since': to_unix_ms(items[-1].synced_at) if items else (since or 0),
    }


@teams_bp.post('/<team_id>/snippets')
@require_auth
@require_plan('team')
def create_snippet(team_id):
    try:
        data = _snippet_schema.load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return validation_failed(e.messages)

    try:
        snippet = TeamService.create_snippet(
            g.current_user,
            team_id,
            data['title'],
            data['ciphertext'],
            data['iv'],
            data.get('tags'),
        )
    except LookupError:
        return not_found('Team not found')

    return _serialize_snippet(snippet), 201


@teams_bp.delete('/<team_id>/snippets/<snippet_id>')
@require_auth
@require_plan('team')
def delete_snippet(team_id, snippet_id):
    if not TeamService.delete_snippet(g.current_user, team_id, snippet_id):
        return not_found('Snippet not found')
    return '', 204


# ── Serializers ───────────────────────────────────────────────────────────────

def _serialize_team(team, role: str | None = None) -> dict:
    d = {
        'id': team.id,
        'name': team.name,
        'owner_id': team.owner_id,
        'created_at': team.created_at.isoformat(),
    }
    if role is not None:
        d['role'] = role
    return d


def _serialize_snippet(snippet) -> dict:
    return {
        'id': snippet.id,
        'team_id': snippet.team_id,
        'title': snippet.title,
        'ciphertext': snippet.ciphertext,
        'iv': snippet.iv,
        'tags': snippet.tags,
        'created_by': snippet.created_by,
        'synced_at': to_unix_ms(snippet.synced_at),
        'created_at': to_unix_ms(snippet.created_at),
        'deleted_at': to_unix_ms(snippet.deleted_at) if snippet.deleted_at else None,
    }
