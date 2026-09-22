import asyncio

import pytest
from app.agents.specialized import AgentResult, SpecializedAgent
from app.core.auth import issue_session_token
from app.main import app
from app.orchestration.supervisor import Supervisor
from fastapi.testclient import TestClient


class FakeAIService:
    async def generate_response(self, message: str, system_prompt: str = "") -> str:
        return f"handled: {message}"


client = TestClient(app)
TOKEN, _ = issue_session_token()
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_supervisor_routes_simple_tasks_to_general_path() -> None:
    assert Supervisor.select_agents("Explain what Python is") == []


def test_supervisor_routes_specialized_tasks() -> None:
    assert Supervisor.select_agents("Research AI agents") == ["research"]
    assert Supervisor.select_agents("Debug this Java function") == ["coding"]
    assert Supervisor.select_agents("Create a project plan") == ["planning"]
    assert Supervisor.select_agents("Research AI agents and create a Python program") == [
        "research",
        "coding",
    ]


@pytest.mark.asyncio
async def test_supervisor_combines_agent_results() -> None:
    supervisor = Supervisor(FakeAIService(), {
        "research": SpecializedAgent(FakeAIService().generate_response),
        "coding": SpecializedAgent(FakeAIService().generate_response),
    })
    result = await supervisor.run("Research AI agents and create a Python program")

    assert result.status == "completed"
    assert result.agents_used == ["research", "coding"]
    assert [step.status for step in result.steps] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_independent_agents_run_concurrently() -> None:
    active = 0
    maximum_active = 0

    async def respond(_: str, __: str) -> str:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return "done"

    agents = {
        "research": SpecializedAgent(respond),
        "planning": SpecializedAgent(respond),
    }
    supervisor = Supervisor(FakeAIService(), agents)
    result = await supervisor.run("Research this topic and create a project plan")

    assert result.status == "completed"
    assert maximum_active == 2


@pytest.mark.asyncio
async def test_agent_failures_are_reported_without_crashing() -> None:
    async def fail(_: str, __: str) -> str:
        raise RuntimeError("provider failed")

    supervisor = Supervisor(FakeAIService(), {"research": SpecializedAgent(fail, name="research")})
    result = await supervisor.run("Research this topic")

    assert result.status == "failed"
    assert result.steps == [
        AgentResult(
            agent="research",
            status="failed",
            error="This agent could not complete its assigned task.",
        )
    ]


def test_orchestrate_endpoint_returns_structured_result(monkeypatch) -> None:
    class FakeEndpointService:
        def __init__(self, api_key: str, model: str) -> None:
            pass

        async def generate_response(self, message: str, system_prompt: str = "") -> str:
            return f"handled: {message}"

    monkeypatch.setattr("app.main.AIService", FakeEndpointService)
    response = client.post(
        "/orchestrate",
        json={"message": "Research AI agents and create a Python program"},
        headers=HEADERS,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["agents_used"] == ["research", "coding"]
    assert [step["status"] for step in body["steps"]] == ["completed", "completed"]
    assert body["task_id"]


def test_orchestrate_rejects_empty_messages() -> None:
    assert client.post("/orchestrate", json={"message": " "}, headers=HEADERS).status_code == 422


def test_background_submission_returns_queued_task(monkeypatch) -> None:
    class FakeAsyncResult:
        id = "celery-test-id"

    class FakeTask:
        @staticmethod
        def delay(task_id: str, user_id: str, description: str) -> FakeAsyncResult:
            assert task_id
            assert user_id
            assert description == "Run this in the background"
            return FakeAsyncResult()

    monkeypatch.setattr("app.main.execute_orchestration", FakeTask())
    response = client.post(
        "/tasks/submit",
        json={"task_description": "Run this in the background"},
        headers=HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    task_id = response.json()["task_id"]
    status = client.get(f"/tasks/{task_id}", headers=HEADERS)
    assert status.status_code == 200
    assert status.json()["status"] == "queued"


def test_background_task_ownership_is_enforced() -> None:
    response = client.get(
        "/tasks/does-not-belong",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
