# Phase 3 实现细节技术文档

> 文档目标：记录 Phase 3 在当前仓库中的**实际实现**、关键代码位置、数据流和验证方式，便于后续迭代（Phase 4+）直接接续。

---

## 1. Phase 3 范围与结果

Phase 3 目标包含三块：

1. 上下文溢出检测（context overflow detection）
2. 自动压缩（auto-compaction）
3. Session 元数据管理（list / fork）

当前实现状态：**核心能力已落地**，并通过 pytest 回归（24 passed）。

---

## 2. 配置层实现（overflow / compaction 参数）

文件：
- [src/opencode_py/config.py](../src/opencode_py/config.py)

新增配置项：

- `context_window_tokens`
- `compaction_enabled`
- `compaction_trigger_ratio`
- `compaction_reserved_tokens`
- `compaction_tail_turns`
- `compaction_max_summary_chars`

新增 helper：

- `usable_context_tokens()`
- `compaction_trigger_tokens()`

作用：
- 为 graph 内 overflow 判断提供统一阈值来源
- 避免把“策略常量”硬编码在节点逻辑里

---

## 3. AgentState 扩展（保持 primitive-only）

文件：
- [src/opencode_py/agent/state.py](../src/opencode_py/agent/state.py)

新增字段：

- `session_id`
- `fork_parent_thread_id`
- `estimated_tokens`
- `overflow`
- `compaction_count`
- `last_compaction_summary`

设计说明：
- 延续 Phase 2 的序列化修复策略：state 内仅保存 primitive 结构
- 避免 checkpoint 反序列化对自定义类（Pydantic model）的未来兼容风险

---

## 4. Graph 扩展：overflow 节点 + compaction 节点

文件：
- [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py)

### 4.1 新增辅助函数

- `_estimate_message_tokens(messages, agent)`
  - 优先使用 provider/model 的 `get_num_tokens_from_messages` 计数
  - 失败时回退 `_estimate_message_tokens_fallback`（字符估算）
- `_visible_messages(state)`
  - 从完整历史中构造“可见窗口”（summary + tail）供后续 LLM 调用
- `_is_context_overflow(estimated_tokens)`
  - 根据配置阈值判定是否 overflow
- `_split_head_tail_messages(messages, tail_turns)`
  - 保留最近 N 轮 user turn，旧历史进入 summary
- `_build_compaction_prompt(head_messages, previous_summary)`
  - 构建压缩提示词
- `_compact_with_llm(agent, prompt)`
  - 调用基础 LLM（不绑 tools）生成 summary

### 4.2 新增节点

- `check_overflow`
  - 计算 `estimated_tokens`
  - 写入 `overflow` 标记
- `compact_context`
  - 对 head 历史做摘要
  - 不物理删除历史消息；仅更新可见窗口边界
  - 更新 `compaction_count` / `last_compaction_summary` / `visible_start_index`

### 4.3 图结构变化

Phase 2：

```text
prepare_input -> llm_call -> route_event -> exec_tools -> ...
```

Phase 3：

```text
prepare_input -> check_overflow -> (compact_context | llm_call)
compact_context -> (llm_call | END)   # /compact 时直接 END
llm_call -> route_event -> (exec_tools | END)
exec_tools -> check_overflow | END
```

关键点：
- `exec_tools` 后不再直接回 `llm_call`，而是先回 `check_overflow`
- 工具输出膨胀上下文时可即时触发 compaction
- compaction 后默认保留完整历史，仅在后续推理时使用“summary + tail”的可见窗口
- 用户输入 `/compact`（兼容 `/compat`）时，可强制执行 compaction 且本轮不再触发常规对话

---

## 5. Session 元数据存储实现

文件：
- [src/opencode_py/session/models.py](../src/opencode_py/session/models.py)
- [src/opencode_py/session/store.py](../src/opencode_py/session/store.py)

### 5.1 新增数据模型

