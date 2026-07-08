"""Tests for /teams endpoints — create, invite, join, members, snippets."""

from tests.conftest import VALID_EMAIL, VALID_PASSWORD

# ── Helpers ───────────────────────────────────────────────────────────────────


def register_and_login(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User
    from app.utils.time import utcnow

    client.post('/snap/auth/register', json={'email': email, 'password': password})
    # Verify the user — login blocks unverified accounts
    user = db.session.execute(select(User).where(User.email == email)).scalar_one()
    user.verified_at = utcnow()
    db.session.commit()

    res = client.post('/snap/auth/login', json={'email': email, 'password': password})
    return {'Authorization': f"Bearer {res.get_json()['access_token']}"}


def upgrade_to_team(email=VALID_EMAIL):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User

    user = db.session.execute(select(User).where(User.email == email)).scalar_one()
    user.plan_tier = 'team'
    db.session.commit()


def team_headers(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    headers = register_and_login(client, email, password)
    upgrade_to_team(email)
    return headers


SNIPPET = {
    'title': 'API key',
    'ciphertext': 'base64cipher==',
    'iv': 'base64iv12bytes=',
}

# ── Plan guard ────────────────────────────────────────────────────────────────


class TestPlanGuard:
    def test_create_team_requires_team_plan(self, client, app):
        headers = register_and_login(client)
        res = client.post('/snap/teams', json={'name': 'My Team'}, headers=headers)
        assert res.status_code == 403

    def test_unauthenticated_create_team(self, client):
        res = client.post('/snap/teams', json={'name': 'x'})
        assert res.status_code == 401


# ── POST /teams ───────────────────────────────────────────────────────────────


class TestCreateTeam:
    def test_creates_team_and_sets_owner(self, client, app):
        headers = team_headers(client)
        res = client.post('/snap/teams', json={'name': 'SNAP Team'}, headers=headers)
        assert res.status_code == 201
        body = res.get_json()
        assert body['name'] == 'SNAP Team'
        assert body['role'] == 'owner'
        assert 'id' in body

    def test_missing_name(self, client, app):
        headers = team_headers(client)
        res = client.post('/snap/teams', json={}, headers=headers)
        assert res.status_code == 422

    def test_name_too_long(self, client, app):
        headers = team_headers(client)
        res = client.post('/snap/teams', json={'name': 'x' * 101}, headers=headers)
        assert res.status_code == 422


# ── GET /teams ────────────────────────────────────────────────────────────────


class TestListTeams:
    def test_returns_teams_user_belongs_to(self, client, app):
        headers = team_headers(client)
        client.post('/snap/teams', json={'name': 'Team A'}, headers=headers)
        client.post('/snap/teams', json={'name': 'Team B'}, headers=headers)

        res = client.get('/snap/teams', headers=headers)
        assert res.status_code == 200
        assert len(res.get_json()['teams']) == 2

    def test_empty_when_no_teams(self, client, app):
        headers = team_headers(client)
        res = client.get('/snap/teams', headers=headers)
        assert res.get_json()['teams'] == []


# ── POST /teams/:id/invite ────────────────────────────────────────────────────


class TestInvite:
    def test_owner_can_invite(self, client, app):
        headers = team_headers(client)
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=headers).get_json()['id']

        res = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'invitee@example.com'},
            headers=headers,
        )
        assert res.status_code == 201
        assert 'invite_token' in res.get_json()

    def test_member_cannot_invite(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        member_h = team_headers(client, 'member@example.com')
        upgrade_to_team('member@example.com')

        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']
        token = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'member@example.com'},
            headers=owner_h,
        ).get_json()['invite_token']
        client.post('/snap/teams/join', json={'token': token}, headers=member_h)

        res = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'third@example.com'},
            headers=member_h,
        )
        assert res.status_code == 403

    def test_invite_nonexistent_team(self, client, app):
        headers = team_headers(client)
        res = client.post(
            '/snap/teams/nonexistent-id/invite',
            json={'email': 'x@example.com'},
            headers=headers,
        )
        assert res.status_code == 404

    def test_invite_already_member(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        upgrade_to_team('owner@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']

        res = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'owner@example.com'},
            headers=owner_h,
        )
        assert res.status_code == 400

    def test_invalid_email(self, client, app):
        headers = team_headers(client)
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=headers).get_json()['id']
        res = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'notanemail'},
            headers=headers,
        )
        assert res.status_code == 422


# ── POST /teams/join ──────────────────────────────────────────────────────────


