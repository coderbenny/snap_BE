import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    yield
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


# ── Reusable auth helpers ────────────────────────────────────────────────────

VALID_EMAIL = 'test@example.com'
VALID_PASSWORD = 'testpassword123'


@pytest.fixture
def registered_user(client):
    client.post('/auth/register', json={'email': VALID_EMAIL, 'password': VALID_PASSWORD})
    return {'email': VALID_EMAIL, 'password': VALID_PASSWORD}


@pytest.fixture
def auth_tokens(client, registered_user):
    res = client.post('/auth/login', json=registered_user)
    return res.get_json()


@pytest.fixture
def auth_headers(auth_tokens):
    return {'Authorization': f"Bearer {auth_tokens['access_token']}"}
