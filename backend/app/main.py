import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.specialized import create_agents
from app.core.auth import authenticated_user, issue_session_token
from app.core.config import get_settings
from app.database.models import Memory
from app.database.repository import MemoryRepository
from app.database.session import get_db
from app.orchestration.supervisor import Supervisor
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.memory import (
    ConversationResponse,
    ConversationSummary,
    DashboardSummary,
    MemoryCreateRequest,
    MemoryResponse,
    MessageResponse,
    TaskHistoryResponse,
)
from app.schemas.orchestration import AgentStep, OrchestrateRequest, OrchestrateResponse
from app.schemas.tasks import (
    TaskListResponse,
    TaskStatusResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from app.services.ai import AIService, AIServiceError
from app.services.embeddings import EmbeddingService
from app.services.memory import retrieve_context
from app.tasks.orchestration import execute_orchestration

settings = get_settings()
logger = logging.getLogger("nexusflow.api")

SessionDependency = Annotated[AsyncSession, Depends(get_db)]

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not settings.is_development and settings.auth_secret == "change-this-auth-secret-in-production":
        raise RuntimeError("AUTH_SECRET must be changed before production startup.")
    try:
        yield
    finally:
        from app.database.session import close_database

        await close_database()


app = FastAPI(
    title="NexusFlow AI API",
    version="0.1.0",
    description="Backend API for the NexusFlow AI orchestration platform.",
    lifespan=lifespan,
)

# Allow the local Vite development server to call the API from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Memory-Used"],
)


