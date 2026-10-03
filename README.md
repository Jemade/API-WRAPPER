# LLM API Gateway

[![CI](https://github.com/Jemade/API-WRAPPER/actions/workflows/ci.yml/badge.svg)](https://github.com/Jemade/API-WRAPPER/actions/workflows/ci.yml)

A FastAPI service that gives client applications a common generation API across Gemini, OpenAI, and Anthropic, with authentication, rate limiting, retries, and delivery records.

## Features

- Client API keys stored as hashes.
- Redis sliding-window rate limiting with configurable failure policy.
- Provider adapters and normalized generation responses.
- Bounded retries for transient upstream failures.
- HMAC-signed webhook delivery and persisted delivery records.
- Structured logging with correlation IDs.
- SQLite development storage and PostgreSQL support.

## Run locally

Requires Python 3.12 or newer. Redis is required for distributed rate limiting; a live provider key is required for generation.

```bash
git clone https://github.com/Jemade/API-WRAPPER.git
cd API-WRAPPER
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
PYTHONPATH=. python scripts/create_api_key.py --name local-client
uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080/docs. Save the generated client key; only its hash is retained.

Defaults use SQLite. Configure provider keys, `REDIS_URL`, `WEBHOOK_SECRET`, and `DATABASE_URL` through environment variables or `.env`. The example file selects PostgreSQL, so adjust it to match your local database before loading it.

## Containers and tests

```bash
docker compose up --build
pytest -q
```

## Documentation

- [Architecture](docs/architecture.md)
- [Demonstration](docs/demo.md)
- [Client example](examples/client.py)

## Current scope

This is a generation gateway, not a transparent implementation of every provider endpoint. Webhook records are persisted, but delivery runs in process rather than through a separate durable outbox worker. The Redis failure policy determines whether traffic is allowed or rejected during a Redis outage.
