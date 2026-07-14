from celery import Celery
from celery.schedules import crontab

celery = Celery()


def init_celery(app):
    """Bind the Celery instance to the Flask app and configure it."""

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        broker_connection_retry_on_startup=True,
    )
    celery.conf.include = ['app.tasks.email_tasks']
    celery.Task = ContextTask

    celery.conf.beat_schedule = {
        'send-expiry-warnings-daily': {
            'task': 'app.tasks.email_tasks.send_expiry_warnings',
            'schedule': crontab(hour=8, minute=0),
        },
    }
    celery.conf.timezone = 'UTC'
    return celery
