def test_health_returns_ok(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'
    assert 'version' in data


def test_health_version_matches_config(client, app):
    response = client.get('/health')
    data = response.get_json()
    assert data['version'] == app.config['APP_VERSION']


def test_404_returns_error_envelope(client):
    response = client.get('/nonexistent-route')
    assert response.status_code == 404
    data = response.get_json()
    assert 'error' in data
    assert 'code' in data['error']
    assert 'message' in data['error']
    assert data['error']['code'] == 'NOT_FOUND'


def test_health_db_with_sqlite(client):
    # In testing config we use SQLite; verifies the endpoint exists and responds
    response = client.get('/health/db')
    assert response.status_code in (200, 503)
    data = response.get_json()
    assert 'status' in data
