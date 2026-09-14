from dataclasses import asdict, dataclass
from .planner import create_plan
from .providers import LLMProvider
from .tools import list_files


@dataclass
class AgentReport:
    task: str
    plan: list[str]
    workspace_items: list[str]
    provider: str = "built-in"
    ai_summary: str | None = None


def run(task: str, workspace: str = ".", provider: LLMProvider | None = None) -> AgentReport:
    plan = create_plan(task)
    items = list_files(workspace)
    summary = None
    provider_name = "built-in"
    if provider is not None:
        provider_name = provider.name
        summary = provider.generate(
            f"Task: {task}\nWorkspace items: {items[:50]}\nPlan: {plan.steps}",
            system="Return a concise, safe engineering assessment. Do not claim to have executed tools you did not execute.",
        )
    return AgentReport(task=plan.goal, plan=plan.steps, workspace_items=items, provider=provider_name, ai_summary=summary)


def as_json(report: AgentReport) -> dict:
    return asdict(report)
