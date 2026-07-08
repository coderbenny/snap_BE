# SNAP Server

![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/flask-3.0.3-black?logo=flask)
![License](https://img.shields.io/badge/license-MIT-green)

The sync backbone for **SNAP** — a universal clipboard vault with a zero-knowledge architecture. The server handles authentication, encrypted clip synchronisation, device management, real-time plan events via SSE, and billing webhooks. It **never holds decryption keys**: all clipboard data is AES-256-GCM encrypted on the client before it reaches the wire.

---

## Features

- **Zero-knowledge sync** — server stores only ciphertext; encryption and decryption happen entirely on the client
- **JWT auth** — access + refresh token pair, with explicit logout / token invalidation
- **Encrypted clip sync** — pull with cursor-based pagination, push (Pro plan only)
- **Device management** — register, list, and revoke trusted devices
- **SSE plan events** — real-time push of plan change notifications to connected clients
- **Rate limiting** — Flask-Limiter, backed by Redis in production
- **Structured logging** — structlog with optional Sentry error tracking
- **Alembic migrations** — `render_as_batch` enabled for full SQLite compatibility in development
- **Docker-first** — dev compose stack included; production compose stack with Nginx also provided

---

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | Flask 3.0.3 |
| Language | Python 3.12 |
| ORM | SQLAlchemy 2.x |
| Migrations | Flask-Migrate (Alembic) |
| Auth tokens | PyJWT |
| Dev database | SQLite |
| Prod database | MySQL (PyMySQL driver) |
| Rate limiting | Flask-Limiter |
| Logging | structlog |
| Error tracking | Sentry SDK (optional) |
| Cache / rate-limit backend | Redis (optional, prod) |

---

## Prerequisites

- Python 3.12+
- pip
- Docker & Docker Compose (for the container workflow)
- Redis (optional — only required for the production rate-limit backend)

---

## Development Setup

### 1. Clone and enter the server directory

```bash
git clone https://github.com/coderbenny/snap_BE
cd snap_BE
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

See the [Environment Variables](#environment-variables) table below for all available options. At minimum you need `FLASK_SECRET_KEY` and `JWT_SECRET`.

### 5. Run database migrations

```bash
flask db upgrade
```

This applies all Alembic migrations. SQLite is used by default — no additional setup required.

### 6. Start the development server

```bash
flask run --host=0.0.0.0 --port=5559
```

The API is now available at `http://localhost:5559`.

---

## Docker Quickstart (Development)

Bring up the full dev stack (Flask + SQLite volume):

```bash
docker compose up --build
```

The server is exposed on port **5559**. Hot-reload is enabled via a bind mount.

To stop and remove containers:

```bash
docker compose down
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FLASK_SECRET_KEY` | Yes | — | Secret key for Flask session signing |
| `JWT_SECRET` | Yes | — | Secret used to sign JWT access and refresh tokens |
| `DATABASE_URL` | No | `sqlite:///snap.db` | SQLAlchemy database URL. Use `mysql+pymysql://...` for MySQL |
| `SENTRY_DSN` | No | — | Sentry DSN for error tracking. Omit to disable Sentry |
| `REDIS_URL` | No | — | Redis connection URL. Used as the Flask-Limiter backend in production. Omit to fall back to in-memory limiting |
| `FLASK_ENV` | No | `development` | Set to `production` to enable production-mode behaviour |

---

## API Overview

Full request/response schemas are documented in **`openapi.yaml`** at the repository root.

### Auth — `/auth`

| Method | Route | Description |
|---|---|---|
| `POST` | `/auth/register` | Create a new user account |
| `POST` | `/auth/login` | Authenticate and receive access + refresh tokens |
| `POST` | `/auth/refresh` | Exchange a valid refresh token for a new access token |
| `POST` | `/auth/logout` | Invalidate the current refresh token |

### Sync — `/sync`

| Method | Route | Plan | Description |
|---|---|---|---|
| `GET` | `/sync/pull` | Free + Pro | Pull clips newer than `?since=<cursor>` (ISO-8601 timestamp or sequence ID) |
| `POST` | `/sync/push` | Pro only | Push one or more encrypted clips to the vault |

### Devices — `/devices`

| Method | Route | Description |
|---|---|---|
| `POST` | `/devices/register` | Register the current device and receive a device ID |
| `GET` | `/devices` | List all devices associated with the authenticated account |
| `DELETE` | `/devices/<id>` | Revoke a device by ID |

### Events — `/events`

| Method | Route | Description |
|---|---|---|
| `GET` | `/events/stream` | Open an SSE stream to receive real-time plan change events |

---

## Database Migrations

Migrations are managed with **Flask-Migrate** (Alembic). All migration scripts use `render_as_batch=True` so that column alterations work correctly on SQLite (which does not support `ALTER COLUMN` natively).

### Common commands

```bash
# Apply all pending migrations
flask db upgrade

# Roll back the most recent migration
flask db downgrade

# Generate a new migration after changing models
flask db migrate -m "describe your change"

# Show current migration state
flask db current
```

When writing new migrations manually, always wrap operations inside `with op.batch_alter_table(...) as batch_op:` to maintain SQLite compatibility.

---

## Running Tests

```bash
# Install dev dependencies if not already present
pip install -r requirements-dev.txt

# Run the full test suite
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing
```

Tests use an in-memory SQLite database and a dedicated Flask test client — no external services required.

---

## Production Deployment

### Docker Compose (recommended)

A production compose file with an Nginx reverse proxy is provided:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This stack runs:
- **Flask** (via Gunicorn) on an internal network
- **Nginx** as the public-facing reverse proxy (port 443 / 80)
- **MySQL** as the database backend
- **Redis** as the rate-limit store

### Environment checklist for production

- Set `FLASK_ENV=production`
- Set a strong, randomly generated `FLASK_SECRET_KEY` and `JWT_SECRET`
- Point `DATABASE_URL` at your MySQL instance: `mysql+pymysql://user:password@host/dbname`
- Set `REDIS_URL` to your Redis instance URL
- Optionally set `SENTRY_DSN` for error tracking
- Run `flask db upgrade` as part of your deployment pipeline before starting the application

### Migrations in CI / CD

It is recommended to run `flask db upgrade` as a pre-start step (or a Kubernetes init container / ECS task) so migrations complete before traffic is served.

---

## License

MIT — see [LICENSE](LICENSE).
