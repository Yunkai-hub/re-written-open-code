# Phase 0 — opencode 架构分析与 LangGraph 映射

> 目标：在动手写 Python 实现之前，把 sst/opencode 的核心运行时拆解清楚，并给出 LangGraph 化的节点 / 状态映射，作为 Phase 1+ 的施工蓝图。
>
> 分析范围（in-scope）：Agent loop、Tool registry、Permission、Session/持久化、Provider、MCP、Sub-agent、Bus。
>
> 不在本阶段范围（out-of-scope）：TUI 渲染、CLI 命令解析、LSP、Git/Snapshot、Share、IDE 集成、format/audio/image。

参考代码：[`reference/opencode/packages/opencode/src/`](../reference/opencode/packages/opencode/src/)

---

## 1. 仓库结构速览

`sst/opencode` 是 monorepo，使用 bun + turborepo：

- `packages/opencode/` — **核心运行时**（TypeScript / Bun）。本阶段几乎所有分析都在这里。
- `packages/tui/` — Go 写的终端 UI（Bubble Tea），通过 HTTP/SSE 与核心通信。
- `packages/sdk/`、`packages/plugin/` — 对外 SDK 与插件机制。
- `packages/web/`、`packages/desktop/` — 网页 / 桌面分发。
- `sdks/` — 多语言 SDK 自动生成。

核心运行时 `packages/opencode/src/` 关键子目录：

| 目录 | 作用 |
|---|---|
| `agent/` | Agent 定义、subagent 权限派生 |
| `session/` | 会话状态机、LLM 调用、消息模型、压缩、溢出检测 |
| `tool/` | 内置工具实现与注册表 |
| `permission/` | 权限规则、评估、用户询问流程 |
| `provider/` | 多 LLM 提供商抽象、消息变换 |
| `mcp/` | MCP server 客户端、OAuth |
| `bus/` | 事件总线（Effect PubSub） |
| `storage/`、`session/session.sql.ts` | SQLite 持久层 |
| `plugin/` | 插件加载 |
| `server/` | HTTP server（给 TUI 用） |

---

## 2. 八大核心模块详解

> 下面 8 节是 Explore agent 对 `packages/opencode/src/` 的深度阅读结果，作为我们后续 Python 实现的"源代码契约"。

### 2.1 Agent Loop

**做什么。** Agent loop 编排"用户消息 → LLM 流式响应 → 工具调用 → 工具结果 → 继续"的循环。当：(1) `agent.steps` 达上限 / (2) 权限拒绝 / (3) token 溢出需要 compaction / (4) LLM 报告完成 时停止。中断时把未完成的 tool call 标记为 `interrupted` 并清理 pending deferred。

**关键代码：**
- `agent/agent.ts:28-49` — `Info`：agent 定义（name、mode、permissions、model、temperature、topP、prompt）
- `session/llm.ts:35-52` — `StreamInput` / `StreamRequest`
- `session/processor.ts:39-55` — `Handle`：`message`、`updateToolCall`、`completeToolCall`、`process()`
- `session/processor.ts:721-789` — `process()` 主循环：消费 LLM stream、分发事件、失败重试
- `session/processor.ts:214-630` — `handleEvent()`：路由 20+ 事件类型（reasoning、tool-call、text、finish-step、error 等）

**数据流：**
1. `processor.create()` 初始化 handle + 初始 snapshot
2. `handle.process(streamInput)` 调用 `llm.stream()`，得到事件 async iterable
3. 每个事件就地更新 `assistantMessage`、写入 DB 的 `ToolPart` / `TextPart` / `ReasoningPart`
4. 工具调用挂起 stream，等 `completeToolCall` / `failToolCall` 信号
5. 返回 `"continue"` | `"compact"` | `"stop"`

**LangGraph 关联点：** 这是整个 graph 的中心循环节点；条件边按 finish_reason 分支；中断通过 abort signal + Deferred 完成。

---

### 2.2 Tool Registry & Execution

