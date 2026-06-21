from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from app.extensions import db

health_bp = Blueprint('health', __name__)


@health_bp.get('/health')
def health():
    return jsonify({
        'status': 'ok',
        'version': current_app.config.get('APP_VERSION', '0.1.0'),
    })


@health_bp.get('/health/db')
def health_db():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception:
        return jsonify({'status': 'error', 'database': 'unavailable'}), 503
