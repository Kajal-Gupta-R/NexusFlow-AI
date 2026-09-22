from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import MAX_MESSAGE_LENGTH


class OrchestrateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("Message cannot be empty.")
        return message


class AgentStep(BaseModel):
    agent: str
    status: str
    error: str | None = None


class OrchestrateResponse(BaseModel):
    task_id: str
    status: str
    agents_used: list[str]
    result: str
    steps: list[AgentStep]
