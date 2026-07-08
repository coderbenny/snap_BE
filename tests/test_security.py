"""Verify security headers are present on every response."""


class TestSecurityHeaders:
    def test_content_type_options(self, client):
        res = client.get('/health')
        assert res.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_frame_options(self, client):
        res = client.get('/health')
        assert res.headers.get('X-Frame-Options') == 'DENY'

    def test_xss_protection(self, client):
        res = client.get('/health')
        assert res.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy(self, client):
        res = client.get('/health')
        assert res.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_hsts_absent_in_testing(self, client):
        res = client.get('/health')
        assert 'Strict-Transport-Security' not in res.headers

    def test_request_id_header_present(self, client):
        res = client.get('/health')
        assert res.headers.get('X-Request-ID') != ''

    def test_request_id_is_uuid(self, client):
        import uuid
        res = client.get('/health')
        request_id = res.headers.get('X-Request-ID', '')
        uuid.UUID(request_id)  # raises ValueError if not a valid UUID

    def test_headers_on_error_responses(self, client):
        res = client.get('/nonexistent-route-404')
        assert res.status_code == 404
        assert res.headers.get('X-Content-Type-Options') == 'nosniff'
