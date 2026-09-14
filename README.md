# OpenPilot

> **Your open-source, local-first AI coding agent.**

OpenPilot turns a software task into a safe workflow: **plan → inspect → assist → test → report**.

## 🚀 v0.2

This release adds:

- 🤖 Optional OpenAI-compatible LLM provider
- 🐙 Read-only public GitHub repository inspector
- 🧪 Safe pytest runner (no shell)
- 🧩 Provider abstraction for future local/cloud models
- 📦 JSON output for automation
- 🔐 No automatic shell execution
- 🏠 Works without an API key using the built-in planner

## Quick start

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

Create a plan:

```bash
openpilot plan "Analyze this repository and suggest improvements"
```

Inspect a public GitHub repository:

```bash
openpilot github owner/repo
```

Run tests:

```bash
openpilot test
```

## Optional AI provider

Set an API key and model through environment variables:

```text
OPENPILOT_API_KEY=your-key
OPENPILOT_MODEL=your-model
OPENPILOT_BASE_URL=https://api.openai.com/v1
```

Then:

```bash
openpilot plan "Review the architecture" --ai
```

The provider uses a standard OpenAI-compatible chat-completions interface, so the adapter can also target compatible gateways or local servers by changing `OPENPILOT_BASE_URL`.

## Architecture

```text
src/openpilot/
├── agent.py          # orchestration and report model
├── planner.py        # deterministic task planning
├── tools.py          # safe workspace inspection
├── providers.py      # optional LLM provider adapters
├── github_tool.py    # read-only GitHub inspection
├── test_runner.py    # safe pytest runner
└── cli.py            # command-line interface
```

## Safety model

OpenPilot v0.2 does **not** execute arbitrary shell commands. The built-in test command invokes `python -m pytest -q` without a shell, and the GitHub tool is read-only. Future execution tools should be sandboxed and permission-gated.

## Roadmap

- [x] v0.1 safe agent skeleton
- [x] v0.2 provider adapter
- [x] v0.2 GitHub inspector
- [x] v0.2 test runner
- [ ] GitHub issues / pull request analysis
- [ ] Docker sandbox
- [ ] MCP integration
- [ ] Local model presets
- [ ] Desktop application
- [ ] Multi-agent workflows

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) before reporting vulnerabilities.

## License

MIT License.
