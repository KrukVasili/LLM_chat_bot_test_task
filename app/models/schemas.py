from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Тело запроса POST /chat"""

    message: Annotated[str, Field(min_length=1, max_length=4096)]
    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        """Убираем лишние пробелы, но сохраняем переносы строк"""
        return v.strip()


class CreateSessionRequest(BaseModel):
    """Опционально: явное создание сессии с параметрами"""

    model_name: Optional[str] = None  # если поддерживаем несколько моделей
    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = None
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    """Базовый ответ на сообщение (без стриминга)"""

    session_id: UUID
    role: Literal["assistant"] = "assistant"
    content: str
    tokens_used: Optional[int] = None
    created_at: datetime


class StreamChunk(BaseModel):
    """Фрагмент для SSE-стриминга"""

    session_id: UUID
    delta: str  # новый токен/часть токена
    finish_reason: Optional[Literal["stop", "length", "error"]] = None
    tokens_used: Optional[int] = None


class HistoryItem(BaseModel):
    """Элемент истории диалога"""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    tokens: Optional[int] = None


class SessionHistory(BaseModel):
    """Ответ GET /chat/{session_id}/history"""

    session_id: UUID
    messages: list[HistoryItem]
    model_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SessionMeta(BaseModel):
    """Краткая информация о сессии"""

    session_id: UUID
    model_name: str
    temperature: float
    created_at: datetime
    updated_at: datetime
    message_count: int
