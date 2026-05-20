# Phase 1 手工端到端测试步骤

> 目标：验证 Phase 1 MVP 的 5 项核心能力 —— LLM 调通、工具循环、权限三档（once/always/reject）、Windows shell 兜底、SQLite resume。
>
> 环境：Windows 11 + Git Bash。所有命令在仓库根目录 `c:/Users/yunkaizhang/project/re-written-open-code/` 下执行。

---

## 0. 一次性准备

```bash
# 打开 Git Bash，进入项目目录
cd /c/Users/yunkaizhang/project/re-written-open-code

# 把 uv 加进 PATH（每个新开的 bash 都要做一次，或写进 ~/.bashrc）
export PATH="/c/Users/yunkaizhang/.local/bin:$PATH"

# 设置 Anthropic API key（任选一种）
#   方式 A：临时（当前 shell 有效）
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx

#   方式 B：持久化（推荐）—— 在仓库根建 .env
echo "ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx" > .env

# 自检环境
uv run opencode-py doctor
```

**`doctor` 期望输出：**
```
model: claude-sonnet-4-5-20250929
data dir: C:\Users\yunkaizhang\.opencode-py
db: C:\Users\yunkaizhang\.opencode-py\sessions.sqlite
api key set: True       ← 必须是 True，否则下面所有测试都会失败
```

如果 `api key set: False`：检查 `.env` 是否在当前目录、是否拼写正确、是否漏了引号。

---

## 剧本 ① — 纯文本单轮 + REPL（验证 LLM 链路）

**目的：** 确认 ChatAnthropic 调用通、流程没死循环、REPL 正常退出。

```bash
uv run opencode-py chat "用一句话介绍 LangGraph"
```

**期望：**
1. 终端先打印一行 `session: thr_xxxxxxxxxx  model: claude-...  cwd: ...` —— **把这个 thread_id 记下来**（剧本 ⑤ 要用）。
2. 助手返回 1 句话介绍 LangGraph。
3. 进入 `you›` 提示符等待下一句输入。
4. 输入 `/exit` 回车 → 干净退出，无报错。

**红旗：**
- 卡住 >30s 不返回 → 可能是网络或 key 无效，按 `Ctrl+C` 退出。
- 报 `model not found` → 编辑 [src/opencode_py/config.py](../src/opencode_py/config.py) 把默认模型改成你账号能用的版本（如 `claude-3-5-sonnet-20241022`）。

---

## 剧本 ② — 多轮 + 自动放行的工具（验证 tool loop）

**目的：** 确认 LLM 能连续触发多个工具调用，`read` / `glob` 因为 `DEFAULT_RULESET` 设了 `allow` 不会弹提示。

```bash
uv run opencode-py chat "列出 src/opencode_py 下的所有 .py 文件，再读 cli.py 前 30 行"
```

**期望：**
1. 第一轮 LLM 决定调用 `glob`，立刻执行，无提示。
2. 第二轮 LLM 决定调用 `read`，立刻执行，无提示。
3. 第三轮 LLM 输出文字总结（文件列表 + cli.py 头部代码片段）。
4. 整个过程没有 `[permission]` 字样。

**红旗：**
- 弹出权限提示 → `DEFAULT_RULESET` 配错了，检查 [permission/schema.py](../src/opencode_py/permission/schema.py)。
- 助手回"我没有工具" → tool binding 失败，检查 [agent/graph.py](../src/opencode_py/agent/graph.py) 里 `bind_tools` 调用。

---

## 剧本 ③ — 权限三档（验证 once / always / reject）

**目的：** 验证 `ask` 决策、`always` 缓存进 session ruleset、`reject` 把结果回填给 LLM。

每一档用**新会话**测，避免上一档的 always 规则污染。

### ③.1 — once（一次性允许）

```bash
uv run opencode-py chat "在当前目录创建 hello.txt，内容是 hi"
```

期望：
1. 终端打印：
   ```
   [permission] write: hello.txt
     detail: {"path": "hello.txt", "content": "hi"}
     allow (o)nce / (a)lways / (r)eject?
   ```
2. 输入 `o` 回车 → 工具执行，助手确认写入。
3. 紧接着输入：`再创建一个 hello2.txt 内容是 hi2`
4. **再次弹提示**（说明 once 没有缓存规则）。按 `o` 继续。
5. 验证文件：另开 bash 跑 `ls hello*.txt` 应看到两个文件。`rm hello*.txt` 清理。
6. `/exit` 退出。

