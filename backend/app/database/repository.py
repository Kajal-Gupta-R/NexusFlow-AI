import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from math import sqrt

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Conversation, Memory, Message, TaskHistory, User

SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|password|passwd|secret|token|bearer)\s*[:=]\s*\S+"
)


def is_safe_memory(text: str) -> bool:
    return bool(text.strip()) and not SENSITIVE_PATTERN.search(text)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_user(self, user_id: str) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            user = User(user_id=user_id)
            self.session.add(user)
            await self.session.flush()
        return user

    async def create_memory(
        self, user_id: str, text: str, memory_type: str, embedding: list[float] | None
    ) -> Memory:
        if not is_safe_memory(text):
            raise ValueError("This memory contains sensitive information and cannot be saved.")
        await self.ensure_user(user_id)
        existing = await self.session.scalar(
            select(Memory).where(Memory.user_id == user_id, Memory.memory_text == text)
        )
        if existing:
            return existing
        memory = Memory(
            memory_id=str(uuid.uuid4()),
            user_id=user_id,
            memory_text=text,
            memory_type=memory_type,
            embedding=embedding,
        )
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def list_memories(self, user_id: str, limit: int = 50) -> list[Memory]:
        return list(
            (
                await self.session.scalars(
                    select(Memory)
                    .where(Memory.user_id == user_id)
                    .order_by(Memory.updated_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def retrieve_memories(
        self, user_id: str, query_embedding: list[float] | None, query: str, limit: int = 5
    ) -> list[Memory]:
        memories = await self.list_memories(user_id, limit=200)
        if query_embedding:
            memories.sort(
                key=lambda memory: cosine_similarity(memory.embedding or [], query_embedding),
                reverse=True,
            )
            return [
                memory
                for memory in memories
                if cosine_similarity(memory.embedding or [], query_embedding) > 0.15
            ][:limit]
        terms = {term.lower() for term in re.findall(r"\w+", query) if len(term) > 2}
        memories.sort(
            key=lambda memory: len(terms.intersection(memory.memory_text.lower().split())),
            reverse=True,
        )
        return [memory for memory in memories if terms.intersection(memory.memory_text.lower().split())][:limit]

    async def delete_memory(self, user_id: str, memory_id: str) -> bool:
        result = await self.session.execute(
            delete(Memory).where(Memory.memory_id == memory_id, Memory.user_id == user_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def save_conversation(
        self, user_id: str, title: str, user_message: str, assistant_message: str
    ) -> str:
        await self.ensure_user(user_id)
        conversation = Conversation(conversation_id=str(uuid.uuid4()), user_id=user_id, title=title)
        conversation.messages = [
            Message(message_id=str(uuid.uuid4()), role="user", content=user_message),
            Message(message_id=str(uuid.uuid4()), role="assistant", content=assistant_message),
        ]
        self.session.add(conversation)
        await self.session.commit()
        return conversation.conversation_id

    async def list_conversations(self, user_id: str, limit: int = 25) -> list[Conversation]:
        return list(
            (
                await self.session.scalars(
                    select(Conversation)
                    .where(Conversation.user_id == user_id)
                    .order_by(Conversation.updated_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def get_conversation(self, user_id: str, conversation_id: str) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.user_id == user_id,
                Conversation.conversation_id == conversation_id,
            )
        )

    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        result = await self.session.execute(
            delete(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.conversation_id == conversation_id,
            )
        )
        await self.session.commit()
        return result.rowcount > 0

    async def save_task(
        self,
        user_id: str,
        task_id: str,
        description: str,
        agents_used: list[str],
        result_summary: str,
        status: str,
    ) -> None:
        await self.ensure_user(user_id)
        self.session.add(
            TaskHistory(
                task_id=task_id,
                user_id=user_id,
                task_description=description,
                agents_used=agents_used,
                result_summary=result_summary,
                status=status,
            )
        )
        await self.session.commit()

    async def create_queued_task(
        self,
        user_id: str,
        task_id: str,
        description: str,
        celery_task_id: str | None = None,
        approval_status: str = "not_required",
    ) -> TaskHistory:
        await self.ensure_user(user_id)
        task = TaskHistory(
            task_id=task_id,
            user_id=user_id,
            task_description=description,
            agents_used=[],
            result_summary="",
            status="queued",
            celery_task_id=celery_task_id,
            approval_status=approval_status,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_task(self, user_id: str, task_id: str) -> TaskHistory | None:
        return await self.session.scalar(
            select(TaskHistory).where(
                TaskHistory.user_id == user_id,
                TaskHistory.task_id == task_id,
            )
        )

    async def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        agents_used: list[str] | None = None,
        result_summary: str | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        cancel_requested: bool | None = None,
        celery_task_id: str | None = None,
        approval_status: str | None = None,
        approval_decision_at: datetime | None = None,
        approval_reason: str | None = None,
    ) -> TaskHistory | None:
        task = await self.session.get(TaskHistory, task_id)
        if task is None:
            return None
        if status is not None:
            task.status = status
        if agents_used is not None:
            task.agents_used = agents_used
        if result_summary is not None:
            task.result_summary = result_summary
        if error_message is not None:
            task.error_message = error_message
        if started_at is not None:
            task.started_at = started_at
        if completed_at is not None:
            task.completed_at = completed_at
        if cancel_requested is not None:
            task.cancel_requested = cancel_requested
        if celery_task_id is not None:
            task.celery_task_id = celery_task_id
        if approval_status is not None:
            task.approval_status = approval_status
        if approval_decision_at is not None:
            task.approval_decision_at = approval_decision_at
        if approval_reason is not None:
            task.approval_reason = approval_reason
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def request_task_cancellation(self, user_id: str, task_id: str) -> TaskHistory | None:
        task = await self.get_task(user_id, task_id)
        if task is None:
            return None
        if task.status in {"queued", "running"}:
            task.cancel_requested = True
            await self.session.commit()
            await self.session.refresh(task)
        return task

    async def list_tasks(
        self, user_id: str, limit: int = 25, offset: int = 0
    ) -> list[TaskHistory]:
        return list(
            (
                await self.session.scalars(
                    select(TaskHistory)
                    .where(TaskHistory.user_id == user_id)
                    .order_by(TaskHistory.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )

    async def count_tasks(self, user_id: str) -> int:
        from sqlalchemy import func

        return int(
            await self.session.scalar(
                select(func.count()).select_from(TaskHistory).where(TaskHistory.user_id == user_id)
            )
            or 0
        )

    async def task_counts(self, user_id: str) -> dict[str, int]:
        tasks = await self.list_tasks(user_id, limit=1000)
        return {
            "total_tasks": len(tasks),
            "completed_tasks": sum(item.status == "completed" for item in tasks),
            "failed_tasks": sum(item.status in {"failed", "completed_with_errors"} for item in tasks),
            "running_tasks": sum(item.status in {"queued", "running"} for item in tasks),
        }
