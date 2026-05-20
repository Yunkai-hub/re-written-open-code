# Phase 1 已实现技术文档（opencode-py）

> 本文档只描述**当前已经落地**的实现，不包含未来规划。
>
> 对齐目标：Python + LangGraph 复刻 opencode 的最小可用链路（MVP）。

---

## 1. 实现范围总览

Phase 1 已实现能力：

1. 基于 LangGraph 的基础 Agent 循环（含工具调用回路）
2. Anthropic 模型接入（`langchain-anthropic`）
3. 工具系统（定义、注册、执行）
4. 权限系统（allow / deny / ask；once / always / reject）
5. SQLite 会话持久化与 resume
6. CLI 交互入口（chat / resume / doctor）

核心未实现（不在本文范围）：MCP、sub-agent task、TUI、上下文压缩、多 Provider router。

---

## 2. 代码结构与模块职责

### 2.1 应用入口
- [src/opencode_py/__init__.py](../src/opencode_py/__init__.py)
- [src/opencode_py/cli.py](../src/opencode_py/cli.py)

职责：
- 提供命令行入口
- 初始化 LangGraph + SqliteSaver
- 处理用户输入循环、session thread_id、输出渲染

### 2.2 配置层
- [src/opencode_py/config.py](../src/opencode_py/config.py)

职责：
- 读取环境变量（`ANTHROPIC_API_KEY`）
- 管理默认模型、max_steps、数据目录
- 提供 session SQLite 路径（`~/.opencode-py/sessions.sqlite`）

### 2.3 Agent 图与状态
- [src/opencode_py/agent/state.py](../src/opencode_py/agent/state.py)
- [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py)

职责：
- 定义 `AgentState`（messages、cwd、agent、approved_ruleset、step_count 等）
- 构建并编译 StateGraph
- 完成 LLM 调用、工具执行与循环终止逻辑

### 2.4 会话数据模型
- [src/opencode_py/session/models.py](../src/opencode_py/session/models.py)

职责：
- 定义 `Message` 与 `Part` 体系（text、reasoning、tool_call、tool_result）
- 定义 `AgentConfig` 与 `TokenUsage`

### 2.5 权限系统
- [src/opencode_py/permission/schema.py](../src/opencode_py/permission/schema.py)
- [src/opencode_py/permission/prompt.py](../src/opencode_py/permission/prompt.py)

职责：
- 规则模型 `Rule / Ruleset`
- 权限评估函数 `evaluate(permission, pattern, *rulesets)`
- CLI 交互询问器（once / always / reject）

### 2.6 工具系统
- [src/opencode_py/tools/base.py](../src/opencode_py/tools/base.py)
- [src/opencode_py/tools/registry.py](../src/opencode_py/tools/registry.py)
- [src/opencode_py/tools/builtin/read.py](../src/opencode_py/tools/builtin/read.py)
- [src/opencode_py/tools/builtin/write.py](../src/opencode_py/tools/builtin/write.py)
- [src/opencode_py/tools/builtin/edit.py](../src/opencode_py/tools/builtin/edit.py)
- [src/opencode_py/tools/builtin/glob_tool.py](../src/opencode_py/tools/builtin/glob_tool.py)
- [src/opencode_py/tools/builtin/bash.py](../src/opencode_py/tools/builtin/bash.py)

职责：
- 抽象工具定义（参数模型、权限、执行函数）
- 提供工具注册与按名查找
- 实现 5 个内置工具

---

## 3. Agent 运行时数据流（当前实现）

当前主循环在 [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py) 内实现。

### 3.1 节点与流程

```text
START
  → prepare_input
  → llm_call
  → (if AIMessage has tool_calls) exec_tools
  → decide_next (max_steps)
  → llm_call / END
```

### 3.2 节点职责

1. `prepare_input`
   - 注入 system prompt（如首条不是 system）
   - 初始化 `step_count`

2. `llm_call`
   - 构建 Anthropic chat model
   - 绑定工具 schema
   - 基于当前消息调用 LLM
   - 写回 `AIMessage` 到 state

3. `exec_tools`
   - 解析 `AIMessage.tool_calls`
   - 对每个工具调用执行：权限评估 → 参数校验 → 执行 → 产出 `ToolMessage`
   - 若用户选 `always`，将对应 allow 规则追加进 `approved_ruleset`

4. `decide_next`
   - 使用 `max_steps` 控制循环上限

