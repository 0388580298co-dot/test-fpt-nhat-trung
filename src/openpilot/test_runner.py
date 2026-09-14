"""Safe test runner for Python projects."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class TestResult:
    __test__ = False
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_pytest(workspace: str = ".", timeout: int = 120) -> TestResult:
    """Run pytest without invoking a shell."""
    process = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    return TestResult(["python", "-m", "pytest", "-q"], process.returncode, process.stdout, process.stderr)
