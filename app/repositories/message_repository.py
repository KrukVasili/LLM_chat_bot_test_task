import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message

log = structlog.get_logger()


class MessageRepository:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self, session_id: str, role: str, content: str, tokens_count: int | None = None
    ) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            tokens_count=tokens_count,
        )
        self.db.add(msg)
        return msg

    async def get_last_n(self, session_id: str, n: int) -> list[Message]:
        """Возвращает N последних сообщений."""
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(n)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        return list(reversed(messages))