@app.middleware("http")
async def request_safety_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > 100_000
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
        if too_large:
            return JSONResponse(status_code=413, content={"detail": "Request payload is too large."})
    result = await call_next(request)
    logger.info("request method=%s path=%s status=%s", request.method, request.url.path, result.status_code)
    return result


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, __: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Persistent storage is unavailable."})


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return a simple response used to verify that the API is running."""
    return {"status": "ok", "service": "nexusflow-api"}


@app.get("/ready")
async def readiness_check() -> dict[str, str]:
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
    except (OSError, TimeoutError, ConnectionError, RedisError):
        raise HTTPException(status_code=503, detail="Required services are not ready.") from None
    return {"status": "ready", "service": "nexusflow-api"}


UserDependency = Annotated[str, Depends(authenticated_user)]


@app.post("/auth/session")
async def create_session() -> dict[str, str | int]:
    token, user_id = issue_session_token()
    return {"access_token": token, "token_type": "bearer", "user_id": user_id}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: UserDependency,
    session: SessionDependency,
    response: Response,
) -> ChatResponse:
    """Generate one response without exposing provider details to the client."""
    try:
        service = AIService(settings.openai_api_key, settings.openai_model)
        context = ""
        try:
            context = await retrieve_context(session, user_id, request.message)
        except SQLAlchemyError:
            pass
        response.headers["X-Memory-Used"] = "true" if context else "false"
        prompt = f"{context}\n\nUser request:\n{request.message}" if context else request.message
        response = await service.generate_response(
            prompt,
            "You are NexusFlow AI, a helpful and concise assistant. Use relevant memory context carefully.",
        ) if context else await service.generate_response(request.message)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="AI service is not configured.") from exc
    except AIServiceError:
        raise HTTPException(status_code=502, detail="The AI service is temporarily unavailable.") from None
    try:
        await MemoryRepository(session).save_conversation(
            user_id, request.message[:200], request.message, response
        )
    except SQLAlchemyError:
        await session.rollback()
    return ChatResponse(response=response)


@app.post("/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(
    request: OrchestrateRequest,
    user_id: UserDependency,
    session: SessionDependency,
    response: Response,
) -> OrchestrateResponse:
    """Route a task through the smallest suitable set of bounded agents."""
    try:
        ai_service = AIService(settings.openai_api_key, settings.openai_model)
        context = ""
        try:
            context = await retrieve_context(session, user_id, request.message)
        except SQLAlchemyError:
            pass
        response.headers["X-Memory-Used"] = "true" if context else "false"
        task_message = f"{context}\n\nUser task:\n{request.message}" if context else request.message
        workflow = Supervisor(ai_service, create_agents(ai_service))
        outcome = await workflow.run(task_message)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="AI service is not configured.") from exc
    except AIServiceError:
        raise HTTPException(status_code=502, detail="The AI service is temporarily unavailable.") from None

    try:
        await MemoryRepository(session).save_task(
            user_id,
            outcome.task_id,
            request.message,
            outcome.agents_used,
            outcome.result[:10000],
            outcome.status,
        )
    except SQLAlchemyError:
        await session.rollback()

    return OrchestrateResponse(
        task_id=outcome.task_id,
        status=outcome.status,
        agents_used=outcome.agents_used,
        result=outcome.result,
        steps=[
            AgentStep(agent=step.agent, status=step.status, error=step.error)
            for step in outcome.steps
        ],
    )


def memory_response(memory: Memory) -> MemoryResponse:
    return MemoryResponse(
        memory_id=memory.memory_id,
        memory_text=memory.memory_text,
        memory_type=memory.memory_type,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@app.get("/memory", response_model=list[MemoryResponse])
async def list_memory(
    user_id: UserDependency,
    session: SessionDependency,
) -> list[MemoryResponse]:
    return [memory_response(item) for item in await MemoryRepository(session).list_memories(user_id)]


@app.post("/memory", response_model=MemoryResponse, status_code=201)
async def create_memory(
    request: MemoryCreateRequest,
    user_id: UserDependency,
    session: SessionDependency,
) -> MemoryResponse:
    try:
        embedding = await EmbeddingService(
            settings.openai_api_key, settings.openai_embedding_model
        ).embed(request.memory_text)
        memory = await MemoryRepository(session).create_memory(
            user_id, request.memory_text, request.memory_type, embedding
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Memory storage is unavailable.") from exc
    return memory_response(memory)


@app.delete("/memory/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> None:
    await MemoryRepository(session).delete_memory(user_id, memory_id)


@app.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    user_id: UserDependency,
    session: SessionDependency,
) -> list[ConversationSummary]:
    conversations = await MemoryRepository(session).list_conversations(user_id)
    return [
        ConversationSummary(
            conversation_id=item.conversation_id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in conversations
    ]


@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> ConversationResponse:
    conversation = await MemoryRepository(session).get_conversation(user_id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationResponse(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageResponse(
                message_id=message.message_id,
                role=message.role,
                content=message.content,
                timestamp=message.timestamp,
            )
            for message in conversation.messages
        ],
    )


@app.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> None:
    await MemoryRepository(session).delete_conversation(user_id, conversation_id)


@app.get("/tasks/history", response_model=list[TaskHistoryResponse])
async def task_history(
    user_id: UserDependency,
    session: SessionDependency,
) -> list[TaskHistoryResponse]:
    tasks = await MemoryRepository(session).list_tasks(user_id)
    return [
        TaskHistoryResponse(
            task_id=item.task_id,
            task_description=item.task_description,
            agents_used=item.agents_used,
            result_summary=item.result_summary,
            status=item.status,
            created_at=item.created_at,
        )
        for item in tasks
    ]


def task_status_response(task) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        task_description=task.task_description,
        agents_used=task.agents_used or [],
        result_summary=task.result_summary,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        cancel_requested=task.cancel_requested,
            approval_status=task.approval_status,
            approval_decision_at=task.approval_decision_at,
            approval_reason=task.approval_reason,
    )


@app.post("/tasks/submit", response_model=TaskSubmitResponse, status_code=202)
async def submit_background_task(
    request: TaskSubmitRequest,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskSubmitResponse:
    task_id = str(uuid.uuid4())
    repository = MemoryRepository(session)
    approval_required = any(
        term in request.task_description.lower()
        for term in ("deploy", "delete", "execute code", "write file", "send email")
    )
    approval_status = "pending" if approval_required else "not_required"
    try:
        task = await repository.create_queued_task(
            user_id, task_id, request.task_description, approval_status=approval_status
        )
        if not approval_required:
            async_result = execute_orchestration.delay(task_id, user_id, request.task_description)
            await repository.update_task(task_id, celery_task_id=async_result.id)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Task storage is unavailable.") from exc
    except Exception as exc:
        await repository.update_task(
            task_id,
            status="failed",
            error_message="The background worker could not be reached.",
        )
        raise HTTPException(status_code=503, detail="Background processing is unavailable.") from exc
    return TaskSubmitResponse(task_id=task.task_id, status=task.status)


@app.post("/tasks/{task_id}/approve", response_model=TaskStatusResponse)
async def approve_background_task(
    task_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskStatusResponse:
    repository = MemoryRepository(session)
    task = await repository.get_task(user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Task is not awaiting approval.")
    task = await repository.update_task(
        task_id,
        status="queued",
        approval_status="approved",
        approval_decision_at=datetime.now(timezone.utc),
    )
    try:
        async_result = execute_orchestration.delay(task_id, user_id, task.task_description)
        task = await repository.update_task(task_id, celery_task_id=async_result.id)
    except (OperationalError, OSError, TimeoutError, ConnectionError):
        await repository.update_task(
            task_id, status="failed", error_message="Background processing is unavailable."
        )
        raise HTTPException(status_code=503, detail="Background processing is unavailable.") from None
    return task_status_response(task)


@app.post("/tasks/{task_id}/reject", response_model=TaskStatusResponse)
async def reject_background_task(
    task_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskStatusResponse:
    repository = MemoryRepository(session)
    task = await repository.get_task(user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Task is not awaiting approval.")
    task = await repository.update_task(
        task_id,
        status="cancelled",
        approval_status="rejected",
        approval_decision_at=datetime.now(timezone.utc),
        approval_reason="Rejected by the task owner.",
        completed_at=datetime.now(timezone.utc),
    )
    return task_status_response(task)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_background_task(
    task_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskStatusResponse:
    task = await MemoryRepository(session).get_task(user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task_status_response(task)


@app.get("/tasks", response_model=TaskListResponse)
async def list_background_tasks(
    user_id: UserDependency,
    session: SessionDependency,
    page: int = 1,
    page_size: int = 25,
) -> TaskListResponse:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination values.")
    repository = MemoryRepository(session)
    items = await repository.list_tasks(user_id, limit=page_size, offset=(page - 1) * page_size)
    return TaskListResponse(
        items=[task_status_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=await repository.count_tasks(user_id),
    )


@app.post("/tasks/{task_id}/cancel", response_model=TaskStatusResponse)
async def cancel_background_task(
    task_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskStatusResponse:
    task = await MemoryRepository(session).request_task_cancellation(user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status not in {"queued", "running"}:
        return task_status_response(task)
    task = await MemoryRepository(session).update_task(
        task_id, status="cancelled" if task.status == "queued" else None, completed_at=task.completed_at
    )
    return task_status_response(task)


@app.post("/tasks/{task_id}/retry", response_model=TaskSubmitResponse, status_code=202)
async def retry_background_task(
    task_id: str,
    user_id: UserDependency,
    session: SessionDependency,
) -> TaskSubmitResponse:
    repository = MemoryRepository(session)
    task = await repository.get_task(user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status not in {"failed", "completed_with_errors"}:
        raise HTTPException(status_code=409, detail="Only failed tasks can be retried.")
    new_task_id = str(uuid.uuid4())
    created = await repository.create_queued_task(user_id, new_task_id, task.task_description)
    try:
        async_result = execute_orchestration.delay(new_task_id, user_id, task.task_description)
        await repository.update_task(new_task_id, celery_task_id=async_result.id)
    except Exception as exc:
        await repository.update_task(
            new_task_id, status="failed", error_message="The background worker could not be reached."
        )
        raise HTTPException(status_code=503, detail="Background processing is unavailable.") from exc
    return TaskSubmitResponse(task_id=created.task_id, status=created.status)


@app.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    user_id: UserDependency,
    session: SessionDependency,
) -> DashboardSummary:
    repository = MemoryRepository(session)
    tasks = await repository.list_tasks(user_id, limit=8)
    conversations = await repository.list_conversations(user_id, limit=8)
    counts = await repository.task_counts(user_id)
    return DashboardSummary(
        **counts,
        recent_tasks=[
            TaskHistoryResponse(
                task_id=item.task_id,
                task_description=item.task_description,
                agents_used=item.agents_used,
                result_summary=item.result_summary,
                status=item.status,
                created_at=item.created_at,
            )
            for item in tasks
        ],
        recent_conversations=[
            ConversationSummary(
                conversation_id=item.conversation_id,
                title=item.title,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in conversations
        ],
        available_agents=["research", "coding", "planning", "general"],
    )