- `SessionMeta`
- `SessionForkMeta`

### 5.2 新增存储模块 API

- `init_schema(db_path)`
- `upsert_session(db_path, meta)`
- `touch_session(...)`
- `list_sessions(...)`
- `record_fork(...)`
- `get_session(...)`
- `make_session_meta(...)`

### 5.3 表结构（同一个 SQLite 文件）

- `session_meta`
- `session_fork`

说明：
- 与 LangGraph checkpoint 共用同一个 DB 文件（`settings.session_db_path()`）
- 元数据表与 checkpoint 表隔离，避免互相污染

---

## 6. CLI 功能扩展

文件：
- [src/opencode_py/cli.py](../src/opencode_py/cli.py)

### 6.1 `_run_chat` 生命周期增强

- 会话启动时 `init_schema`
- 新会话自动写入 `session_meta`
- 每轮结束后 `touch_session` 更新：
  - `message_count`
  - `compaction_count`
  - `last_user_preview`

### 6.2 新命令

- `sessions`
  - 展示会话列表（thread/provider/model/message_count/compaction_count/parent）
- `fork <thread_id>`
  - 使用 `AsyncSqliteSaver.acopy_thread` 复制线程 checkpoint
  - 写入 `session_meta`（parent linkage）
  - 写入 `session_fork` 记录

### 6.3 交互细节增强

- 输出前缀从 `assistant›` 调整为 `assistant>`，降低 Windows 编码问题触发概率
- 新增 `/compact`（兼容 `/compat`）触发手动压缩
- 每轮结束输出 token 统计：`turn` 与 `total` 分开展示，同时展示 `estimated_ctx` 与 `compact` 次数

---

## 7. 测试覆盖

新增测试文件：

- [tests/test_overflow.py](../tests/test_overflow.py)
- [tests/test_compaction.py](../tests/test_compaction.py)
- [tests/test_session_store.py](../tests/test_session_store.py)
- [tests/test_graph_compaction_routing.py](../tests/test_graph_compaction_routing.py)
- [tests/test_cli_sessions.py](../tests/test_cli_sessions.py)

验证结果：

- `uv run pytest -q` → **24 passed**

---

## 8. 关键实现决策

1. **token 估算使用轻量策略**
   - 当前不是 provider 专属 tokenizer
   - 目标是先形成稳定路由钩子，后续可替换为精确计数

2. **compaction 用“summary + tail”策略**
   - 保留最近轮次完整上下文，降低行为漂移
   - 老历史折叠成单条摘要，控制上下文增长

3. **session metadata 与 checkpoint 解耦**
   - checkpoint 负责图状态恢复
   - metadata 负责“可管理性”（list/fork/审计）

4. **继续坚持 primitive-only state**
   - 避免 LangGraph 未来 stricter msgpack 反序列化风险

---

## 9. 已知限制与下一步

当前限制：

1. provider 计数在部分环境可能失败并回退到字符估算（已有 fallback）
2. compaction prompt 策略仍是 MVP，缺少可观测性指标
3. sessions/fork 目前是 CLI 级别管理，尚未加入更细粒度过滤/归档能力

建议下一步（Phase 3.1 或 Phase 4 前置）

1. 接 provider-aware tokenizer 统计
2. 为 compaction 增加 telemetry（触发次数、压缩前后长度）
3. 给 sessions 增加过滤与详情查看命令

---

## 10. 快速验证命令

```bash
# 1) 全量测试
uv run pytest -q

# 2) 环境检查
uv run opencode-py doctor

# 3) 新会话 + 触发工具
uv run opencode-py chat "list python files under src/opencode_py"

# 4) 查看会话列表
uv run opencode-py sessions

# 5) fork 某会话
uv run opencode-py fork thr_xxxxxxxxxxxx

# 6) 手动触发压缩
#   /compact 可在 chat/repl 中输入（兼容 /compat）
```
