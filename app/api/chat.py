from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ChatRequest, ChatResponse, CreateSessionRequest, SessionHistory
from app.repositories import MessageRepository, SessionRepository
from app.services.llm_service import LLMService

settings = get_settings()
log = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])


def get_session_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SessionRepository:
    return SessionRepository(db)


def get_message_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> MessageRepository:
    return MessageRepository(db)


async def get_llm_service(request: Request) -> LLMService:
    if not hasattr(request.app.state, "llm_service"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service not ready",
        )
    return request.app.state.llm_service


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={501: {"description": "Under construction."}},
)
async def send_message(
    request: ChatRequest,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
    db: AsyncSession = Depends(get_db),
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)] = None,
    message_repo: Annotated[MessageRepository, Depends(get_message_repo)] = None,
    llm: Annotated[LLMService, Depends(get_llm_service)] = None,
) -> ChatResponse:
    """
    Отправить сообщение в чат.
    Если X-Session-Id не передан --- создастся новая сессия.
    """

    # Управление сессией
    if session_id:
        session = await session_repo.get_by_id(session_id)
    else:
        session = await session_repo.create(
            CreateSessionRequest(
                model_name=str(settings.llm.model_path), temperature=request.temperature
            )
        )
        session_id = session.id

    # Загрзука истории для контекста
    history_limit = settings.chat.history_limit
    history_db = await message_repo.get_last_n(session_id, history_limit)
    history_dicts = [{"role": m.role, "content": m.content} for m in history_db]

    # Генерация ответа
    temperature = request.temperature or session.generation_params.get("temperature")
    prompt = llm.format_prompt(history_dicts, request.message)

    try:
        assistant_text, tokens_used = await llm.generate_response(
            prompt, temperature=temperature
        )
    except Exception as e:
        log.error("LLM generation failed", error=str(e), exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to generate response"
        )

    # Сохранение в БД
    await message_repo.create(session_id, "user", request.message)
    await message_repo.create(
        session_id, "assistant", assistant_text, tokens_count=tokens_used
    )
    await db.commit()

    # Формирование ответа
    return ChatResponse(
        session_id=session_id,
        role="assistant",
        content=assistant_text,
        tokens_used=tokens_used,
        created_at=datetime.now(timezone.utc),
    )


@router.get(
    "/{session_id}/history",
    response_model=SessionHistory,
    status_code=status.HTTP_200_OK,
)
async def get_history(
    session_id: str,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)] = None,
) -> SessionHistory:
    try:
        return await session_repo.get_history(session_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Session not found"}},
)
async def delete_session(
    session_id: str,
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)] = None,
) -> None:
    deleted = await session_repo.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