class TestJoin:
    def _setup_invite(self, client, app, invitee_email='invitee@example.com'):
        owner_h = team_headers(client, 'owner@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']
        token = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': invitee_email},
            headers=owner_h,
        ).get_json()['invite_token']
        return team_id, token

    def test_invitee_can_join(self, client, app):
        team_id, token = self._setup_invite(client, app)
        invitee_h = team_headers(client, 'invitee@example.com')

        res = client.post('/snap/teams/join', json={'token': token}, headers=invitee_h)
        assert res.status_code == 200
        body = res.get_json()
        assert body['team_id'] == team_id
        assert body['role'] == 'member'

    def test_invalid_token_rejected(self, client, app):
        headers = team_headers(client)
        res = client.post('/snap/teams/join', json={'token': 'badtoken'}, headers=headers)
        assert res.status_code == 404

    def test_token_cannot_be_reused(self, client, app):
        team_id, token = self._setup_invite(client, app)
        invitee_h = team_headers(client, 'invitee@example.com')
        second_h = team_headers(client, 'second@example.com')

        client.post('/snap/teams/join', json={'token': token}, headers=invitee_h)
        res = client.post('/snap/teams/join', json={'token': token}, headers=second_h)
        assert res.status_code == 404

    def test_wrong_email_cannot_use_token(self, client, app):
        """Token issued for A cannot be accepted by B — IDOR fix."""
        _, token = self._setup_invite(client, app, 'intended@example.com')
        other_h = team_headers(client, 'other@example.com')

        res = client.post('/snap/teams/join', json={'token': token}, headers=other_h)
        assert res.status_code == 404

    def test_reinvite_supersedes_old_token(self, client, app):
        """Creating a second invite for the same email expires the first token."""
        team_id, token1 = self._setup_invite(client, app)
        owner_h = team_headers(client, 'owner@example.com')

        # Second invite for the same email on the same team
        token2 = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'invitee@example.com'},
            headers=owner_h,
        ).get_json()['invite_token']

        invitee_h = team_headers(client, 'invitee@example.com')
        res1 = client.post('/snap/teams/join', json={'token': token1}, headers=invitee_h)
        res2 = client.post('/snap/teams/join', json={'token': token2}, headers=invitee_h)
        assert res1.status_code == 404  # first token expired
        assert res2.status_code == 200  # second token works

    def test_already_member_rejected(self, client, app):
        import hashlib
        from datetime import timedelta

        from app.extensions import db
        from app.models.team import TeamInvite
        from app.utils.time import utcnow

        team_id, token = self._setup_invite(client, app)
        invitee_h = team_headers(client, 'invitee@example.com')

        # Join successfully
        client.post('/snap/teams/join', json={'token': token}, headers=invitee_h)

        # Directly insert a second valid invite for the same team to bypass
        # the already-member guard on POST /teams/:id/invite.
        raw2 = 'a' * 64
        with app.app_context():
            db.session.add(TeamInvite(
                team_id=team_id,
                email='invitee@example.com',
                token_hash=hashlib.sha256(raw2.encode()).hexdigest(),
                expires_at=utcnow() + timedelta(days=7),
            ))
            db.session.commit()

        res = client.post('/snap/teams/join', json={'token': raw2}, headers=invitee_h)
        assert res.status_code == 400


# ── GET /teams/:id/members ────────────────────────────────────────────────────


class TestListMembers:
    def test_owner_sees_themselves(self, client, app):
        headers = team_headers(client)
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=headers).get_json()['id']

        res = client.get(f'/snap/teams/{team_id}/members', headers=headers)
        assert res.status_code == 200
        members = res.get_json()['members']
        assert len(members) == 1
        assert members[0]['role'] == 'owner'

    def test_non_member_gets_404(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        outsider_h = team_headers(client, 'outsider@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']

        res = client.get(f'/snap/teams/{team_id}/members', headers=outsider_h)
        assert res.status_code == 404

    def test_member_appears_after_join(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        member_h = team_headers(client, 'member@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']
        token = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'member@example.com'},
            headers=owner_h,
        ).get_json()['invite_token']
        client.post('/snap/teams/join', json={'token': token}, headers=member_h)

        members = (
            client.get(f'/snap/teams/{team_id}/members', headers=owner_h).get_json()['members']
        )
        assert len(members) == 2


# ── Snippets ──────────────────────────────────────────────────────────────────