**做什么。** 工具用 Effect schema 定义（id、description、parameters、execute、formatValidationError）。Registry 启动时加载约 20 个内置工具（read、edit、shell、task、glob、grep、webfetch、todowrite…）+ 插件工具 + 自定义目录工具。每个工具被 `wrap()` 自动加上参数校验、输出截断、span tracing。LLM 通过 JSON 校验后的参数选择工具。

**关键代码：**
- `tool/tool.ts:35-45` — `Def`：tool 定义
- `tool/tool.ts:16-26` — `Context`：sessionID、messageID、agent name、abort signal、`ask()`、`metadata()`
- `tool/registry.ts:73-78` — `Interface`：`ids()` / `all()` / `tools(model)` / `named()`
- `tool/registry.ts:138-267` — `state` generator：懒加载插件工具、初始化内置工具、应用 feature flag
- `tool/tool.ts:79-130` — `wrap()`：参数校验 + 输出截断 + span 归因

**特殊工具：**
- `task` — 启动 subagent（详见 §2.7）
- `question` — 向用户提问（权限门控）
- `skill` — 加载领域 instruction prompt

**LangGraph 关联点：** Tool registry 整体放进 graph 的初始 state；`tool_exec` 节点收到 (name, args) 后查表 → 校验 → 执行；ctx.ask() 在节点内同步阻塞等权限。

---

### 2.3 Permission System

**做什么。** 规则化：`(permission, pattern) → allow|deny|ask`，从右往左贪婪匹配，最后一条命中的规则胜出。需要 ask 时往 bus 发 `Event.Asked`，UI 回 (once / always / reject)。always 会把规则追加到 approved ruleset 并自动放行同 pattern 的 pending 请求；reject 会把同 session 的 pending 全部 cascade 拒绝。

**关键代码：**
- `permission/index.ts:19-30` — `Action` / `Rule` / `Ruleset`
- `permission/index.ts:32-45` — `Request`
- `permission/index.ts:161-196` — `ask()` 主入口
- `permission/evaluate.ts` — `evaluate(permission, pattern, ...rulesets): Rule`（greedy-rightmost）
- `permission/index.ts:287-289` — `merge(...rulesets)`
- `permission/index.ts:293-302` — `disabled(tools, ruleset)`：把被 deny 的编辑类工具直接从工具列表里摘除

**错误类型：** `DeniedError`、`RejectedError`、`CorrectedError`（带 user feedback）。

**LangGraph 关联点：** 既可以做成独立节点 `check_permission`，也可以收编到 `tool_exec` 内部。需要"ask"时整张 graph 进入 `interrupt`，等用户回复后 resume。

---

### 2.4 Session / 持久化

**做什么。** Session = 一段对话线程（带 dir、agent、model、permission、history）。存 SQLite。消息（MessageV2）由 Part 组成：text、tool、reasoning、patch、snapshot、compaction、file。Resume 是 `fork()`：把历史 clone 到某个 messageID 之前，重新发号。token 溢出时触发 compaction（用专门的 compact agent 总结老消息）。

**关键代码：**
- `session/schema.ts` — `SessionID`、`MessageID`、`PartID`（升降序 ID 保排序）
- `session/session.ts:207-227` — `Info` schema
- `session/session.ts:60-111` — SQLite ↔ Info
- `session/session.ts:522-568` — `createNext()`
- `session/session.ts:678-718` — `fork()`：clone messages ≤ messageID，带 idMap
- `session/message-v2.ts` — Part 类型族
- `session/overflow.ts` — `isOverflow()` / `usable()`
- `session/processor.ts:549-551` — 触发 compaction

**LangGraph 关联点：** LangGraph 内置 `Checkpointer` 几乎一一对应（state 快照 + thread_id + 时间旅行）。我们额外需要 `Part` 这种细粒度结构去支持流式 UI。

---

### 2.5 Provider 抽象

