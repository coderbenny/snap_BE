import os
import time
import uuid

import structlog
from flask import Flask, g, request

from app.config import config_by_name
from app.extensions import db, limiter, migrate
from app.logging_config import configure_logging

_logger = structlog.get_logger('snap.requests')


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    configure_logging(debug=app.debug)
    _init_sentry(app)

    from app import models  # noqa: F401 — registers all tables with SQLAlchemy metadata

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    _register_blueprints(app)
    _register_hooks(app)
    _register_error_handlers(app)

    return app


def _init_sentry(app: Flask) -> None:
    dsn = app.config.get('SENTRY_DSN', '')
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )


def _register_blueprints(app: Flask) -> None:
    from flask import Blueprint

    from app.routes.auth import auth_bp
    from app.routes.billing import billing_bp
    from app.routes.devices import devices_bp
    from app.routes.events import events_bp
    from app.routes.health import health_bp
    from app.routes.sync import sync_bp
    from app.routes.teams import teams_bp
    from app.routes.webhooks import webhooks_bp

    # /health lives at root so the infra health check always works
    app.register_blueprint(health_bp)

    # All API routes live under /snap
    api = Blueprint('api', __name__, url_prefix='/snap')
    api.register_blueprint(auth_bp)
    api.register_blueprint(devices_bp)
    api.register_blueprint(events_bp)
    api.register_blueprint(sync_bp)
    api.register_blueprint(billing_bp)
    api.register_blueprint(webhooks_bp)
    api.register_blueprint(teams_bp)
    app.register_blueprint(api)


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _before_request():
        g.request_id = str(uuid.uuid4())
        g.start_time = time.monotonic()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=g.request_id)

    @app.after_request
    def _after_request(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug and not app.testing:
            response.headers['Strict-Transport-Security'] = (
                'max-age=63072000; includeSubDomains'
            )

        response.headers['X-Request-ID'] = g.get('request_id', '')

        if hasattr(g, 'start_time'):
            duration_ms = round((time.monotonic() - g.start_time) * 1000, 2)
            _logger.info(
                'request_completed',
                method=request.method,
                path=request.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )

        return response


def _register_error_handlers(app: Flask) -> None:
    from app.utils.errors import error_response

    @app.errorhandler(404)
    def handle_404(e):
        return error_response('NOT_FOUND', 'Resource not found', 404)

    @app.errorhandler(405)
    def handle_405(e):
        return error_response('METHOD_NOT_ALLOWED', 'Method not allowed', 405)

    @app.errorhandler(500)
    def handle_500(e):
        _logger.exception('unhandled_exception', exc_info=e)
        return error_response('INTERNAL_ERROR', 'An unexpected error occurred', 500)
