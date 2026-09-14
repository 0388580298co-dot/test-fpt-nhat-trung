import argparse
import json
from .agent import OpenPilot


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenPilot v0.1")
    parser.add_argument("goal", help="What should OpenPilot plan?")
    parser.add_argument("--workspace", default=".", help="Workspace to inspect")
    args = parser.parse_args()

    result = OpenPilot(args.workspace).run(args.goal)
    print("OpenPilot v0.1")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
