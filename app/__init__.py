import os
from flask import Flask
from app.config import config_by_name
from app.extensions import db, migrate, limiter


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    _register_blueprints(app)
    _register_error_handlers(app)

    return app


def _register_blueprints(app):
    from app.routes.health import health_bp
    app.register_blueprint(health_bp)


def _register_error_handlers(app):
    from app.utils.errors import error_response

    @app.errorhandler(404)
    def handle_404(e):
        return error_response('NOT_FOUND', 'Resource not found', 404)

    @app.errorhandler(405)
    def handle_405(e):
        return error_response('METHOD_NOT_ALLOWED', 'Method not allowed', 405)

    @app.errorhandler(500)
    def handle_500(e):
        return error_response('INTERNAL_ERROR', 'An unexpected error occurred', 500)
