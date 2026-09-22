from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import MAX_MESSAGE_LENGTH


class TaskSubmitRequest(BaseModel):
    task_description: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("task_description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        description = value.strip()
        if not description:
            raise ValueError("Task description cannot be empty.")
        return description


class TaskSubmitResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    task_description: str
    agents_used: list[str]
    result_summary: str
    error_message: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancel_requested: bool
    approval_status: str
    approval_decision_at: datetime | None
    approval_reason: str | None


class TaskListResponse(BaseModel):
    items: list[TaskStatusResponse]
    page: int
    page_size: int
    total: int
