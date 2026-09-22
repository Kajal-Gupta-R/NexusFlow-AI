import asyncio
import uuid
from dataclasses import dataclass

from app.agents.specialized import AgentResult, SpecializedAgent
from app.services.ai import AIService, AIServiceError

MAX_CONCURRENT_AGENTS = 3
MAX_AGENT_CALLS = 3


@dataclass(frozen=True)
class OrchestrationResult:
    task_id: str
    status: str
    agents_used: list[str]
    result: str
    steps: list[AgentResult]


class Supervisor:
    """Bounded task router and coordinator for the Phase 4 agent workflow."""

    def __init__(self, ai_service: AIService, agents: dict[str, SpecializedAgent]) -> None:
        self._ai_service = ai_service
        self._agents = agents
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)

    @staticmethod
    def select_agents(message: str) -> list[str]:
        text = message.lower()
        research = any(
            word in text for word in ("research", "investigate", "compare", "findings", "literature")
        )
        coding = any(
            word in text
            for word in ("code", "coding", "program", "script", "debug", "function")
        )
        planning = any(
            word in text for word in ("plan", "planning", "roadmap", "milestones", "steps", "strategy")
        )

        selected = []
        if research:
            selected.append("research")
        if coding:
            selected.append("coding")
        if planning:
            selected.append("planning")
        return selected[:MAX_AGENT_CALLS]

    async def run(self, message: str) -> OrchestrationResult:
        task_id = str(uuid.uuid4())
        selected = self.select_agents(message)

        if not selected:
            try:
                response = await self._ai_service.generate_response(message)
                return OrchestrationResult(
                    task_id=task_id,
                    status="completed",
                    agents_used=["general"],
                    result=response,
                    steps=[AgentResult(agent="general", status="completed", result=response)],
                )
            except AIServiceError as exc:
                return OrchestrationResult(
                    task_id=task_id,
                    status="failed",
                    agents_used=["general"],
                    result="The task could not be completed.",
                    steps=[AgentResult(agent="general", status="failed", error=str(exc))],
                )

        results: list[AgentResult] = []
        if "research" in selected and "coding" in selected:
            research_result = await self._run_agent("research", message)
            results.append(research_result)
            coding_task = f"{message}\n\nResearch agent output:\n{research_result.result}"
            results.append(await self._run_agent("coding", coding_task))
            remaining = [name for name in selected if name not in {"research", "coding"}]
        else:
            remaining = selected

        if remaining:
            results.extend(await asyncio.gather(*(self._run_agent(name, message) for name in remaining)))

        successful = [item for item in results if item.status == "completed"]
        failed = [item for item in results if item.status == "failed"]
        if not successful:
            status = "failed"
            combined = "The requested task could not be completed because all assigned agents failed."
        else:
            status = "completed_with_errors" if failed else "completed"
            combined = "\n\n".join(
                f"### {item.agent.title()} Agent\n{item.result}" for item in successful
            )
            if failed:
                combined += "\n\nSome agents failed, so this result may be incomplete."

        return OrchestrationResult(
            task_id=task_id,
            status=status,
            agents_used=selected,
            result=combined,
            steps=results,
        )

    async def _run_agent(self, name: str, task: str) -> AgentResult:
        async with self._semaphore:
            try:
                return await asyncio.wait_for(self._agents[name].run(task), timeout=45)
            except asyncio.TimeoutError:
                return AgentResult(
                    agent=name,
                    status="failed",
                    error="This agent exceeded its execution time limit.",
                )
