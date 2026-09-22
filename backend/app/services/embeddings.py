import hashlib
import math
import re

from openai import APIError, AsyncOpenAI


class EmbeddingService:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=15.0) if api_key else None
        self._model = model

    async def embed(self, text: str) -> list[float] | None:
        if self._client is None:
            return None
        try:
            response = await self._client.embeddings.create(model=self._model, input=text)
        except APIError:
            return None
        return response.data[0].embedding if response.data else None

    @staticmethod
    def local_embedding(text: str, dimensions: int = 64) -> list[float]:
        """Create a deterministic local vector for offline fallback retrieval."""
        vector = [0.0] * dimensions
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector
