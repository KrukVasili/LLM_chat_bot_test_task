from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    host: str = Field(default="0.0.0.0", description="Хост для запуска uvicorn")
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = Field(
        default=False, description="Режим отладки (влияет на логи и CORS)"
    )


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default="sqlite+aiosqlite:///./",
        description="Async SQLAlchemy URL. Для SQLite: sqlite+aiosqlite:///<path>",
    )
    pool_size: int = Field(default=5, ge=1)
    echo: bool = Field(default=False, description="Логировать SQL-запросы (только dev)")


class LLMSettings(BaseSettings):
    model_path: Path = Field(
        default=Path("models/model.q4_k_m.gguf"),
        description="Путь к GGUF-модели. Обязательно квантованная q4_k_m или аналог.",
    )
    context_window: int = Field(default=4096, ge=512, description="N_ctx для llama.cpp")
    n_gpu_layers: int = Field(
        default=0, ge=0, description="0 = CPU-only. >0 = offload на GPU."
    )


class ChatSettings(BaseSettings):
    history_limit: int = Field(
        default=20, ge=4, description="Макс. сообщений в контексте диалога"
    )
    max_tokens_per_response: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class LogSettings(BaseSettings):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    format: Literal["console", "json"] = Field(default="console")


class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    log: LogSettings = Field(default_factory=LogSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    """
    # Пример валидации:
    @field_validator("llm.model_path")
    @classmethod
    def check_model_exists(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"LLM model file not found: {v.resolve()}")
        return v
    """

    # другие валидаторы...


def get_settings() -> Settings:
    """Фабрика конфига. Вызывается один раз при старте, далее переиспользуется."""
    return Settings()
