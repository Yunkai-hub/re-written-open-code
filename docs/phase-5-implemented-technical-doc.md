# Phase 5 实现细节技术文档（5A/5B）

> 文档目标：记录当前仓库中 MCP 集成（Phase 5A/5B）的实际实现、代码入口与验证方式。

---

## 1. 当前范围

Phase 5 在当前仓库已实现的能力：

1. MCP 配置加载（JSON + schema 校验）
2. transport 路径：`stdio` 与 `sse`
3. MCP tool 动态注入运行时 registry
4. 权限系统接入 `mcp` 通道（默认 `ask`）
5. CLI 状态可见性与 `mcp-tools` 命令

---

## 2. 配置层

文件：
- [src/opencode_py/config.py](../src/opencode_py/config.py)
- [src/opencode_py/mcp/schema.py](../src/opencode_py/mcp/schema.py)
- [src/opencode_py/mcp/loader.py](../src/opencode_py/mcp/loader.py)

关键配置项：
- `mcp_enabled`
- `mcp_config_path`
- `mcp_startup_strict`
- `mcp_default_timeout_ms`

MCP server 配置支持：
- `transport=stdio`（需 `command`）
- `transport=sse`（需 `url`）

---

## 3. 运行时注入链路

文件：
- [src/opencode_py/mcp/manager.py](../src/opencode_py/mcp/manager.py)
- [src/opencode_py/mcp/client.py](../src/opencode_py/mcp/client.py)
- [src/opencode_py/mcp/adapter.py](../src/opencode_py/mcp/adapter.py)
- [src/opencode_py/tools/registry.py](../src/opencode_py/tools/registry.py)

流程：
1. CLI 启动时触发 MCP bootstrap
2. manager 按 server transport 构造 client：
   - `MCPStdioClient`
   - `MCPSSEClient`
3. client 执行 `initialize` + `tools/list`
4. 每个 MCP tool 经 `make_mcp_tooldef` 转换成 `ToolDef`
5. 通过 `registry.register_many(..., dynamic=True)` 注入

命名规则：
- MCP tool 统一命名为 `mcp_<server>_<tool>`
- 非法字符会被替换为 `_`

---

## 4. 与现有 graph 的集成方式

文件：
- [src/opencode_py/agent/graph.py](../src/opencode_py/agent/graph.py)

集成策略：
- 不改主图结构
- 复用既有工具执行路径：`_tool_schemas()` + `exec_tools`
- 因为 MCP 工具被适配成 `ToolDef`，所以执行期无需特判 MCP 分支

---

## 5. CLI 与可观测性

文件：
- [src/opencode_py/cli.py](../src/opencode_py/cli.py)

已实现：
- `doctor` 输出 MCP 启动摘要（servers/tools/errors）
- 命令 `mcp-tools` 列出当前注入 MCP 工具
- chat REPL 支持 `/mcp-tools`
- 会话退出时显式 shutdown MCP manager，避免子进程管道析构告警

---

## 6. 测试覆盖

新增/扩展测试：
- [tests/test_mcp_schema.py](../tests/test_mcp_schema.py)
- [tests/test_mcp_loader.py](../tests/test_mcp_loader.py)
- [tests/test_mcp_registry_injection.py](../tests/test_mcp_registry_injection.py)
- [tests/test_mcp_tool_execution.py](../tests/test_mcp_tool_execution.py)
- [tests/test_mcp_manager_bootstrap.py](../tests/test_mcp_manager_bootstrap.py)
- [tests/test_mcp_sse_client.py](../tests/test_mcp_sse_client.py)
- [tests/test_cli_mcp_bootstrap.py](../tests/test_cli_mcp_bootstrap.py)

当前回归结果：
- `uv run pytest -q` 通过（最新为 42 passed）

---

## 7. 已知限制与下一步

当前限制：
1. SSE 路径目前是最小可用请求流，仍可增强连接管理与恢复策略
2. 远端服务鉴权与错误观测可进一步完善
3. 缺少更大规模真实 MCP 服务组合下的长时回归数据

建议下一步：
1. 构建真实远端 MCP E2E 测试矩阵（stdio+sse）
2. 加强 SSE 重试/退避与状态诊断
3. 与 Phase 4 TUI 的工具可视化协同设计
