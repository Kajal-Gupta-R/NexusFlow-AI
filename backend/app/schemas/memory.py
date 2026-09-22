from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import MAX_MESSAGE_LENGTH


class MemoryCreateRequest(BaseModel):
    memory_text: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    memory_type: str = Field(default="fact", min_length=1, max_length=64)

    @field_validator("memory_text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Memory text cannot be empty.")
        return value.strip()


class MemoryResponse(BaseModel):
    memory_id: str
    memory_text: str
    memory_type: str
    created_at: datetime | None
    updated_at: datetime | None


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime | None
    updated_at: datetime | None


class MessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    timestamp: datetime | None


class ConversationResponse(ConversationSummary):
    messages: list[MessageResponse]


class TaskHistoryResponse(BaseModel):
    task_id: str
    task_description: str
    agents_used: list[str]
    result_summary: str
    status: str
    created_at: datetime | None


class DashboardSummary(BaseModel):
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    running_tasks: int
    recent_tasks: list[TaskHistoryResponse]
    recent_conversations: list[ConversationSummary]
    available_agents: list[str]