class TestSnippets:
    def _make_team(self, client, app, email='owner@example.com'):
        headers = team_headers(client, email)
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=headers).get_json()['id']
        return headers, team_id

    def test_create_snippet(self, client, app):
        headers, team_id = self._make_team(client, app)
        res = client.post(f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers)
        assert res.status_code == 201
        body = res.get_json()
        assert body['title'] == SNIPPET['title']
        assert body['ciphertext'] == SNIPPET['ciphertext']
        assert body['deleted_at'] is None

    def test_create_missing_fields(self, client, app):
        headers, team_id = self._make_team(client, app)
        res = client.post(f'/snap/teams/{team_id}/snippets', json={'title': 'x'}, headers=headers)
        assert res.status_code == 422

    def test_create_in_nonexistent_team(self, client, app):
        headers = team_headers(client)
        res = client.post('/snap/teams/ghost/snippets', json=SNIPPET, headers=headers)
        assert res.status_code == 404

    def test_list_snippets_empty(self, client, app):
        headers, team_id = self._make_team(client, app)
        res = client.get(f'/snap/teams/{team_id}/snippets', headers=headers)
        assert res.status_code == 200
        assert res.get_json()['items'] == []

    def test_list_snippets_returns_created(self, client, app):
        headers, team_id = self._make_team(client, app)
        client.post(f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers)

        res = client.get(f'/snap/teams/{team_id}/snippets', headers=headers)
        items = res.get_json()['items']
        assert len(items) == 1
        assert items[0]['title'] == SNIPPET['title']

    def test_list_snippets_non_member_gets_404(self, client, app):
        headers, team_id = self._make_team(client, app)
        outsider = team_headers(client, 'outsider@example.com')
        res = client.get(f'/snap/teams/{team_id}/snippets', headers=outsider)
        assert res.status_code == 404

    def test_list_snippets_paging(self, client, app):
        headers, team_id = self._make_team(client, app)
        for _ in range(4):
            client.post(f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers)

        res = client.get(f'/snap/teams/{team_id}/snippets?limit=2', headers=headers)
        body = res.get_json()
        assert len(body['items']) == 2
        assert body['has_more'] is True

    def test_delete_snippet_by_owner(self, client, app):
        headers, team_id = self._make_team(client, app)
        snippet_id = client.post(
            f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers
        ).get_json()['id']

        res = client.delete(f'/snap/teams/{team_id}/snippets/{snippet_id}', headers=headers)
        assert res.status_code == 204

    def test_delete_snippet_by_creator(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        member_h = team_headers(client, 'member@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']
        token = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'member@example.com'},
            headers=owner_h,
        ).get_json()['invite_token']
        client.post('/snap/teams/join', json={'token': token}, headers=member_h)

        snippet_id = client.post(
            f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=member_h
        ).get_json()['id']

        res = client.delete(f'/snap/teams/{team_id}/snippets/{snippet_id}', headers=member_h)
        assert res.status_code == 204

    def test_member_cannot_delete_others_snippet(self, client, app):
        owner_h = team_headers(client, 'owner@example.com')
        member_h = team_headers(client, 'member@example.com')
        team_id = client.post('/snap/teams', json={'name': 'T'}, headers=owner_h).get_json()['id']
        token = client.post(
            f'/snap/teams/{team_id}/invite',
            json={'email': 'member@example.com'},
            headers=owner_h,
        ).get_json()['invite_token']
        client.post('/snap/teams/join', json={'token': token}, headers=member_h)

        snippet_id = client.post(
            f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=owner_h
        ).get_json()['id']

        res = client.delete(f'/snap/teams/{team_id}/snippets/{snippet_id}', headers=member_h)
        assert res.status_code == 404

    def test_deleted_snippet_in_next_pull(self, client, app):
        import time
        headers, team_id = self._make_team(client, app)
        snippet_id = client.post(
            f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers
        ).get_json()['id']

        time.sleep(0.005)
        now_ms = int(time.time() * 1000)
        time.sleep(0.005)
        client.delete(f'/snap/teams/{team_id}/snippets/{snippet_id}', headers=headers)

        res = client.get(f'/snap/teams/{team_id}/snippets?since={now_ms}', headers=headers)
        items = res.get_json()['items']
        found = next((i for i in items if i['id'] == snippet_id), None)
        assert found is not None
        assert found['deleted_at'] is not None

    def test_outsider_cannot_create_snippet(self, client, app):
        headers, team_id = self._make_team(client, app)
        outsider = team_headers(client, 'outsider@example.com')
        res = client.post(f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=outsider)
        assert res.status_code == 404

    def test_invalid_since_param(self, client, app):
        headers, team_id = self._make_team(client, app)
        res = client.get(f'/snap/teams/{team_id}/snippets?since=abc', headers=headers)
        assert res.status_code == 400

    def test_next_since_not_advanced_while_pages_remain(self, client, app):
        """next_since must stay pinned when has_more=True to avoid skipping rows."""
        headers, team_id = self._make_team(client, app)
        for _ in range(4):
            client.post(f'/snap/teams/{team_id}/snippets', json=SNIPPET, headers=headers)

        since = 0
        res = client.get(f'/snap/teams/{team_id}/snippets?since={since}&limit=2', headers=headers)
        body = res.get_json()
        assert body['has_more'] is True
        assert body['next_since'] == since

    def test_iv_too_short_rejected(self, client, app):
        headers, team_id = self._make_team(client, app)
        bad = {**SNIPPET, 'iv': 'tooshort'}
        res = client.post(f'/snap/teams/{team_id}/snippets', json=bad, headers=headers)
        assert res.status_code == 422
