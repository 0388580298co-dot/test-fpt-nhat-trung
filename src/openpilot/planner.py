from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: list[str]


def create_plan(goal: str) -> Plan:
    goal = goal.strip()
    if not goal:
        raise ValueError("A goal is required")

    return Plan(
        goal=goal,
        steps=[
            "Inspect the workspace",
            "Identify the requested outcome",
            "Produce a safe execution plan",
            "Report findings and next steps",
        ],
    )
