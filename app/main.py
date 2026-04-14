from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response

from app.core.config import get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управление жизненным циклом приложения (startup / shutdown)."""
    # 1. Загружаем конфиг ОДИН раз
    settings = get_settings()

    # 2. Инициализируем логирование с учётом настроек из конфига
    setup_logging(settings.log)

    logger = structlog.get_logger()
    logger.info(
        "Application starting",
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
    )

    # TODO: Здесь позже будет инициализация БД, LLM-движка, кэшей и т.д.
    yield  # Сервер работает

    logger.info("Graceful shutdown initiated")
    # TODO: Здесь позже будет закрытие пула БД, выгрузка модели, очистка кэшей


def create_app() -> FastAPI:
    """Factory-паттерн для создания приложения. Упрощает тестирование и конфигурирование."""
    settings = get_settings()

    app = FastAPI(
        title="LLM Chat Microservice",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Middleware для изоляции контекста запросов
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid4()),
            method=request.method,
            path=request.url.path,
        )
        logger = structlog.get_logger()
        logger.info("HTTP request started")

        try:
            response = await call_next(request)
            logger.info("HTTP request completed", status_code=response.status_code)
            return response
        except Exception as e:
            logger.error("HTTP request failed", error=str(e), exc_info=True)
            raise

    # Простой health-check для проверки запуска
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Глобальная точка входа для uvicorn / docker
app = create_app()
