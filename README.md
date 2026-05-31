# opencode-py

Python + LangGraph reimplementation of [sst/opencode](https://github.com/sst/opencode).

Status: **Phase 5 (in progress)** — Phase 3 session governance + Phase 5A/5B MCP integration (config loading, stdio/SSE transport client path, dynamic tool injection) are implemented.

## Layout

- [reference/opencode/](reference/opencode/) — upstream TypeScript source, read-only reference.
- [docs/phase-0-architecture.md](docs/phase-0-architecture.md) — module-by-module map of opencode → LangGraph.
- [docs/phase-5-implemented-technical-doc.md](docs/phase-5-implemented-technical-doc.md) — Phase 5A/5B MCP implementation notes.
- [src/opencode_py/](src/opencode_py/) — our implementation.

## Quick start

```bash
# 1. install uv if you don't have it (Windows PowerShell)
#    irm https://astral.sh/uv/install.ps1 | iex

# 2. install deps
uv sync

# 3. choose provider + set API key
# Anthropic (default)
export OPENCODE_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OR OpenAI
# export OPENCODE_PROVIDER=openai
# export OPENAI_API_KEY=sk-...

# 4. environment check
uv run opencode-py doctor

# 5. optional MCP local test setup
export OPENCODE_MCP_ENABLED=true
export OPENCODE_MCP_CONFIG_PATH=./mcp.json
uv run opencode-py mcp-tools

# 6. start a chat
uv run opencode-py chat "list the python files under src/"

# 7. resume a prior session
uv run opencode-py resume thr_abc123 "and now show me bash.py"
```

## Built-in tools

| name | permission | notes |
|---|---|---|
| `read` | allow | line-numbered file read with truncation |
| `glob` | allow | filesystem glob |
| `write` | ask | full-file write |
| `edit` | ask | exact substring replace (with `replace_all`) |
| `bash` | ask | runs via Git Bash / WSL / cmd.exe fallback on Windows |

## MCP integration (Phase 5A/5B)

- MCP servers are configured through `OPENCODE_MCP_ENABLED` and `OPENCODE_MCP_CONFIG_PATH`.
- Supported transport paths in current implementation:
  - `stdio`
  - `sse` (HTTP request path)
- Loaded MCP tools are dynamically injected into the runtime tool registry with safe names like `mcp_<server>_<tool>`.
- Permissions use `mcp` policy channel (default action: `ask`).
- You can list currently loaded MCP tools with:

```bash
uv run opencode-py mcp-tools
```

## What's missing vs. opencode (next milestones)

- TUI (Phase 4): currently plain `rich` REPL
- Full MCP production hardening (reconnect strategy, richer SSE session semantics, stronger auth/error telemetry)
- Sub-agents / `task` tool (Phase 6)
- Advanced streaming event UX polish (current streaming is terminal-first MVP)
- More accurate token accounting for compaction trigger (current estimator is lightweight)
