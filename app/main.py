from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.constants import APP_DESCRIPTION, APP_TITLE, APP_VERSION, WORKER_COUNT
from app.db.mongo import close_mongo, init_mongo
from app.db.redis_client import close_redis, init_redis
from app.routes import documents, health, users
from app.worker.processor import worker_loop


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.log_level == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    await init_mongo()
    await init_redis()

    tasks: list[asyncio.Task] = []
    if not getattr(app.state, "skip_worker", False):
        tasks = [
            asyncio.create_task(worker_loop(i), name=f"worker-{i}")
            for i in range(WORKER_COUNT)
        ]

    yield

    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await close_mongo()
    await close_redis()


def create_app(skip_worker: bool = False) -> FastAPI:
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
    )
    app.state.skip_worker = skip_worker

    app.include_router(documents.router)
    app.include_router(users.router)
    app.include_router(health.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": str(exc.body)},
        )

    return app


app = create_app()
