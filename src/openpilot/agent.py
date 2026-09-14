from dataclasses import asdict
from .planner import create_plan
from .tools import list_files


class OpenPilot:
    def __init__(self, workspace: str = ".") -> None:
        self.workspace = workspace

    def run(self, goal: str) -> dict:
        plan = create_plan(goal)
        files = list_files(self.workspace)
        return {
            "status": "planned",
            "plan": asdict(plan),
            "workspace_file_count": len(files),
            "sample_files": files[:20],
            "safety": "No shell commands or file modifications were executed.",
        }
