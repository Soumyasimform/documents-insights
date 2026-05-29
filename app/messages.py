from __future__ import annotations

# HTTP error messages
ERR_DOCUMENT_NOT_FOUND = "Document not found"
ERR_RATE_LIMIT_EXCEEDED = "Rate limit exceeded: max {limit} active documents per user"

# Summarizer
ERR_SIMULATED_PROCESSING_FAILURE = "Simulated AI processing failure"

# Log events — document service
LOG_CACHE_HIT = "cache_hit"
LOG_DOCUMENT_CREATED = "document_created"

# Log events — worker / processor
LOG_PROCESSING_STARTED = "processing_started"
LOG_PROCESSING_COMPLETED = "processing_completed"
LOG_PROCESSING_COMPLETED_FROM_CACHE = "processing_completed_from_concurrent_cache"
LOG_PROCESSING_FAILED_WILL_RETRY = "processing_failed_will_retry"
LOG_PROCESSING_FAILED_PERMANENTLY = "processing_failed_permanently"
LOG_WAITING_FOR_CONCURRENT_DUPLICATE = "waiting_for_concurrent_duplicate"
LOG_CONCURRENT_CACHE_WAIT_TIMED_OUT = "concurrent_cache_wait_timed_out_proceeding"
LOG_DUPLICATE_DOCUMENT_FOUND = "duplicate_document_found"
LOG_WORKER_STARTED = "worker_started"
LOG_WORKER_STOPPED = "worker_stopped"
LOG_WORKER_UNEXPECTED_ERROR = "worker_unexpected_error"

# Log events — MongoDB
LOG_MONGODB_CONNECTED = "mongodb_connected"
LOG_MONGODB_CLOSED = "mongodb_closed"
LOG_MONGODB_INDEXES_CREATED = "mongodb_indexes_created"

# Log events — Redis
LOG_REDIS_CONNECTED = "redis_connected"
LOG_REDIS_CLOSED = "redis_closed"
LOG_REDIS_UNAVAILABLE_AT_STARTUP = "redis_unavailable_at_startup"
LOG_REDIS_RATE_LIMIT_UNAVAILABLE = "redis_rate_limit_unavailable"
LOG_REDIS_RATE_LIMIT_DECR_FAILED = "redis_rate_limit_decr_failed"
LOG_REDIS_CACHE_GET_FAILED = "redis_cache_get_failed"
LOG_REDIS_CACHE_SET_FAILED = "redis_cache_set_failed"
LOG_REDIS_LOCK_FAILED = "redis_lock_failed"

# Log events — rate limiter
LOG_RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
LOG_RATE_LIMIT_REDIS_FALLBACK = "rate_limit_redis_fallback"

# Log events — cache service
LOG_CACHE_GET_UNAVAILABLE = "cache_get_unavailable"
