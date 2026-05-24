# Phase 2 Implementation Plan

## Context
Phase 1 已完成 MVP（LangGraph 基础循环、Anthropic、5 个工具、权限询问、SQLite resume），但还缺少更接近 opencode 的关键能力：流式输出、多 Provider 抽象、显式事件路由节点、基础回归测试。当前代码集中在 `src/opencode_py/agent/graph.py` 与 `src/opencode_py/cli.py`，且 `llm_call`/`exec_tools` 为紧耦合实现。Phase 2 的目标是在不破坏现有可用性的前提下，先建立稳定扩展点，再增强交互体验。

## Recommended approach

### 1) Introduce provider router abstraction (keep Anthropic default)
**Why first:** 为后续 streaming 和更复杂路由提供稳定模型层接口，降低 `graph.py` 改动耦合。

**Files to modify**
- `src/opencode_py/config.py`
- `src/opencode_py/agent/graph.py`
- `src/opencode_py/providers/router.py` (new)
- `src/opencode_py/providers/__init__.py` (new)

**Implementation details**
- 在 `Settings` 增加 `provider`（默认 `anthropic`）与 `openai_api_key` 字段。
- 新增 `providers/router.py`，暴露 `build_chat_model(agent, settings)`：
  - `provider=anthropic` -> 返回 `ChatAnthropic`
  - `provider=openai` -> 返回 `ChatOpenAI`（若 key 缺失则报清晰错误）
- `graph.py` 中 `_build_llm` 改为调用 router；工具绑定保持现有接口。

---

### 2) Refactor graph with explicit route node
**Why second:** 先把流程语义化（`route_event`）再做 streaming，避免后续重复改图。

**Files to modify**
- `src/opencode_py/agent/graph.py`
- `src/opencode_py/agent/state.py`

**Implementation details**
- 将当前 `route_after_llm` 升级为显式节点：`route_event`。
- 图结构改为：
  - `START -> prepare_input -> llm_call -> route_event`
  - `route_event` 条件分支：`exec_tools` 或 `end`
  - `exec_tools -> decide_next -> llm_call/end`
- 在 state 中保留最小控制字段（例如 `step_count` 与必要路由标记），避免提前引入复杂 event bus。

---

### 3) Add streaming output in CLI (token-level where available)
**Why third:** 这是用户体验增强项，依赖前两步稳定接口。

**Files to modify**
- `src/opencode_py/cli.py`
- `src/opencode_py/agent/graph.py`（仅做最小兼容改动）

**Implementation details**
- `cli.py::_run_chat` 从 `graph.ainvoke` 改为 `graph.astream_events`（或 `graph.astream`，优先 events）。
- 在 CLI 侧处理事件：
  - 模型 token 增量 -> 立即打印
  - tool start/end -> 输出简短状态行
  - 最终 assistant message -> 保留完整内容
- 保持当前 permission prompt 机制可用（`CLIPrompter.ask`），不在 Phase 2 强行改 interrupt/resume。

---

### 4) Add baseline regression tests
**Why fourth but required in same phase:** 防回归，确保后续 Phase 3/4 重构安全。

**Files to add**
- `tests/test_permission_schema.py`
- `tests/test_tools_registry.py`
- `tests/test_graph_routing.py`
- `tests/test_provider_router.py`

**Reuse existing code**
- `permission/schema.py::evaluate`
- `tools/registry.py::all_tools/get`
- `agent/graph.py::build_graph`
- `providers/router.py::build_chat_model`

**Test focus**
- 权限：allow/deny/ask 与 rule 覆盖顺序。
- registry：工具存在性与 schema 基本结构。
- graph：有/无 tool_call 时路由分支正确；max_steps 生效。
- provider router：provider 选择与缺失 key 报错。

---

### 5) Update docs to match implemented Phase 2 state
**Files to modify**
- `docs/project-plan-and-progress.md`
- `docs/phase-1-implemented-technical-doc.md`（补充“已演进到 Phase 2”段）
- `README.md`

**Implementation details**
- 更新命令示例（流式输出行为说明、provider 配置说明）。
- 明确 Phase 2 新增能力与仍未完成项。

## Execution order
1. Provider router
2. Graph route node refactor
3. CLI streaming
4. Tests
5. Docs update

## Verification

### Automated
- `uv run pytest`
- `uv run pytest tests/test_permission_schema.py tests/test_graph_routing.py -q`

### Manual E2E
- `uv run opencode-py doctor`
- Anthropic 流程：`uv run opencode-py chat "列出 src/opencode_py 下的 py 文件"`
- Tool + permission：触发 `write`，验证 once/always/reject
- Resume：记录 `thread_id` 后 `uv run opencode-py resume <thread_id> "继续"`
- Provider 切换（若配置 OpenAI key）：设置 provider=openai 后运行一次 chat 验证连通

### Success criteria
- CLI 能看到增量输出（而不是仅最终整段）
- `provider` 可切换，anthropic 路径不回归
- 有工具调用时仍能稳定循环并正确停在 `max_steps`
- pytest 基础用例通过
