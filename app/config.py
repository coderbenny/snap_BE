import os
from datetime import timedelta

from sqlalchemy.pool import StaticPool


class BaseConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    APP_VERSION = os.environ.get('APP_VERSION', '0.1.0')
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://snapit.ink')
    RATELIMIT_HEADERS_ENABLED = True
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
    PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET', '')
    PAYSTACK_PLANS = {
        'pro': os.environ.get('PAYSTACK_PLAN_PRO', ''),
        'pro_ai': os.environ.get('PAYSTACK_PLAN_PRO_AI', ''),
        'team': os.environ.get('PAYSTACK_PLAN_TEAM', ''),
    }
    # Celery — uses Redis as both broker and result backend
    CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']

    # Email — Resend is primary; Google SMTP is the fallback.
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    MAIL_FROM = os.environ.get('MAIL_FROM', 'Snapit <hello@snapit.ink>')
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://snap:snap@localhost:3306/snap_dev',
    )
    RATELIMIT_STORAGE_URI = 'memory://'


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},
        'poolclass': StaticPool,
    }
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = 'memory://'
    PAYSTACK_WEBHOOK_SECRET = 'test-webhook-secret'
    PAYSTACK_PLANS = {
        'pro': 'PLN_test_pro',
        'pro_ai': 'PLN_test_pro_ai',
        'team': 'PLN_test_team',
    }


_POOL_OPTIONS = {
    'pool_size': 10,
    'pool_recycle': 300,  # prevent "server has gone away" on idle connections
    'pool_pre_ping': True,
    'max_overflow': 20,
}


class StagingConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = _POOL_OPTIONS
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = _POOL_OPTIONS
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL')


config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
}