**做什么。** 用 AI SDK 的统一接口。Registry 从 BUNDLED_PROVIDERS（Anthropic、OpenAI、Bedrock、Vertex、GitLab…）动态 import，模型能力（temperature、top_p、context window）归一化，provider 特化的消息转换在 `provider/transform.ts`（如 OpenAI OAuth 的 system → instructions）。Options 合并顺序：provider 默认 < model < agent。

**关键代码：**
- `provider/provider.ts:87-117` — `BUNDLED_PROVIDERS`
- `provider/provider.ts:119-128` — `CustomLoader`
- `provider/transform.ts` — `temperature()` / `topP()` / `maxOutputTokens()` / `smallOptions()` / `message()` / `providerOptions()`
- `session/llm.ts:90-98` — 并发拉 model / provider / auth
- `session/llm.ts:146-159` — GitLab workflow 特殊路径

**LangGraph 关联点：** 我们写一个 `ModelRouter`（不是节点，是工具类），在 `llm_call` 节点之前完成选型 + 消息变换。

---

### 2.6 MCP 集成

**做什么。** MCP server 来自 config，启动 stdio/HTTP/SSE transport，握手后 `listTools(timeout=30s)`，把每个 MCPToolDef 包装成 AI SDK Tool 注入 registry。output schema 校验失败时退化重试（去 outputSchema）。OAuth 走 `mcp/auth.ts`。

**关键代码：**
- `mcp/index.ts:42-49` — `Resource`
- `mcp/index.ts:51-56` — `ToolsChanged` event
- `mcp/index.ts:72-96` — Status：connected / disabled / failed / needs_auth / needs_client_registration
- `mcp/index.ts:124-151` — `listTools()` + retry
- `mcp/index.ts:154-182` — `convertMcpTool()`：→ AI SDK `dynamicTool`

**LangGraph 关联点：** 启动期一次性把 MCP tools 注入 registry，运行时与内置工具无差别。

---

### 2.7 Sub-Agent / Task 工具

**做什么。** `task` 工具开新 agent。subagent 是 `Agent.mode === "subagent"`，用户不能直接调用。可前台（阻塞返回结果）或后台（立刻返回 task_id，用户用 `task_status` 轮询）。权限继承：父 agent 的 edit denies + 父 session 的 denies + 默认的 todowrite/task denies（除非 subagent 自身已 allow）。

**关键代码：**
- `tool/task.ts:19-24` — `TaskPromptOps`
- `tool/task.ts:26-52` — `Parameters`
- `tool/task.ts:95-150+` — execute：resume vs new、前台 vs 后台
- `agent/subagent-permissions.ts` — `deriveSubagentSessionPermission()`

**LangGraph 关联点：** subagent = 嵌套 subgraph，复用同一份 agent loop 定义；前台 = 子图同步 invoke，后台 = `spawn` + 父图返回 task_id。

---

### 2.8 Bus / Events

**做什么。** Effect PubSub。双通道：wildcard（全事件）+ typed（按事件类型）。每次 state 变更后 publish，UI/同步层订阅。例子：`Permission.Event.Asked`、`Session.Event.Error`、`Session.Event.Updated`、`MessageV2.Event.Updated`。

**关键代码：**
- `bus/index.ts:32-44` — `Interface`：publish / subscribe / subscribeAll / *Callback
- `bus/index.ts:87-108` — `publish()`
- `bus/index.ts:131-157` — `on()`

**LangGraph 关联点：** 不是节点；用 Python 端的 `asyncio.Queue` / `anyio.MemoryObjectStream` 实现等价能力，给 TUI 推流。

---

## 3. opencode → LangGraph 节点映射表

我们的 Python 实现会建立一个主 `StateGraph[AgentState]`，subagent 用 subgraph 嵌套。

### 3.1 AgentState（顶层 state）

