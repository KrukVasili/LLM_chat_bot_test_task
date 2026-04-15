from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Message, Session
from app.models.schemas import CreateSessionRequest, HistoryItem, SessionHistory

log = structlog.get_logger()


class SessionRepository:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CreateSessionRequest) -> Session:
        """Создаёт новую сессию."""
        session = Session(
            model_name=data.model_name,
            generation_params=(
                {"temperature": data.temperature} if data.temperature else {}
            ),
        )
        self.db.add(session)
        log.info("Session created", session_id=session.id)
        return session

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        stmt = select(Session).where(Session.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, session_id: str) -> bool:
        session = await self.get_by_id(session_id)
        if not session:
            return False
        await self.db.delete(session)
        log.info("Session deleted", session_id=session_id)
        return True

    async def get_history(self, session_id: str, limit: int = 20) -> SessionHistory:
        session = await self.get_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        history_items = [
            HistoryItem(
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                tokens=m.tokens_count,
            )
            for m in messages
        ]

        return SessionHistory(
            session_id=session_id,
            messages=history_items,
            model_name=session.model_name,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
