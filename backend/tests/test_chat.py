from app.core.auth import issue_session_token
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
TOKEN, _ = issue_session_token()
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_health_endpoint_remains_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nexusflow-api"}


def test_protected_endpoints_require_bearer_authentication() -> None:
    response = client.get("/memory")
    assert response.status_code == 401


def test_session_tokens_are_server_issued() -> None:
    response = client.post("/auth/session")
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_chat_rejects_blank_and_oversized_messages() -> None:
    assert client.post("/chat", json={"message": "   "}, headers=HEADERS).status_code == 422
    assert client.post("/chat", json={"message": "x" * 4001}, headers=HEADERS).status_code == 422


def test_chat_returns_service_response(monkeypatch) -> None:
    class FakeAIService:
        def __init__(self, api_key: str, model: str) -> None:
            assert model == "gpt-4o-mini"

        async def generate_response(self, message: str) -> str:
            assert message == "Hello NexusFlow"
            return "Hello from the test assistant."

    monkeypatch.setattr("app.main.AIService", FakeAIService)

    response = client.post("/chat", json={"message": " Hello NexusFlow "}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"response": "Hello from the test assistant."}


def test_chat_hides_missing_configuration(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.openai_api_key", "")
    response = client.post("/chat", json={"message": "Hello"}, headers=HEADERS)

    assert response.status_code == 503
    assert response.json() == {"detail": "AI service is not configured."}
