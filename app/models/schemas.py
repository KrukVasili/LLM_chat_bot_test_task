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
    """Явное создание сессии с параметрами"""

    model_name: Optional[str] = None
    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = None
    system_prompt: Optional[str] = None


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
