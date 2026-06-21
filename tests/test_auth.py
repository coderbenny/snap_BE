"""Tests for /auth/* endpoints — register, login, refresh, logout."""

import jwt

from tests.conftest import VALID_EMAIL, VALID_PASSWORD

# ── Register ─────────────────────────────────────────────────────────────────

class TestRegister:
    def test_success(self, client):
        res = client.post('/auth/register', json={
            'email': 'new@example.com',
            'password': 'strongpassword1',
        })
        assert res.status_code == 201
        data = res.get_json()
        assert 'user_id' in data
        assert data['message'] == 'Account created successfully'

    def test_email_normalised_to_lowercase(self, client):
        res = client.post('/auth/register', json={
            'email': 'UPPER@EXAMPLE.COM',
            'password': 'strongpassword1',
        })
        assert res.status_code == 201

        # Should be able to log in with lowercase version
        login = client.post('/auth/login', json={
            'email': 'upper@example.com',
            'password': 'strongpassword1',
        })
        assert login.status_code == 200

    def test_duplicate_email_returns_409(self, client, registered_user):
        res = client.post('/auth/register', json={
            'email': VALID_EMAIL,
            'password': 'anotherpassword1',
        })
        assert res.status_code == 409
        data = res.get_json()
        assert data['error']['code'] == 'CONFLICT'
        assert 'sign in instead' in data['error']['message']

    def test_duplicate_email_case_insensitive(self, client, registered_user):
        res = client.post('/auth/register', json={
            'email': VALID_EMAIL.upper(),
            'password': 'anotherpassword1',
        })
        assert res.status_code == 409

    def test_invalid_email_returns_422(self, client):
        res = client.post('/auth/register', json={
            'email': 'not-an-email',
            'password': 'strongpassword1',
        })
        assert res.status_code == 422
        assert res.get_json()['error']['code'] == 'VALIDATION_FAILED'

    def test_password_too_short_returns_422(self, client):
        res = client.post('/auth/register', json={
            'email': 'short@example.com',
            'password': '1234567',
        })
        assert res.status_code == 422

    def test_missing_email_returns_422(self, client):
        res = client.post('/auth/register', json={'password': 'strongpassword1'})
        assert res.status_code == 422

    def test_missing_password_returns_422(self, client):
        res = client.post('/auth/register', json={'email': 'missing@example.com'})
        assert res.status_code == 422

    def test_empty_body_returns_422(self, client):
        res = client.post('/auth/register', json={})
        assert res.status_code == 422

    def test_non_json_body_returns_422(self, client):
        res = client.post('/auth/register', data='not json', content_type='text/plain')
        assert res.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_success_returns_tokens(self, client, registered_user):
        res = client.post('/auth/login', json=registered_user)
        assert res.status_code == 200
        data = res.get_json()
        assert 'access_token' in data
        assert 'refresh_token' in data

    def test_access_token_is_valid_jwt(self, client, registered_user, app):
        res = client.post('/auth/login', json=registered_user)
        token = res.get_json()['access_token']
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        assert 'sub' in payload
        assert 'plan_tier' in payload
        assert payload['plan_tier'] == 'free'

    def test_wrong_password_returns_401(self, client, registered_user):
        res = client.post('/auth/login', json={
            'email': VALID_EMAIL,
            'password': 'wrongpassword',
        })
        assert res.status_code == 401
        assert res.get_json()['error']['code'] == 'UNAUTHORIZED'

    def test_unknown_email_returns_401(self, client):
        res = client.post('/auth/login', json={
            'email': 'nobody@example.com',
            'password': VALID_PASSWORD,
        })
        assert res.status_code == 401

    def test_both_wrong_returns_same_401(self, client):
        # Ensure error message doesn't leak whether email exists
        res = client.post('/auth/login', json={
            'email': 'nobody@example.com',
            'password': 'wrongtoo',
        })
        assert res.status_code == 401
        assert res.get_json()['error']['message'] == 'Invalid email or password'

    def test_missing_fields_returns_422(self, client):
        res = client.post('/auth/login', json={'email': VALID_EMAIL})
        assert res.status_code == 422

    def test_login_is_case_insensitive_for_email(self, client, registered_user):
        res = client.post('/auth/login', json={
            'email': VALID_EMAIL.upper(),
            'password': VALID_PASSWORD,
        })
        assert res.status_code == 200


# ── Refresh ──────────────────────────────────────────────────────────────────

class TestRefresh:
    def test_success_returns_new_access_token(self, client, auth_tokens, app):
        res = client.post('/auth/refresh', json={
            'refresh_token': auth_tokens['refresh_token'],
        })
        assert res.status_code == 200
        data = res.get_json()
        assert 'access_token' in data
        # Verify the returned token is a valid JWT for the same user
        import jwt as pyjwt
        payload = pyjwt.decode(data['access_token'], app.config['SECRET_KEY'], algorithms=['HS256'])
        assert 'sub' in payload
        assert 'plan_tier' in payload

    def test_invalid_token_returns_401(self, client):
        res = client.post('/auth/refresh', json={'refresh_token': 'notavalidtoken'})
        assert res.status_code == 401

    def test_missing_token_returns_422(self, client):
        res = client.post('/auth/refresh', json={})
        assert res.status_code == 422

    def test_revoked_token_returns_401(self, client, auth_tokens):
        # Logout first (revokes the refresh token)
        client.post('/auth/logout', json={'refresh_token': auth_tokens['refresh_token']})
        # Then try to refresh with the revoked token
        res = client.post('/auth/refresh', json={
            'refresh_token': auth_tokens['refresh_token'],
        })
        assert res.status_code == 401


# ── Logout ───────────────────────────────────────────────────────────────────

class TestLogout:
    def test_success_returns_204(self, client, auth_tokens):
        res = client.post('/auth/logout', json={
            'refresh_token': auth_tokens['refresh_token'],
        })
        assert res.status_code == 204

    def test_logout_is_idempotent(self, client, auth_tokens):
        # Logging out twice should still return 204 (not an error)
        client.post('/auth/logout', json={'refresh_token': auth_tokens['refresh_token']})
        res = client.post('/auth/logout', json={'refresh_token': auth_tokens['refresh_token']})
        assert res.status_code == 204

    def test_logout_with_garbage_token_returns_204(self, client):
        res = client.post('/auth/logout', json={'refresh_token': 'garbagetoken'})
        assert res.status_code == 204

    def test_missing_token_returns_422(self, client):
        res = client.post('/auth/logout', json={})
        assert res.status_code == 422
