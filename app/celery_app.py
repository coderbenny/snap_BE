from celery import Celery
from celery.schedules import crontab

celery = Celery()


def init_celery(app):
    """Bind the Celery instance to the Flask app and configure it."""

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.config_from_object(app.config, namespace='CELERY')
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
