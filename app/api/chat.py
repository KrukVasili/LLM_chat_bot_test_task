import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Annotated, Union

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ChatRequest, CreateSessionRequest, SessionHistory
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


def format_sse(data: Union[str, dict], event: str = "message") -> str:
    """
    Формирует строку SSE.
    Если data — строка, кладёт её как есть. Если dict — сериализует в JSON.
    """
    if isinstance(data, dict):
        payload = json.dumps(data, ensure_ascii=False)
    else:
        payload = data

    return f"event: {event}\ndata: {payload}\n\n"


@router.post(
    "",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "SSE stream: meta - done/error"},
    },
)
async def send_message_stream(
    request: ChatRequest,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
    db: AsyncSession = Depends(get_db),
    session_repo: Annotated[SessionRepository, Depends(get_session_repo)] = None,
    message_repo: Annotated[MessageRepository, Depends(get_message_repo)] = None,
    llm: Annotated[LLMService, Depends(get_llm_service)] = None,
):
    """
    Отправить сообщение в чат с потоковой генерацией (SSE).

    События:
    - meta: начало ответа (session_id, created_at)
    - message: новый токен (delta)
    - done: генерация завершена (tokens_used, finish_reason)
    - error: произошла ошибка
    """
    if session_id:
        session = await session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = await session_repo.create(
            CreateSessionRequest(
                model_name=str(settings.llm.model_path),
                temperature=request.temperature,
            )
        )
        session_id = session.id

    history_limit = settings.chat.history_limit
    history_db = await message_repo.get_last_n(session_id, history_limit)
    history_dicts = [{"role": m.role, "content": m.content} for m in history_db]

    temperature = (
        request.temperature
        or session.generation_params.get("temperature")
        or getattr(settings.llm, "temperature", 0.7)
    )
    max_tokens = settings.chat.max_tokens_per_response
    prompt = llm.format_prompt(history_dicts, request.message)

    await message_repo.create(session_id, "user", request.message)
    await db.commit()

    async def event_generator():
        tokens_collected: list[str] = []
        created_at = datetime.now(timezone.utc)

        request_start = time.perf_counter()
        first_token_time: float | None = None

        try:
            yield format_sse(
                {
                    "session_id": str(session_id),
                    "created_at": created_at.isoformat(),
                },
                event="meta",
            )

            async for token in llm.stream_response(prompt, temperature, max_tokens):
                if first_token_time is None:
                    first_token_time = time.perf_counter()

                tokens_collected.append(token)
                yield format_sse(token, event="message")

            assistant_text = "".join(tokens_collected)

            generation_end = time.perf_counter()
            total_time_sec = generation_end - request_start
            ttft_ms = (
                (first_token_time - request_start) * 1000 if first_token_time else None
            )
            tokens_per_sec = (
                len(tokens_collected) / total_time_sec if total_time_sec > 0 else 0
            )

            token_ids = llm._model.tokenize(
                assistant_text.encode("utf-8"),
                add_bos=False,
            )
            tokens_used = len(token_ids)

            await message_repo.create(
                session_id, "assistant", assistant_text, tokens_count=tokens_used
            )
            await db.commit()

            log.info(
                "chat_generation_completed",
                session_id=str(session_id),
                tokens_used=tokens_used,
                tokens_generated=len(tokens_collected),
                ttft_ms=round(ttft_ms, 2) if ttft_ms else None,
                total_time_sec=round(total_time_sec, 3),
                tokens_per_sec=round(tokens_per_sec, 2),
                content_length=len(assistant_text),
            )

            yield format_sse(
                {
                    "finish_reason": "stop",
                    "tokens_used": tokens_used,
                    "content_length": len(assistant_text),
                },
                event="done",
            )

        except asyncio.CancelledError:
            log.info("Stream cancelled by client", session_id=session_id)
            await db.rollback()
            yield format_sse("cancelled", event="error")

        except Exception as e:
            log.error("Stream generation failed", error=str(e), exc_info=True)
            await db.rollback()
            yield format_sse("error", event="error")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