### ③.2 — always（永久允许同 session）

```bash
uv run opencode-py chat "创建 a.txt 内容 a"
```

1. 弹提示 → 输入 `a` 回车 → 写入。
2. 输入：`再创建 b.txt 内容 b`
3. **不再弹提示**，直接写入（说明 `Rule(write, a.txt, allow)` 已加入 approved ruleset，但 b.txt 不匹配 a.txt 的 pattern，应该还是会弹）。

> ⚠️ **预期偏差说明：** 当前实现 `always` 缓存的 pattern 是**具体文件名**（`pattern_from_args` 返回 `path`），所以严格讲只对同一个文件免提示。如果你想"按 always 后所有 write 都放行"，需要把 pattern 改为 `*`。当前行为是**安全默认**。

正确的 always 验证方式：
```
you› 创建 a.txt 内容 a
[permission] write: a.txt ...  → 输入 a
you› 再写一遍 a.txt，内容改成 a2
（不再弹提示，直接覆盖）        ← 这才是 always 生效证据
```

清理：`rm a.txt b.txt`，`/exit`。

### ③.3 — reject

```bash
uv run opencode-py chat "用 write 工具创建 dangerous.txt 内容 boom"
```

1. 弹提示 → 输入 `r` 回车。
2. 助手收到 tool result = `permission denied by user`，应当**用文字回复**说明被拒绝、不会重试。
3. 验证：`ls dangerous.txt 2>&1` 应该报"No such file"。
4. `/exit`。

---

## 剧本 ④ — bash 工具 + Windows shell 兜底

**目的：** 验证 [tools/builtin/bash.py](../src/opencode_py/tools/builtin/bash.py) 的 `_pick_shell()` 在 Win11 上正确选了 Git Bash（你装了 Git for Windows）。

```bash
uv run opencode-py chat "运行 git --version 并告诉我结果"
```

1. 弹 `[permission] bash: git` → 输入 `o`。
2. 助手返回 `git version 2.x.x.windows.x`。

进阶检查 —— 跑一个明显是 Unix shell 才支持的命令：
```bash
uv run opencode-py chat "运行 'echo \$HOME && uname -s' 告诉我结果"
```

期望：能输出 `/c/Users/yunkaizhang` 和 `MINGW64_NT-...` 之类 —— 说明走的是 Git Bash 而非 cmd.exe。

如果输出像 `%HOME%` 没被解析、或者 `uname: 不是内部命令`，说明退化到了 cmd.exe，回去看 `_pick_shell()` 的 `shutil.which("bash")` 为什么没命中。

---

## 剧本 ⑤ — Resume（验证 SqliteSaver 持久化）

**目的：** 验证 LangGraph checkpointer 把对话写进了 SQLite，且 `resume` 命令能完整恢复 history。

```bash
# 第一段：让它记住一个数字
uv run opencode-py chat "记住数字 42，等下我会问你"
```

1. 记下输出第一行的 `session: thr_xxxxxxxxxx`。
2. 助手确认收到。
3. `/exit` 退出。

```bash
# 验证 DB 已生成
ls -la ~/.opencode-py/sessions.sqlite
# 应看到一个非零大小的文件
```

```bash
# 第二段：用上面的 thread_id resume
uv run opencode-py resume thr_xxxxxxxxxx "我刚让你记的数字是多少？"
```

期望：助手回答 `42`（或包含 42 的句子）。

**红旗：**
- 助手回"我不记得"或"这是新对话" → checkpointer 没生效，检查 [cli.py](../src/opencode_py/cli.py) 里 `AsyncSqliteSaver.from_conn_string` 是否真正传给了 `build_graph`。
- 报 `database is locked` → 前一次进程没干净退出，关掉残留 python 进程或删 `sessions.sqlite-journal`。

---

## 整体通过标准

5 个剧本都按预期跑完即视为 Phase 1 验收通过。把通过/失败的剧本编号回来告诉我即可。

## 清理（可选）

```bash
# 删测试产物
rm -f hello*.txt a.txt b.txt dangerous.txt

# 清空所有会话历史（如果想从头来）
rm -f ~/.opencode-py/sessions.sqlite*
```
