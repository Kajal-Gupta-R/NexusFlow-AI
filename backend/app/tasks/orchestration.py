from datetime import datetime, timezone

from app.agents.specialized import create_agents
from app.core.config import get_settings
from app.database.repository import MemoryRepository
from app.database.session import (
    close_database,
    get_session_factory,
    initialize_database,
)
from app.orchestration.supervisor import Supervisor
from app.services.ai import AIService, AIServiceError
from app.tasks.celery_app import celery_app


class RetryableTaskError(AIServiceError):
    """An AI failure that is safe to retry a bounded number of times."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(bind=True, name="nexusflow.execute_orchestration", max_retries=2)
def execute_orchestration(self, task_id: str, user_id: str, description: str) -> dict[str, str]:
    """Execute one queued task and persist each terminal lifecycle state."""
    import asyncio

    try:
        return asyncio.run(_execute(self.request.id, task_id, user_id, description))
    except RetryableTaskError as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1))
        asyncio.run(_mark_failed(task_id, user_id, str(exc)))
        return {"task_id": task_id, "status": "failed"}


async def _mark_failed(task_id: str, user_id: str, error_message: str) -> None:
    await initialize_database()
    try:
        async with get_session_factory()() as session:
            await MemoryRepository(session).update_task(
                task_id,
                status="failed",
                error_message=error_message,
                completed_at=utc_now(),
            )
    finally:
        await close_database()


async def _execute(
    celery_task_id: str, task_id: str, user_id: str, description: str
) -> dict[str, str]:
    settings = get_settings()
    await initialize_database()
    factory = get_session_factory()
    try:
        async with factory() as session:
            repository = MemoryRepository(session)
            task = await repository.get_task(user_id, task_id)
            if task is None:
                return {"task_id": task_id, "status": "missing"}
            if task.approval_status in {"pending", "rejected"}:
                return {"task_id": task_id, "status": task.approval_status}
            if task.cancel_requested or task.status == "cancelled":
                await repository.update_task(
                    task_id, status="cancelled", completed_at=utc_now()
                )
                return {"task_id": task_id, "status": "cancelled"}
            await repository.update_task(
                task_id,
                status="running",
                started_at=utc_now(),
            )

        try:
            service = AIService(settings.openai_api_key, settings.openai_model)
            outcome = await Supervisor(service, create_agents(service)).run(description)
        except AIServiceError as exc:
            if any(
                phrase in str(exc).lower()
                for phrase in ("temporarily busy", "could not be reached", "timed out")
            ):
                raise RetryableTaskError(str(exc)) from exc
            async with factory() as session:
                await MemoryRepository(session).update_task(
                    task_id,
                    status="failed",
                    error_message=str(exc),
                    completed_at=utc_now(),
                )
            return {"task_id": task_id, "status": "failed"}

        async with factory() as session:
            repository = MemoryRepository(session)
            current = await repository.get_task(user_id, task_id)
            if current is None:
                return {"task_id": task_id, "status": "missing"}
            if current.cancel_requested or current.status == "cancelled":
                await repository.update_task(
                    task_id,
                    status="cancelled",
                    completed_at=utc_now(),
                    agents_used=outcome.agents_used,
                )
                return {"task_id": task_id, "status": "cancelled"}
            await repository.update_task(
                task_id,
                status=outcome.status,
                agents_used=outcome.agents_used,
                result_summary=outcome.result[:10000],
                completed_at=utc_now(),
            )
        return {"task_id": task_id, "status": outcome.status}
    finally:
        await close_database()
