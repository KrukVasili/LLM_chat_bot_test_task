from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import chat as chat_router
from app.core.config import get_settings
from app.core.database import engine, get_db
from app.core.logging import setup_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Управление жизненным циклом приложения.
    Startup: конфиг, логи, проверка БД.
    Shutdown: корректное закрытие пула соединений.
    """
    # Startup
    settings = get_settings()
    setup_logging(settings.log)

    logger = structlog.get_logger()
    logger.info(
        "Application starting",
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
        db_url=settings.db.url,
    )
    # DB connection check
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Database connection failed", error=str(e))

    yield

    # Shutdown
    logger.info("Graceful shutdown initiated")

    if isinstance(engine, AsyncEngine):
        await engine.dispose()
        logger.info("Database engine disposed")

    # TODO: llm engine


def create_app() -> FastAPI:
    """Factory-паттерн для создания приложения. Упрощает тестирование и конфигурирование."""
    settings = get_settings()

    app = FastAPI(
        title="LLM Chat Microservice",
        version="0.1.0",
        description="Production-ready chat service with LLM inference (llama-cpp-python, GGUF)",
        lifespan=lifespan,
        docs_url="/docs" if settings.app.debug else None,
        openapi_url="/openapi.json" if settings.app.debug else None,
    )

    # Middleware
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid4()))
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid4()),
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        logger = structlog.get_logger()
        logger.info("HTTP request started")

        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            logger.info(
                "HTTP request completed",
                status_code=response.status_code,
                duration_ms=getattr(response, "_duration_ms", None),
            )
            return response
        except Exception as e:
            logger.error("HTTP request failed", error=str(e), exc_info=True)
            raise

    # TODO: exception_handler, health_check, root_endpoint,

    # routers
    app.include_router(
        chat_router.router,
        prefix="/api/v1",
        tags=["chat"],
    )

    return app


# Глобальная точка входа для uvicorn / docker
app = create_app()