```python
class AgentState(TypedDict):
    # 会话标识
    session_id: str
    thread_id: str            # LangGraph checkpointer 用
    parent_session_id: str | None

    # 配置
    agent: AgentConfig        # name, model, temperature, prompt, permission, steps
    cwd: str

    # 消息
    messages: list[MessageV2] # 完整历史；每条带 parts
    pending_user_input: UserInput | None

    # 当前 step 的工作区
    assistant_draft: MessageV2 | None   # 流式累积中的助手消息
    pending_tool_calls: list[ToolCall]  # 已收到调用但未执行完
    tool_results: list[ToolResult]      # 本轮工具产出，下一次 LLM call 携带

    # 权限缓存（session 级）
    approved_ruleset: Ruleset

    # 计费 & 限制
    tokens: TokenUsage
    step_count: int
    max_steps: int

    # 控制流
    finish_reason: Literal["continue", "compact", "stop", "interrupted"] | None
    last_error: ErrorInfo | None
```

### 3.2 节点 / 边对照

| LangGraph 节点 | 对应 opencode 代码 | 职责 | 出边 |
|---|---|---|---|
| `START` → `prepare_input` | `session/llm.ts:35-90` | 拼 system prompt、装载 history、解析 user message 的 file/image 引用 | → `llm_call` |
| `llm_call` | `session/llm.ts` + `provider/transform.ts` | 选 provider+model、应用 transform、发起 streamText、把事件源源不断写进 state | → `route_event`（条件） |
| `route_event` | `session/processor.ts:214-630 handleEvent` | 把当前事件分类：text / reasoning / tool_call / finish_step / error | text/reasoning → 回 `llm_call` 续流；tool_call → `check_permission`；finish_step → `decide_next`；error → `handle_error` |
| `check_permission` | `permission/index.ts:161-196 ask()` + `permission/evaluate.ts` | 用 ruleset 评估；allow 直通；ask 触发 `interrupt()`；deny 抛错 | allow → `exec_tool`；deny → `handle_error`；ask → `interrupt` → 用户回复后回到自身 |
| `exec_tool` | `tool/registry.ts` + `tool/tool.ts wrap()` | 查 registry、Schema 校验参数、运行 `execute()`、截断输出 | → `record_tool_result` |
| `record_tool_result` | `session/processor.ts completeToolCall` | 把结果作为新 Part 写入 assistant_draft 与持久层；publish bus event | → `llm_call`（带上新 tool result） |
| `decide_next` | `session/processor.ts:721-789 process()` 末尾 | 看 step_count、finish_reason、`isOverflow()` | continue → `llm_call`；compact → `compact`；stop → `END` |
| `compact` | `session/compaction.ts` + `session/overflow.ts` | 用 compact agent 子图总结历史，生成 CompactionPart 替换老消息 | → `llm_call` |
| `handle_error` | `session/processor.ts` error 分支 + `session/retry.ts` | 区分可重试 / 致命，决定重试还是终止 | retry → `llm_call`；fatal → `END` |
| `task_subgraph`（被 `exec_tool` 在 tool=task 时 invoke） | `tool/task.ts` + `agent/subagent-permissions.ts` | 派生权限、创建子 session、用同一份 AgentState graph invoke；后台模式立即返回 task_id | 完成后回到父图的 `record_tool_result` |

### 3.3 横切关注点（非节点）

| 关注点 | opencode 实现 | Python 侧设计 |
|---|---|---|
| 持久化 | SQLite + `session.sql.ts` + SyncEvent | LangGraph `SqliteSaver` checkpointer + 业务 metadata 表（SQLAlchemy） |
| 事件总线 | Effect PubSub | `anyio.create_memory_object_stream`，TUI 订阅 |
| 流式输出 | AI SDK stream + Effect Stream | LangGraph `astream_events` + 自定义 channel |
| 中断 / 恢复 | abort signal + Deferred | LangGraph `interrupt()` + `Command(resume=...)` |
| Provider 抽象 | AI SDK + transform.ts | `langchain-*` 的 chat model + 自写 `ModelRouter` |
| MCP | `@modelcontextprotocol/sdk` | 官方 `mcp` Python SDK + `MCPToolAdapter`（包成 `BaseTool`） |

