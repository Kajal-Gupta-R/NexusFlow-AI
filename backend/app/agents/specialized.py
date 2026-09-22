from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.services.ai import AIService, AIServiceError


@dataclass(frozen=True)
class AgentResult:
    agent: str
    status: str
    result: str = ""
    error: str | None = None


AgentResponder = Callable[[str, str], Awaitable[str]]


class SpecializedAgent:
    name = "agent"
    responsibility = "Complete an assigned subtask."
    system_prompt = "You are a reliable specialized assistant."

    def __init__(self, responder: AgentResponder, name: str | None = None) -> None:
        self._responder = responder
        self._name = name or self.name

    async def run(self, task: str) -> AgentResult:
        try:
            result = await self._responder(task, self.system_prompt)
            return AgentResult(agent=self._name, status="completed", result=result)
        except AIServiceError as exc:
            return AgentResult(agent=self._name, status="failed", error=str(exc))
        except (RuntimeError, ValueError):
            return AgentResult(
                agent=self._name,
                status="failed",
                error="This agent could not complete its assigned task.",
            )


class ResearchAgent(SpecializedAgent):
    name = "research"
    responsibility = "Organize research questions into accurate, structured summaries."
    system_prompt = (
        "You are the NexusFlow Research Agent. Organize the requested topic into a "
        "structured summary with key concepts and findings. You do not have web access "
        "unless explicitly provided with source material. Never invent sources or claim "
        "that web research was performed; clearly state when external information is unavailable."
    )


class CodingAgent(SpecializedAgent):
    name = "coding"
    responsibility = "Generate, explain, debug, and improve code safely."
    system_prompt = (
        "You are the NexusFlow Coding Agent. Generate or debug code and explain it "
        "in simple language. Suggest safe corrections and improvements. Never execute "
        "generated code and do not claim that code was tested unless test output is provided."
    )


class PlanningAgent(SpecializedAgent):
    name = "planning"
    responsibility = "Create actionable plans with dependencies and progress states."
    system_prompt = (
        "You are the NexusFlow Planning Agent. Break the request into actionable "
        "steps, identify dependencies, and label each step pending or completed. "
        "Return a clear, structured plan."
    )


def create_agents(ai_service: AIService) -> dict[str, SpecializedAgent]:
    async def respond(task: str, system_prompt: str) -> str:
        return await ai_service.generate_response(task, system_prompt)

    return {
        "research": ResearchAgent(respond),
        "coding": CodingAgent(respond),
        "planning": PlanningAgent(respond),
    }
