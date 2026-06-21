"""Tests for GET /sync, POST /sync/push, POST /sync/delete."""
import time
import uuid

import pytest

from tests.conftest import VALID_EMAIL, VALID_PASSWORD

# ── Helpers ──────────────────────────────────────────────────────────────────

ITEM_DEFAULTS = {
    'ciphertext': 'base64ciphertext==',
    'iv': 'base64iv12bytes==',
    'content_type': 'text',
    'client_created_at': 1_700_000_000_000,
}


def make_item(**overrides) -> dict:
    return {**ITEM_DEFAULTS, 'id': str(uuid.uuid4()), **overrides}


def register_and_login(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    client.post('/auth/register', json={'email': email, 'password': password})
    res = client.post('/auth/login', json={'email': email, 'password': password})
    data = res.get_json()
    return {'Authorization': f"Bearer {data['access_token']}"}


def upgrade_to_pro(app, email=VALID_EMAIL):
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User
    with app.app_context():
        user = db.session.execute(select(User).where(User.email == email)).scalar_one()
        user.plan_tier = 'pro'
        db.session.commit()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pro_headers(client, app):
    headers = register_and_login(client)
    upgrade_to_pro(app)
    return headers


@pytest.fixture
def free_headers(client):
    return register_and_login(client)


# ── Plan guard ───────────────────────────────────────────────────────────────

class TestPlanGuard:
    def test_pull_requires_pro(self, client, free_headers):
        res = client.get('/sync', headers=free_headers)
        assert res.status_code == 403
        assert res.get_json()['error']['code'] == 'FORBIDDEN'

    def test_push_requires_pro(self, client, free_headers):
        res = client.post('/sync/push', json={'items': [make_item()]}, headers=free_headers)
        assert res.status_code == 403

    def test_delete_requires_pro(self, client, free_headers):
        res = client.post('/sync/delete', json={'ids': [str(uuid.uuid4())]}, headers=free_headers)
        assert res.status_code == 403

    def test_unauthenticated_pull(self, client):
        res = client.get('/sync')
        assert res.status_code == 401

    def test_unauthenticated_push(self, client):
        res = client.post('/sync/push', json={'items': [make_item()]})
        assert res.status_code == 401

    def test_unauthenticated_delete(self, client):
        res = client.post('/sync/delete', json={'ids': [str(uuid.uuid4())]})
        assert res.status_code == 401


# ── Pull (GET /sync) ─────────────────────────────────────────────────────────

class TestPull:
    def test_pull_empty(self, client, pro_headers):
        res = client.get('/sync', headers=pro_headers)
        assert res.status_code == 200
        body = res.get_json()
        assert body['items'] == []
        assert body['has_more'] is False

    def test_pull_returns_pushed_items(self, client, pro_headers):
        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        res = client.get('/sync', headers=pro_headers)
        assert res.status_code == 200
        body = res.get_json()
        assert len(body['items']) == 1
        returned = body['items'][0]
        assert returned['id'] == item['id']
        assert returned['ciphertext'] == item['ciphertext']
        assert returned['iv'] == item['iv']
        assert returned['content_type'] == item['content_type']
        assert returned['client_created_at'] == item['client_created_at']
        assert returned['deleted_at'] is None

    def test_pull_since_filters_old_items(self, client, pro_headers):
        item_a = make_item()
        client.post('/sync/push', json={'items': [item_a]}, headers=pro_headers)

        now_ms = int(time.time() * 1000)
        time.sleep(0.05)  # ensure item_b has a later synced_at

        item_b = make_item()
        client.post('/sync/push', json={'items': [item_b]}, headers=pro_headers)

        res = client.get(f'/sync?since={now_ms}', headers=pro_headers)
        assert res.status_code == 200
        body = res.get_json()
        ids = [i['id'] for i in body['items']]
        assert item_b['id'] in ids
        assert item_a['id'] not in ids

    def test_pull_includes_soft_deleted(self, client, pro_headers):
        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)
        client.post('/sync/delete', json={'ids': [item['id']]}, headers=pro_headers)

        res = client.get('/sync', headers=pro_headers)
        body = res.get_json()
        found = next((i for i in body['items'] if i['id'] == item['id']), None)
        assert found is not None
        assert found['deleted_at'] is not None

    def test_pull_has_more_paging(self, client, pro_headers):
        items = [make_item() for _ in range(5)]
        client.post('/sync/push', json={'items': items}, headers=pro_headers)

        res = client.get('/sync?limit=3', headers=pro_headers)
        body = res.get_json()
        assert len(body['items']) == 3
        assert body['has_more'] is True

    def test_pull_invalid_since(self, client, pro_headers):
        res = client.get('/sync?since=notanumber', headers=pro_headers)
        assert res.status_code == 400

    def test_pull_invalid_limit(self, client, pro_headers):
        res = client.get('/sync?limit=0', headers=pro_headers)
        assert res.status_code == 400

    def test_pull_limit_too_large(self, client, pro_headers):
        res = client.get('/sync?limit=999', headers=pro_headers)
        assert res.status_code == 400

    def test_pull_isolates_between_users(self, client, app):
        headers_a = register_and_login(client, 'a@example.com')
        headers_b = register_and_login(client, 'b@example.com')
        upgrade_to_pro(app, 'a@example.com')
        upgrade_to_pro(app, 'b@example.com')

        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=headers_a)

        res = client.get('/sync', headers=headers_b)
        body = res.get_json()
        assert body['items'] == []


