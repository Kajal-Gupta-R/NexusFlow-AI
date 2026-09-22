from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("Message cannot be empty.")
        return message


class ChatResponse(BaseModel):
    response: str
