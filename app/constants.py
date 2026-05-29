from __future__ import annotations

# MongoDB
MONGO_COLLECTION_DOCUMENTS = "documents"

# Redis key prefixes  (usage: f"{PREFIX}:{key}")
REDIS_RATE_LIMIT_PREFIX = "rate_limit"
REDIS_CONTENT_CACHE_PREFIX = "content_cache"
REDIS_CONTENT_LOCK_PREFIX = "content_lock"

# App metadata
APP_TITLE = "Document Insights API"
APP_DESCRIPTION = "Async document summarization service"
APP_VERSION = "1.0.0"

# Health check response values
HEALTH_STATUS_OK = "ok"
HEALTH_STATUS_DEGRADED = "degraded"

# Summarizer mock output
MOCK_SUMMARY_SENTIMENT = "neutral"
MOCK_SUMMARY_SUFFIX = "[Mock AI Summary]"

# Worker
WORKER_COUNT = 3
WORKER_POLL_INTERVAL = 2
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5

# Rate limiting
RATE_LIMIT_MAX = 3

# Cache / content lock
CACHE_TTL_SECONDS = 86400
CONTENT_LOCK_TTL_SECONDS = 120
CONTENT_LOCK_WAIT_SECONDS = 60

# Summarizer (mock AI)
SUMMARIZER_MIN_DELAY: float = 10.0
SUMMARIZER_MAX_DELAY: float = 30.0
SUMMARIZER_FAILURE_RATE: float = 0.10
