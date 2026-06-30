"""Tests for /devices/* endpoints — register, list, delete."""

import uuid

from sqlalchemy import select

from app.extensions import db
from app.models.user import User
from app.utils.time import utcnow

URL = '/snap/devices/register'


def _make_device_id():
    return str(uuid.uuid4())


def _reg_body(**overrides):
    base = {'device_id': _make_device_id(), 'name': 'Test Device', 'platform': 'macos'}
    return {**base, **overrides}


def _verify_user(email):
    user = db.session.execute(select(User).where(User.email == email)).scalar_one()
    user.verified_at = utcnow()
    db.session.commit()


# ── Register device ───────────────────────────────────────────────────────────

class TestRegisterDevice:
    def test_success(self, client, auth_headers):
        res = client.post(URL, json=_reg_body(name='MacBook Pro'), headers=auth_headers)
        assert res.status_code == 201
        data = res.get_json()
        assert data['name'] == 'MacBook Pro'
        assert data['platform'] == 'macos'
        assert 'id' in data
        assert 'created_at' in data
        assert data['last_seen_at'] is not None

    def test_all_platforms_accepted(self, client, auth_headers):
        for platform in ['macos', 'windows', 'android', 'ios', 'web']:
            body = _reg_body(name=f'My {platform}', platform=platform)
            res = client.post(URL, json=body, headers=auth_headers)
            assert res.status_code == 201, f'Failed for platform: {platform}'

    def test_no_auth_returns_401(self, client):
        res = client.post(URL, json=_reg_body(name='MacBook Pro'))
        assert res.status_code == 401

    def test_invalid_bearer_returns_401(self, client):
        res = client.post(
            URL,
            json=_reg_body(name='MacBook Pro'),
            headers={'Authorization': 'Bearer invalidtoken'},
        )
        assert res.status_code == 401

    def test_invalid_platform_returns_422(self, client, auth_headers):
        res = client.post(
            URL,
            json=_reg_body(name='Linux Box', platform='linux'),
            headers=auth_headers,
        )
        assert res.status_code == 422
        assert res.get_json()['error']['code'] == 'VALIDATION_FAILED'

    def test_missing_name_returns_422(self, client, auth_headers):
        body = {'device_id': _make_device_id(), 'platform': 'macos'}
        res = client.post(URL, json=body, headers=auth_headers)
        assert res.status_code == 422

    def test_missing_platform_returns_422(self, client, auth_headers):
        body = {'device_id': _make_device_id(), 'name': 'MacBook Pro'}
        res = client.post(URL, json=body, headers=auth_headers)
        assert res.status_code == 422

    def test_empty_name_returns_422(self, client, auth_headers):
        res = client.post(URL, json=_reg_body(name=''), headers=auth_headers)
        assert res.status_code == 422

    def test_name_too_long_returns_422(self, client, auth_headers):
        res = client.post(URL, json=_reg_body(name='x' * 101), headers=auth_headers)
        assert res.status_code == 422


# ── List devices ──────────────────────────────────────────────────────────────

class TestListDevices:
    def test_empty_list(self, client, auth_headers):
        res = client.get('/snap/devices', headers=auth_headers)
        assert res.status_code == 200
        assert res.get_json()['devices'] == []

    def test_returns_registered_devices(self, client, auth_headers):
        client.post(URL, json=_reg_body(name='MacBook', platform='macos'), headers=auth_headers)
        client.post(URL, json=_reg_body(name='Pixel 8', platform='android'), headers=auth_headers)

        res = client.get('/snap/devices', headers=auth_headers)
        assert res.status_code == 200
        devices = res.get_json()['devices']
        assert len(devices) == 2
        assert {d['name'] for d in devices} == {'MacBook', 'Pixel 8'}

    def test_no_auth_returns_401(self, client):
        res = client.get('/snap/devices')
        assert res.status_code == 401

    def test_only_returns_own_devices(self, client):
        client.post('/snap/auth/register',
                    json={'email': 'alice@example.com', 'password': 'password123'})
        client.post('/snap/auth/register',
                    json={'email': 'bob@example.com', 'password': 'password123'})
        _verify_user('alice@example.com')
        _verify_user('bob@example.com')

        alice_token = client.post('/snap/auth/login', json={
            'email': 'alice@example.com', 'password': 'password123',
        }).get_json()['access_token']
        bob_token = client.post('/snap/auth/login', json={
            'email': 'bob@example.com', 'password': 'password123',
        }).get_json()['access_token']

        ah = {'Authorization': f'Bearer {alice_token}'}
        bh = {'Authorization': f'Bearer {bob_token}'}

        client.post(URL, json=_reg_body(name="Alice's Mac"), headers=ah)
        client.post(URL, json=_reg_body(name="Bob's PC", platform='windows'), headers=bh)

        alice_devices = client.get('/snap/devices', headers=ah).get_json()['devices']
        bob_devices = client.get('/snap/devices', headers=bh).get_json()['devices']

        assert len(alice_devices) == 1
        assert alice_devices[0]['name'] == "Alice's Mac"
        assert len(bob_devices) == 1
        assert bob_devices[0]['name'] == "Bob's PC"


# ── Delete device ─────────────────────────────────────────────────────────────

class TestDeleteDevice:
    def _register_device(self, client, auth_headers):
        res = client.post(URL, json=_reg_body(), headers=auth_headers)
        return res.get_json()['id']

    def test_success(self, client, auth_headers):
        device_id = self._register_device(client, auth_headers)
        res = client.delete(f'/snap/devices/{device_id}', headers=auth_headers)
        assert res.status_code == 204

        devices = client.get('/snap/devices', headers=auth_headers).get_json()['devices']
        assert not any(d['id'] == device_id for d in devices)

    def test_not_found_returns_404(self, client, auth_headers):
        res = client.delete('/snap/devices/nonexistent-id', headers=auth_headers)
        assert res.status_code == 404
        assert res.get_json()['error']['code'] == 'NOT_FOUND'

    def test_no_auth_returns_401(self, client, auth_headers):
        device_id = self._register_device(client, auth_headers)
        res = client.delete(f'/snap/devices/{device_id}')
        assert res.status_code == 401

    def test_cannot_delete_another_users_device(self, client):
        client.post('/snap/auth/register',
                    json={'email': 'alice2@example.com', 'password': 'password123'})
        client.post('/snap/auth/register',
                    json={'email': 'bob2@example.com', 'password': 'password123'})
        _verify_user('alice2@example.com')
        _verify_user('bob2@example.com')

        alice_token = client.post('/snap/auth/login', json={
            'email': 'alice2@example.com', 'password': 'password123',
        }).get_json()['access_token']
        bob_token = client.post('/snap/auth/login', json={
            'email': 'bob2@example.com', 'password': 'password123',
        }).get_json()['access_token']

        ah = {'Authorization': f'Bearer {alice_token}'}
        bh = {'Authorization': f'Bearer {bob_token}'}

        device_id = (
            client.post(URL, json=_reg_body(name="Alice's Mac"), headers=ah).get_json()['id']
        )

        res = client.delete(f'/snap/devices/{device_id}', headers=bh)
        assert res.status_code == 404

        alice_devices = client.get('/snap/devices', headers=ah).get_json()['devices']
        assert len(alice_devices) == 1
