from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)


class AIServiceError(Exception):
    """An expected, safe-to-report AI service failure."""


class AIService:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")
        self._client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=1)
        self._model = model

    async def generate_response(
        self,
        message: str,
        system_prompt: str = "You are NexusFlow AI, a helpful and concise assistant.",
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": message},
                ],
                temperature=0.7,
            )
        except RateLimitError as exc:
            raise AIServiceError("The AI service is temporarily busy. Please try again shortly.") from exc
        except APITimeoutError as exc:
            raise AIServiceError("The AI service took too long to respond. Please try again.") from exc
        except APIConnectionError as exc:
            raise AIServiceError("The AI service could not be reached. Please try again.") from exc
        except APIStatusError as exc:
            raise AIServiceError("The AI service could not process the request. Please try again.") from exc
        except APIError as exc:
            raise AIServiceError("The AI service timed out or returned an unexpected error.") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise AIServiceError("The AI service returned an empty response. Please try again.")
        return content.strip()
