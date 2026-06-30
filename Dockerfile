FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -r -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5559

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5559/health')" || exit 1

ENV GUNICORN_WORKERS=4 \
    GUNICORN_TIMEOUT=60 \
    GUNICORN_KEEPALIVE=5

CMD gunicorn \
    --bind 127.0.0.1:5559 \
    --workers ${GUNICORN_WORKERS} \
    --timeout ${GUNICORN_TIMEOUT} \
    --keep-alive ${GUNICORN_KEEPALIVE} \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    wsgi:app
