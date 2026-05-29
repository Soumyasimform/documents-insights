# Document Insights API

A backend service that accepts document text, processes it asynchronously with simulated AI summarization, and returns structured summaries.

## Quick Start

```bash
# 1. Copy the example env file and adjust values if needed
cp .env.example .env

# 2. Start the full stack
docker-compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/documents` | Submit a document for processing |
| `GET` | `/documents/{id}` | Poll processing status and result |
| `GET` | `/users/{user_id}/documents` | List user's documents (paginated) |
| `GET` | `/health` | Service health check |

### Submit a document
```bash
curl -X POST http://localhost:8000/documents \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "title": "My Report", "content": "The quick brown fox..."}'
```

### Poll for status
```bash
curl http://localhost:8000/documents/<document_id>
```

### List documents
```bash
curl "http://localhost:8000/users/alice/documents?page=1&page_size=10&status=completed"
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

`.env` contains only environment-specific values:

| Variable | Docker default | Description |
|----------|----------------|-------------|
| `MONGODB_URL` | `mongodb://mongo:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `document_insights` | Database name |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG` / `INFO` / `WARNING` / `ERROR`) |

> **Local development (without Docker):** change the URLs in `.env` to `mongodb://localhost:27017` and `redis://localhost:6379/0`.

All other operational values (worker count, retry limits, cache TTLs, rate limits, summarizer behaviour) are fixed constants defined in `app/constants.py` and do not require environment configuration.

## Design Decisions

**Background workers** — asyncio tasks spawned inside the FastAPI lifespan, no Celery. Keeps things simple; tradeoff is a single uvicorn worker process is required.

**Rate limiting** — a Redis Lua script atomically checks and increments a per-user counter so the read and write can't race. If Redis is down, falls back to a MongoDB count query.

**Content deduplication** — SHA-256 hash on every submission, two checks:
1. Before inserting, check if the same user already has a `queued`, `processing`, or `completed` record for that hash. If yes, return it — no new record. `failed` is excluded intentionally so the user can retry.
2. At the worker, a Redis SETNX lock on the hash prevents two workers from summarising the same content at the same time (covers the case where two different users submit identical content concurrently). The second worker waits for the result and completes from cache.

**Retry** — failed jobs write a future `available_at` timestamp back to the queue instead of sleeping in the worker. Backoff is `5 × 2^retry` (5s, 10s, 20s). After 3 attempts the document is marked `failed`.

**Redis failure** — every Redis call catches `RedisError` and raises an internal `RedisUnavailableError`. Rate limiter falls back to MongoDB; cache treats it as a miss. Neither path crashes the API.

## MongoDB Schema

```
documents: {
  _id: ObjectId,
  user_id: str,
  title: str,
  content: str,
  content_hash: str (SHA-256 hex),
  status: queued | processing | completed | failed,
  summary: { summary, word_count, key_topics, sentiment } | null,
  error: str | null,
  retry_count: int,
  available_at: datetime,   ← backoff timestamp
  created_at: datetime,
  updated_at: datetime,
  processed_at: datetime | null
}
```

**Indexes:**
- `(user_id, status)` — rate limit fallback count + user document listing with status filter
- `(user_id, content_hash)` — dedup check: find existing record by user + content hash
- `(status, available_at)` — worker claim filter (status=queued, available_at ≤ now)
- `(status, created_at)` — worker FIFO ordering fallback

## Code Organisation

| File | Purpose |
|------|---------|
| `app/config.py` | Reads environment variables into a `Settings` object (`MONGODB_URL`, `REDIS_URL`, `LOG_LEVEL`) |
| `app/constants.py` | Fixed application constants — Redis key prefixes, worker/retry/cache/rate-limit values, app metadata |
| `app/messages.py` | All string literals — log event keys, HTTP error messages, summarizer strings |
| `app/models/` | Pydantic request/response models and the `DocumentStatus` enum |
| `app/routes/` | FastAPI route handlers (`/documents`, `/users`, `/health`) |
| `app/services/` | Business logic — document creation, caching, rate limiting, summarization |
| `app/worker/` | Background worker loop and atomic document claim logic |
| `app/db/` | MongoDB (Motor) and Redis async client setup |

## Running Tests

```bash
# Install dev dependencies (only needed once)
pip install -r requirements-dev.txt

# Run all tests with coverage
pytest --cov=app --cov-report=term-missing
```

Tests use `mongomock-motor` (in-memory MongoDB) and `fakeredis` (in-memory Redis) — no real databases needed.


## Assumptions Made

- Content deduplication is **per user** — same content from two different users creates separate records for each; the SETNX lock prevents duplicate processing at the worker level
- Same user resubmitting the same content returns the existing document (no new record), except after `failed` status which allows a retry
- The `10%` failure rate applies per processing attempt, not per document (a document can be unlucky multiple times)

## If I Had More Time

- **Proper authentication** — right now `user_id` is just a string the caller passes in, with no checks at all. I'd add JWT auth so users can only see their own documents and can't guess someone else's ID.
- **A real summarizer** — the current one is just a mock that sleeps and returns a template. I'd swap it out for an actual LLM call (OpenAI or something self-hosted) behind the same `generate_summary` function, so nothing else in the codebase would need to change.
- **Scaling the workers out** — everything runs in one process right now, which is fine for a demo but wouldn't hold up under real load. I'd move the worker into its own service so you can run more of them independently without touching the API.