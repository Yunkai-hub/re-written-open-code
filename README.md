# opencode-py

Python + LangGraph reimplementation of [sst/opencode](https://github.com/sst/opencode).

Status: **Phase 2 (in progress)** — provider router, explicit route node, streaming CLI output, and baseline regression tests are implemented.

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

# 3. choose provider + set API key
# Anthropic (default)
export OPENCODE_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OR OpenAI
# export OPENCODE_PROVIDER=openai
# export OPENAI_API_KEY=sk-...

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
- Full MCP integration (Phase 5)
- Sub-agents / `task` tool (Phase 6)
- Context compaction (Phase 3)
- Dedicated TUI (Phase 4)
- Advanced streaming event UX polish (current streaming is terminal-first MVP)
- Context compaction (Phase 3): not yet
