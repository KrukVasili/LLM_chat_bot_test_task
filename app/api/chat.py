from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ChatRequest, ChatResponse, SessionHistory
from app.repositories import MessageRepository, SessionRepository

log = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])


def get_session_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SessionRepository:
    return SessionRepository(db)


def get_message_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> MessageRepository:
    return MessageRepository(db)


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    responses={501: {"description": "Under construction."}},
)
async def send_message(
    request: ChatRequest,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)] = None,
    message_repo: Annotated[MessageRepository, Depends(get_message_repo)] = None,
) -> ChatResponse:
    """
    Отправить сообщение в чат.
    Если X-Session-Id не передан --- создастся новая сессия.
    """
    # Заглушка
    log.info(
        "Message received",
        session_id=session_id or "new",
        message_length=len(request.message),
    )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="ChatService will be implemented next. Repository & routing are ready.",
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