---

## 4. 权限系统实现细节

权限规则位于 [src/opencode_py/permission/schema.py](../src/opencode_py/permission/schema.py)。

### 4.1 规则模型
- `Action`: `allow | deny | ask`
- `Rule`: `(permission, pattern, action)`
- `Ruleset`: `list[Rule]`

### 4.2 评估策略
- `evaluate()` 使用“后匹配覆盖前匹配”的扫描策略
- 默认未命中时是 `ask`
- 默认规则（`DEFAULT_RULESET`）：
  - `read`, `glob` 默认 allow
  - `write`, `edit`, `bash` 默认 ask

### 4.3 用户交互
`CLIPrompter.ask()` 给出三选项：
- `once`：本次放行
- `always`：写入本 session 的 allow 规则
- `reject`：拒绝并返回工具拒绝结果

---

## 5. 工具系统实现细节

### 5.1 抽象接口
定义在 [src/opencode_py/tools/base.py](../src/opencode_py/tools/base.py)：

- `ToolDef`
  - `name`
  - `description`
  - `params_model`（Pydantic）
  - `permission`
  - `pattern_from_args`
  - `execute(params, context)`

- `ToolContext`
  - `cwd`
  - `session_id`

- `ToolResult`
  - `ok`
  - `output`
  - `metadata`

### 5.2 已实现内置工具

1. `read`
   - 文件读取，带行号输出
   - 支持 offset / limit
   - 大文件有截断上限

2. `write`
   - 全量写入文件（存在则覆盖）
   - 自动创建父目录

3. `edit`
   - 基于 `old_string -> new_string` 精确替换
   - 多命中需 `replace_all=True`

4. `glob`
   - 按 glob pattern 搜索路径
   - 返回命中列表并设置上限

5. `bash`
   - 异步子进程执行命令
   - Windows 下优先 Git Bash，其次 WSL，再回退 cmd.exe
   - 支持超时与输出截断

---

## 6. 模型接入实现细节

模型接入在 [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py) 的 `_build_llm()`。

当前实现：
- Provider：Anthropic
- 类：`ChatAnthropic`
- 工具绑定：`llm.bind_tools(tools)`
- 模型配置来源：`AgentConfig` + `Settings`

已完成：
- LLM 可依据工具 schema 触发 tool calls
- 工具结果通过 `ToolMessage` 回注下一轮推理

---

## 7. 会话持久化与 Resume

实现位置：
- [src/opencode_py/cli.py](../src/opencode_py/cli.py)
- [src/opencode_py/config.py](../src/opencode_py/config.py)

当前机制：
- 使用 `AsyncSqliteSaver.from_conn_string(db_path)` 构建 checkpointer
- Graph 调用时通过 `configurable.thread_id` 标识会话线程
- `resume <thread_id>` 会沿用同一 thread 恢复历史

说明：
- 当前持久化依赖 LangGraph checkpointer 数据结构
- 还未提供“列出会话”命令，thread_id 需从终端输出保存

---

## 8. CLI 能力与行为

CLI 位于 [src/opencode_py/cli.py](../src/opencode_py/cli.py)。

已实现命令：
1. `chat [message]`
   - 创建新 session（新 thread_id）
   - 进入交互循环

2. `resume <thread_id> [message]`
   - 使用既有 thread 继续对话

3. `doctor`
   - 打印模型配置、数据目录、DB 路径、key 是否存在

交互退出：
- 输入 `/exit` 或 `/quit`

---

## 9. 已完成验证

已完成 smoke 验证：
1. 依赖安装与导入成功
2. Graph 编译成功
3. CLI `--help` / `doctor` 正常

手工 E2E 验证文档：
- [docs/phase-1-manual-test.md](phase-1-manual-test.md)

---

## 10. 当前已知限制（真实状态）

1. 未实现流式 token 增量输出（当前按 step 返回）
2. 未实现 MCP 工具接入
3. 未实现 sub-agent / task tool
4. 未实现 context overflow 检测与 compaction
5. 未实现多 Provider router（目前 Anthropic-only）
6. 未实现 TUI（当前为 CLI + Rich）

---

## 11. 维护建议

后续每次迭代建议同步更新本文档三块内容：
1. 第 1 节“实现范围总览”
2. 第 9 节“已完成验证”
3. 第 10 节“已知限制”

这样可以保证该文档持续可用，方便随时接续开发。