---

## 4. Python 项目骨架（Phase 1 起点）

```
src/opencode_py/
├── __init__.py
├── cli.py                  # typer 入口
├── config/                 # pydantic-settings：env / file / cli 三层
├── agent/
│   ├── state.py            # AgentState TypedDict
│   ├── graph.py            # build_agent_graph() → CompiledStateGraph
│   ├── nodes/
│   │   ├── llm_call.py
│   │   ├── route_event.py
│   │   ├── check_permission.py
│   │   ├── exec_tool.py
│   │   ├── decide_next.py
│   │   ├── compact.py
│   │   └── handle_error.py
│   └── prompts/            # 对应 opencode 的 *.txt
├── tools/
│   ├── base.py             # ToolDef 协议
│   ├── registry.py
│   ├── builtin/
│   │   ├── read.py write.py edit.py glob.py grep.py
│   │   ├── bash.py
│   │   ├── task.py         # subagent
│   │   ├── todowrite.py
│   │   └── webfetch.py
│   └── mcp_adapter.py
├── permission/
│   ├── schema.py rules.py evaluate.py
│   └── prompt.py           # 与 TUI 解耦的 ask() 协议
├── providers/
│   ├── router.py
│   ├── anthropic.py openai.py google.py
│   └── transform.py
├── session/
│   ├── models.py           # MessageV2 / Part
│   ├── store.py            # SQLite（业务侧）
│   ├── compaction.py overflow.py
│   └── fork.py
├── mcp/
│   ├── client.py auth.py
├── bus/
│   └── events.py
├── tui/                    # Phase 4 才填
└── server/                 # 可选，供未来 SDK 用
tests/
docs/
```

---

## 5. Phase 1 入场清单（下一步要做的事）

1. **建立 Python 工程骨架**（uv init + 上述目录 + ruff + mypy + pytest）
2. **实现最小 AgentState + StateGraph**：节点先只有 `prepare_input` / `llm_call` / `route_event` / `exec_tool` / `decide_next`
3. **实现 5 个核心工具**：`read` / `write` / `edit` / `bash` / `glob`（参考 [`packages/opencode/src/tool/`](../reference/opencode/packages/opencode/src/tool/) 对应文件的 schema 与 prompt）
4. **接 1 个 provider**（Anthropic via `langchain-anthropic`），跑通端到端 CLI 单轮 + 多轮 + 1 个工具调用 + 1 次 permission ask
5. **接入 LangGraph SqliteSaver checkpointer**，验证 resume / fork

---

## 6. 已识别的实现风险与缓解

| 风险 | 缓解 |
|---|---|
| LangGraph `interrupt()` 在长流式过程中触发，可能与 token stream 冲突 | 把 `check_permission` 设计成"先收齐 tool_call、暂停 stream、再 interrupt"；不在 token 流中间打断 |
| AI SDK 的事件类型很丰富，LangChain 的 chunk 抽象更扁 | 自定义 `LLMEvent` union 类型，在 `llm_call` 内部把 LangChain chunk 翻译成 opencode 风格事件 |
| Windows 上 bash 工具 | 检测 WSL → Git Bash → 失败兜底；Phase 1 就在 Win11 上测，避免最后才暴露 |
| MCP stdio transport 子进程在 Win 上 PTY 行为差异 | 优先 SSE/HTTP transport；stdio 用 `anyio.open_process` 而非裸 subprocess |
| Effect Schema → Python | 直接用 pydantic v2 / `BaseModel`，丢掉 Effect 的 generator 风格，逻辑等价即可 |

---

## 7. 参考链接

- 源码：[reference/opencode/packages/opencode/src/](../reference/opencode/packages/opencode/src/)
- LangGraph 文档（State / Checkpointer / interrupt）：在 Phase 1 实施前再查最新版
- MCP Python SDK：`pip install mcp`

— end of Phase 0 —
