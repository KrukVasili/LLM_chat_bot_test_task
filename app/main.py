from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.chat import router as chat_router
from app.core.config import get_settings
from app.core.database import engine, get_db
from app.core.logging import setup_logging
from app.models.db import Base
from app.services.llm_service import LLMService

settings = get_settings()
setup_logging(settings.log)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Управление жизненным циклом приложения.
    Startup: конфиг, логи, проверка БД.
    Shutdown: корректное закрытие пула соединений.
    """
    # Startup
    logger.info(
        "Application starting",
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
        db_url=settings.db.url,
        model_path=settings.llm.model_path,
    )
    # connection
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database connection established")

        app.state.llm_service = await LLMService.create(settings.llm, settings.chat)
        logger.info("LLM Service initialized successfully")

    except Exception as e:
        logger.critical("Startup failed", error=str(e), exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Graceful shutdown initiated")

    if hasattr(app.state, "llm_service"):
        await app.state.llm_service.close()
    await engine.dispose()
    logger.info("Application shut down gracefully")


app = FastAPI(
    title="LLM Chat Microservice",
    version="0.1.0",
    description="Production-ready chat service with LLM inference",
    lifespan=lifespan,
    docs_url="/docs" if settings.app.debug else None,
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


app.include_router(chat_router, prefix="/api/v1", tags=["chat"])

# TODO: exception_handler, health_check, root_endpoint,
