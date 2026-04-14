from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from structlog.contextvars import merge_contextvars
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

if TYPE_CHECKING:
    from app.core.config import LogSettings


def setup_logging(config: LogSettings) -> None:
    """Инициализирует structlog один раз. Вызывается в lifespan приложения."""
    # 1. Базовый пайплайн процессоров (общий для dev/prod)
    processors = [
        merge_contextvars,  # Подтягивает request_id, session_id и др.
        add_log_level,  # Добавляет поле "level"
        TimeStamper(fmt="iso"),  # ISO 8601 timestamp
    ]

    # 2. Последний процессор зависит от окружения
    if config.format == "json":
        processors.append(JSONRenderer())
    else:
        processors.append(ConsoleRenderer(colors=True))

    # 3. Применяем конфигурацию
    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(config.level),
        cache_logger_on_first_use=True,
    )

    # 4. Отключаем стандартные логи uvicorn, чтобы не дублировались
    import logging

    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn").handlers = []