# ── Push (POST /sync/push) ───────────────────────────────────────────────────

class TestPush:
    def test_push_single_item(self, client, pro_headers):
        item = make_item()
        res = client.post('/sync/push', json={'items': [item]}, headers=pro_headers)
        assert res.status_code == 200
        assert res.get_json()['accepted'] == 1

    def test_push_multiple_items(self, client, pro_headers):
        items = [make_item() for _ in range(10)]
        res = client.post('/sync/push', json={'items': items}, headers=pro_headers)
        assert res.status_code == 200
        assert res.get_json()['accepted'] == 10

    def test_push_upsert_updates_existing(self, client, pro_headers):
        item = make_item(ciphertext='original==')
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        updated = {**item, 'ciphertext': 'updated=='}
        res = client.post('/sync/push', json={'items': [updated]}, headers=pro_headers)
        assert res.status_code == 200

        pull = client.get('/sync', headers=pro_headers).get_json()
        assert len(pull['items']) == 1
        assert pull['items'][0]['ciphertext'] == 'updated=='

    def test_push_upsert_preserves_client_created_at(self, client, pro_headers):
        original_ts = 1_600_000_000_000
        item = make_item(client_created_at=original_ts)
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        updated = {**item, 'client_created_at': 9_999_999_999_999}
        client.post('/sync/push', json={'items': [updated]}, headers=pro_headers)

        pull = client.get('/sync', headers=pro_headers).get_json()
        assert pull['items'][0]['client_created_at'] == original_ts

    def test_push_optional_fields(self, client, pro_headers):
        item = make_item(tags=['work', 'important'], pinned=True)
        res = client.post('/sync/push', json={'items': [item]}, headers=pro_headers)
        assert res.status_code == 200

        pull = client.get('/sync', headers=pro_headers).get_json()
        returned = pull['items'][0]
        assert returned['tags'] == ['work', 'important']
        assert returned['pinned'] is True

    def test_push_empty_items_list(self, client, pro_headers):
        res = client.post('/sync/push', json={'items': []}, headers=pro_headers)
        assert res.status_code == 422

    def test_push_missing_required_field(self, client, pro_headers):
        item = make_item()
        del item['ciphertext']
        res = client.post('/sync/push', json={'items': [item]}, headers=pro_headers)
        assert res.status_code == 422

    def test_push_invalid_content_type(self, client, pro_headers):
        item = make_item(content_type='video')
        res = client.post('/sync/push', json={'items': [item]}, headers=pro_headers)
        assert res.status_code == 422

    def test_push_no_body(self, client, pro_headers):
        res = client.post('/sync/push', headers=pro_headers, content_type='application/json')
        assert res.status_code == 422


# ── Delete (POST /sync/delete) ───────────────────────────────────────────────

class TestSoftDelete:
    def test_delete_existing_item(self, client, pro_headers):
        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        res = client.post('/sync/delete', json={'ids': [item['id']]}, headers=pro_headers)
        assert res.status_code == 200
        assert res.get_json()['deleted'] == 1

    def test_delete_nonexistent_id_is_noop(self, client, pro_headers):
        res = client.post(
            '/sync/delete', json={'ids': [str(uuid.uuid4())]}, headers=pro_headers
        )
        assert res.status_code == 200
        assert res.get_json()['deleted'] == 0

    def test_delete_idempotent(self, client, pro_headers):
        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        client.post('/sync/delete', json={'ids': [item['id']]}, headers=pro_headers)
        res = client.post('/sync/delete', json={'ids': [item['id']]}, headers=pro_headers)
        assert res.status_code == 200
        assert res.get_json()['deleted'] == 0

    def test_delete_does_not_delete_other_users_items(self, client, app):
        headers_a = register_and_login(client, 'owner@example.com')
        headers_b = register_and_login(client, 'attacker@example.com')
        upgrade_to_pro(app, 'owner@example.com')
        upgrade_to_pro(app, 'attacker@example.com')

        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=headers_a)

        res = client.post('/sync/delete', json={'ids': [item['id']]}, headers=headers_b)
        assert res.status_code == 200
        assert res.get_json()['deleted'] == 0

        pull = client.get('/sync', headers=headers_a).get_json()
        assert pull['items'][0]['deleted_at'] is None

    def test_delete_empty_ids_list(self, client, pro_headers):
        res = client.post('/sync/delete', json={'ids': []}, headers=pro_headers)
        assert res.status_code == 422

    def test_delete_missing_body(self, client, pro_headers):
        res = client.post('/sync/delete', headers=pro_headers, content_type='application/json')
        assert res.status_code == 422

    def test_deleted_item_appears_in_next_pull(self, client, pro_headers):
        item = make_item()
        client.post('/sync/push', json={'items': [item]}, headers=pro_headers)

        now_ms = int(time.time() * 1000)
        time.sleep(0.05)
        client.post('/sync/delete', json={'ids': [item['id']]}, headers=pro_headers)

        res = client.get(f'/sync?since={now_ms}', headers=pro_headers)
        body = res.get_json()
        found = next((i for i in body['items'] if i['id'] == item['id']), None)
        assert found is not None
        assert found['deleted_at'] is not None
