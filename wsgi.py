import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app          # noqa: E402
from app.celery_app import celery   # noqa: E402 — re-exported for `celery -A wsgi.celery`

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5559)
