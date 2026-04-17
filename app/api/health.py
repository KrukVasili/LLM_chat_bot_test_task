from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """
    Эндпоинт для Docker healthcheck.
    Проверяет готовность LLM и доступность БД.
    """
    try:
        llm_ready = (
            hasattr(request.app.state, "llm_service")
            and request.app.state.llm_service._model is not None
        )

        async with engine.begin() as conn:
            await conn.execute(select(1))

        response_status = (
            status.HTTP_200_OK if llm_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            status_code=response_status,
            content={
                "status": "ok" if llm_ready else "loading",
                "llm": llm_ready,
                "db": "ok",
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "detail": str(e)},
        )
