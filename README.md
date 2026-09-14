# OpenPilot

> An open-source local-first AI coding agent starter.

OpenPilot turns a task into a small execution loop: **plan -> act -> inspect -> report**. This v0.1 is a safe, lightweight foundation that runs locally and does not execute shell commands unless a future tool is explicitly added.

## Features

- Task planning
- File inspection tools
- Workspace-aware agent loop
- JSON execution report
- CLI interface
- Tests with pytest
- GitHub Actions CI
- Extensible architecture for AI providers and tools

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
openpilot "Create a plan for improving this repository"
```

## Example

```text
$ openpilot "Analyze this project"
OpenPilot v0.1

1. Inspect the workspace
2. Identify the requested outcome
3. Produce a safe execution plan
4. Report findings and next steps
```

## Architecture

```text
src/openpilot/
├── agent.py       # orchestration
├── planner.py     # task planning
├── tools.py       # safe workspace tools
└── cli.py         # command-line interface
```

## Roadmap

- [x] v0.1: safe agent skeleton
- [ ] AI provider adapters
- [ ] GitHub repository tool
- [ ] Test runner tool
- [ ] Docker sandbox
- [ ] MCP integration
- [ ] Desktop application

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Please read [SECURITY.md](SECURITY.md) before reporting vulnerabilities.

## License

MIT License.
