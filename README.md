# opencode-py

Python + LangGraph reimplementation of [sst/opencode](https://github.com/sst/opencode).

Status: **Phase 1 MVP** — end-to-end agent loop, tool calling, permission ask, SQLite session persistence.

## Layout

- [reference/opencode/](reference/opencode/) — upstream TypeScript source, read-only reference.
- [docs/phase-0-architecture.md](docs/phase-0-architecture.md) — module-by-module map of opencode → LangGraph.
- [src/opencode_py/](src/opencode_py/) — our implementation.

## Quick start

```bash
# 1. install uv if you don't have it (Windows PowerShell)
#    irm https://astral.sh/uv/install.ps1 | iex

# 2. install deps
uv sync

# 3. set API key
export ANTHROPIC_API_KEY=sk-ant-...

# 4. environment check
uv run opencode-py doctor

# 5. start a chat
uv run opencode-py chat "list the python files under src/"

# 6. resume a prior session
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

## What's missing vs. opencode (will come in later phases)

- TUI (Phase 4): currently plain `rich` REPL
- MCP integration (Phase 5)
- Sub-agents / `task` tool (Phase 6)
- Multi-provider router (Phase 2): only Anthropic for now
- Streaming token output (Phase 2): currently awaits full response per step
- Context compaction (Phase 3): not yet
