"""Tests for /devices/* endpoints — register, list, delete."""



# ── Register device ───────────────────────────────────────────────────────────

class TestRegisterDevice:
    def test_success(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': 'MacBook Pro', 'platform': 'macos'},
                          headers=auth_headers)
        assert res.status_code == 201
        data = res.get_json()
        assert data['name'] == 'MacBook Pro'
        assert data['platform'] == 'macos'
        assert 'id' in data
        assert 'created_at' in data
        assert data['last_seen_at'] is None

    def test_all_platforms_accepted(self, client, auth_headers):
        for platform in ['macos', 'windows', 'android', 'ios', 'web']:
            res = client.post('/devices/register',
                              json={'name': f'My {platform}', 'platform': platform},
                              headers=auth_headers)
            assert res.status_code == 201, f'Failed for platform: {platform}'

    def test_no_auth_returns_401(self, client):
        res = client.post('/devices/register',
                          json={'name': 'MacBook Pro', 'platform': 'macos'})
        assert res.status_code == 401

    def test_invalid_bearer_returns_401(self, client):
        res = client.post('/devices/register',
                          json={'name': 'MacBook Pro', 'platform': 'macos'},
                          headers={'Authorization': 'Bearer invalidtoken'})
        assert res.status_code == 401

    def test_invalid_platform_returns_422(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': 'Linux Box', 'platform': 'linux'},
                          headers=auth_headers)
        assert res.status_code == 422
        assert res.get_json()['error']['code'] == 'VALIDATION_FAILED'

    def test_missing_name_returns_422(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'platform': 'macos'},
                          headers=auth_headers)
        assert res.status_code == 422

    def test_missing_platform_returns_422(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': 'MacBook Pro'},
                          headers=auth_headers)
        assert res.status_code == 422

    def test_empty_name_returns_422(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': '', 'platform': 'macos'},
                          headers=auth_headers)
        assert res.status_code == 422

    def test_name_too_long_returns_422(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': 'x' * 101, 'platform': 'macos'},
                          headers=auth_headers)
        assert res.status_code == 422


# ── List devices ──────────────────────────────────────────────────────────────

class TestListDevices:
    def test_empty_list(self, client, auth_headers):
        res = client.get('/devices', headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['devices'] == []

    def test_returns_registered_devices(self, client, auth_headers):
        client.post('/devices/register',
                    json={'name': 'MacBook', 'platform': 'macos'},
                    headers=auth_headers)
        client.post('/devices/register',
                    json={'name': 'Pixel 8', 'platform': 'android'},
                    headers=auth_headers)

        res = client.get('/devices', headers=auth_headers)
        assert res.status_code == 200
        devices = res.get_json()['devices']
        assert len(devices) == 2
        names = {d['name'] for d in devices}
        assert names == {'MacBook', 'Pixel 8'}

    def test_no_auth_returns_401(self, client):
        res = client.get('/devices')
        assert res.status_code == 401

    def test_only_returns_own_devices(self, client):
        # Register two separate users, each with a device
        client.post('/auth/register',
                    json={'email': 'alice@example.com', 'password': 'password123'})
        client.post('/auth/register',
                    json={'email': 'bob@example.com', 'password': 'password123'})

        alice_token = client.post('/auth/login', json={
            'email': 'alice@example.com', 'password': 'password123'
        }).get_json()['access_token']
        bob_token = client.post('/auth/login', json={
            'email': 'bob@example.com', 'password': 'password123'
        }).get_json()['access_token']

        alice_headers = {'Authorization': f'Bearer {alice_token}'}
        bob_headers = {'Authorization': f'Bearer {bob_token}'}

        client.post('/devices/register',
                    json={'name': "Alice's Mac", 'platform': 'macos'},
                    headers=alice_headers)
        client.post('/devices/register',
                    json={'name': "Bob's PC", 'platform': 'windows'},
                    headers=bob_headers)

        alice_devices = client.get('/devices', headers=alice_headers).get_json()['devices']
        bob_devices = client.get('/devices', headers=bob_headers).get_json()['devices']

        assert len(alice_devices) == 1
        assert alice_devices[0]['name'] == "Alice's Mac"
        assert len(bob_devices) == 1
        assert bob_devices[0]['name'] == "Bob's PC"


# ── Delete device ─────────────────────────────────────────────────────────────

class TestDeleteDevice:
    def _register_device(self, client, auth_headers):
        res = client.post('/devices/register',
                          json={'name': 'Test Device', 'platform': 'macos'},
                          headers=auth_headers)
        return res.get_json()['id']

    def test_success(self, client, auth_headers):
        device_id = self._register_device(client, auth_headers)
        res = client.delete(f'/devices/{device_id}', headers=auth_headers)
        assert res.status_code == 204

        # Confirm it's gone from the list
        devices = client.get('/devices', headers=auth_headers).get_json()['devices']
        assert not any(d['id'] == device_id for d in devices)

    def test_not_found_returns_404(self, client, auth_headers):
        res = client.delete('/devices/nonexistent-id', headers=auth_headers)
        assert res.status_code == 404
        assert res.get_json()['error']['code'] == 'NOT_FOUND'

    def test_no_auth_returns_401(self, client, auth_headers):
        device_id = self._register_device(client, auth_headers)
        res = client.delete(f'/devices/{device_id}')
        assert res.status_code == 401

    def test_cannot_delete_another_users_device(self, client):
        # Alice registers a device
        client.post('/auth/register',
                    json={'email': 'alice2@example.com', 'password': 'password123'})
        client.post('/auth/register',
                    json={'email': 'bob2@example.com', 'password': 'password123'})

        alice_token = client.post('/auth/login', json={
            'email': 'alice2@example.com', 'password': 'password123'
        }).get_json()['access_token']
        bob_token = client.post('/auth/login', json={
            'email': 'bob2@example.com', 'password': 'password123'
        }).get_json()['access_token']

        alice_headers = {'Authorization': f'Bearer {alice_token}'}
        bob_headers = {'Authorization': f'Bearer {bob_token}'}

        # Alice creates a device
        device_id = client.post('/devices/register',
                                json={'name': "Alice's Mac", 'platform': 'macos'},
                                headers=alice_headers).get_json()['id']

        # Bob tries to delete Alice's device — must get 404 (not 403, to avoid leaking existence)
        res = client.delete(f'/devices/{device_id}', headers=bob_headers)
        assert res.status_code == 404

        # Alice's device is still there
        alice_devices = client.get('/devices', headers=alice_headers).get_json()['devices']
        assert len(alice_devices) == 1
