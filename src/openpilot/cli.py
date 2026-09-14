import argparse
import json
from .agent import as_json, run
from .github_tool import inspect_repository
from .providers import provider_from_env
from .test_runner import run_pytest


def main():
    parser = argparse.ArgumentParser(description="OpenPilot v0.2 - safe local-first coding agent")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a safe plan for a task")
    plan.add_argument("task")
    plan.add_argument("--workspace", default=".")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--ai", action="store_true", help="Use the configured optional LLM provider")

    gh = sub.add_parser("github", help="Inspect a public GitHub repository (read-only)")
    gh.add_argument("repo", help="owner/repo or GitHub URL")

    test = sub.add_parser("test", help="Run the safe pytest runner")
    test.add_argument("--workspace", default=".")

    args = parser.parse_args()

    if args.command == "plan":
        provider = provider_from_env() if args.ai else None
        report = run(args.task, args.workspace, provider)
        if args.json:
            print(json.dumps(as_json(report), indent=2, ensure_ascii=False))
            return
        print("OpenPilot v0.2\n")
        for i, step in enumerate(report.plan, 1):
            print(f"{i}. {step}")
        print(f"\nProvider: {report.provider}")
        print("\nWorkspace:")
        for item in report.workspace_items[:20]:
            print(f"- {item}")
        if report.ai_summary:
            print("\nAI assessment:\n" + report.ai_summary)

    elif args.command == "github":
        print(json.dumps(inspect_repository(args.repo), indent=2, ensure_ascii=False))

    elif args.command == "test":
        result = run_pytest(args.workspace)
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")
        print(f"\nExit code: {result.returncode}")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
