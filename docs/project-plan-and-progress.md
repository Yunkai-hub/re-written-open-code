# opencode-py 复刻计划与进展

> 项目目标：使用 **Python + LangGraph** 复刻开源 opencode（以 `sst/opencode` 为参考），面向可持续演进到产品级能力。
>
> 更新时间：2026-05-21

---

## 1. 目标与范围

### 1.1 总目标
- 复刻 opencode 核心能力：Agent 循环 + 工具调用 + 会话持久化 + 权限系统 +（后续）MCP +（后续）TUI。

### 1.2 当前技术选型
- 编排框架：LangGraph（StateGraph + Checkpointer）
- 模型接入：LangChain（当前已接 Anthropic）
- CLI：Typer + Rich
- 配置：pydantic-settings
- 持久化：LangGraph SqliteSaver（SQLite）
- 包管理：uv

---

## 2. 分阶段路线图

## Phase 0（已完成）— 架构分析
**目标**：读懂 `sst/opencode` 核心运行时并建立映射。

**完成产物**：
- [docs/phase-0-architecture.md](phase-0-architecture.md)
- 已克隆上游参考仓库：`reference/opencode/`

**已确认模块映射**：
- Agent loop / Tool registry / Permission / Session / Provider / MCP / Sub-agent / Bus
- 已形成 opencode → LangGraph 节点映射表

---

## Phase 1（已完成 MVP）— 最小可用运行链路
**目标**：跑通 end-to-end：对话 → 工具调用 → 权限询问 → 会话恢复。

**当前状态**：✅ MVP 已落地

### 2.1 已完成功能
1. **工程初始化（uv）**
   - 已完成项目初始化与依赖安装（langgraph、langchain-anthropic、typer、rich、pydantic 等）

2. **核心数据模型**
   - [src/opencode_py/session/models.py](../src/opencode_py/session/models.py)
   - 定义了 Message / Part（text、reasoning、tool_call、tool_result）/ AgentConfig / TokenUsage

3. **权限系统（基础版）**
   - [src/opencode_py/permission/schema.py](../src/opencode_py/permission/schema.py)
   - [src/opencode_py/permission/prompt.py](../src/opencode_py/permission/prompt.py)
   - 支持 `allow | deny | ask`，支持 once / always / reject 交互

4. **工具框架 + 内置工具（5个）**
   - 基础定义：[src/opencode_py/tools/base.py](../src/opencode_py/tools/base.py)
   - 注册表：[src/opencode_py/tools/registry.py](../src/opencode_py/tools/registry.py)
   - 内置工具：
     - [read.py](../src/opencode_py/tools/builtin/read.py)
     - [write.py](../src/opencode_py/tools/builtin/write.py)
     - [edit.py](../src/opencode_py/tools/builtin/edit.py)
     - [glob_tool.py](../src/opencode_py/tools/builtin/glob_tool.py)
     - [bash.py](../src/opencode_py/tools/builtin/bash.py)

5. **LangGraph 状态机（MVP）**
   - [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py)
   - 主链路：`prepare_input → llm_call → exec_tools → llm_call/END`

6. **Anthropic 模型接入（MVP）**
   - 通过 `langchain-anthropic` 在图内完成工具绑定调用

7. **会话持久化（MVP）**
   - 已接 `AsyncSqliteSaver`（thread_id 可 resume）

8. **CLI（MVP）**
   - [src/opencode_py/cli.py](../src/opencode_py/cli.py)
   - 命令：`chat` / `resume` / `doctor`

9. **文档**
   - [README.md](../README.md)
   - [docs/phase-1-manual-test.md](phase-1-manual-test.md)

### 2.2 已验证项
- ✅ import 与 graph compile 通过
- ✅ CLI 帮助与 doctor 可运行
- ⏳ 手工端到端剧本（①~⑤）正在你本机执行中

---

## Phase 2（进行中）— 交互体验与模型层增强
**状态**：🟨 已完成核心实现，待补充手工 E2E 验证

**已完成**：
1. 流式 token 输出（CLI 基于 `astream_events` 增量渲染）
2. 多 Provider Router（Anthropic/OpenAI 基础切换）
3. 显式路由节点（`route_event`）
4. 基础回归测试（pytest，10 个用例已通过）

**待继续完善**：
- streaming 事件展示体验打磨（tool begin/end、异常路径提示）
- 增加更细粒度 graph 行为测试

---

## Phase 3（后续）— Session 完整化
**状态**：⬜ 未开始

**计划内容**：
1. Context overflow 检测
2. Auto-compaction（历史总结压缩）
3. session list/fork 元数据管理

---

## Phase 4（后续）— TUI
**状态**：⬜ 未开始

**计划内容**：
1. Textual UI 骨架
2. 消息流、状态栏、权限弹窗
3. 流式渲染 + 中断控制

---

## Phase 5（后续）— MCP 集成
**状态**：⬜ 未开始

**计划内容**：
1. MCP server 配置加载
2. stdio/SSE transport
3. MCP tool 动态注入 registry

---

## Phase 6（后续）— 子 Agent 与扩展能力
**状态**：⬜ 未开始

**计划内容**：
1. `task` 工具（subgraph/subagent）
2. 后台任务与状态查询
3. skill/hook 扩展点

---

## 3. 当前阻塞与注意事项

1. 本机终端是 PowerShell 时，`export` 命令不可用（需改用 `$env:...` 或切到 Git Bash）
2. 端到端测试依赖 `ANTHROPIC_API_KEY`
3. `always` 权限目前按具体 pattern 生效（安全默认），不是全量放开

---

## 4. 下一次继续建议（从这里接）

建议按以下顺序继续：
1. 跑完 [docs/phase-1-manual-test.md](phase-1-manual-test.md) 剧本并补记录（尤其是 provider=openai 分支）
2. 增加 route_event / exec_tools 的行为级测试（包含 tool_call 分支覆盖）
3. 进入 Phase 3：context overflow + compaction

---

## 5. 快速命令备忘

```bash
# 环境检查
uv run opencode-py doctor

# 新会话
uv run opencode-py chat "列出 src/opencode_py 下的 py 文件"

# 恢复会话
uv run opencode-py resume thr_xxxxx "继续上一个任务"
```
