from openpilot.github_tool import parse_repo_url
from openpilot.planner import create_plan
from openpilot.providers import OpenAICompatibleProvider
from openpilot.test_runner import TestResult


def test_planner_rejects_empty_goal():
    try:
        create_plan("   ")
    except ValueError:
        return
    assert False


def test_github_repo_parser():
    assert parse_repo_url("https://github.com/octo/demo.git") == ("octo", "demo")
    assert parse_repo_url("octo/demo") == ("octo", "demo")


def test_provider_has_generate_method():
    provider = OpenAICompatibleProvider("secret", "demo", "https://example.com/v1")
    assert callable(provider.generate)


def test_test_result_passed():
    result = TestResult(["python", "-m", "pytest"], 0, "2 passed", "")
    assert result.passed
