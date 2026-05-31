# Phase 3 手工端到端回归步骤

> 目标：验证 Phase 3 的核心交互能力与观测指标：`/compact`、自动 overflow 压缩、`/sessions` 切换、`fork` 分支会话。
>
> 环境：Windows 11 + Git Bash，仓库根目录 `c:/Users/yunkaizhang/project/re-written-open-code/`。

---

## 0. 准备

```bash
cd /c/Users/yunkaizhang/project/re-written-open-code
export PATH="/c/Users/yunkaizhang/.local/bin:$PATH"
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
uv run opencode-py doctor
```

期望：
- `api key set: True`
- `compaction enabled: True`
- 正常打印 `compaction trigger tokens`

---

## 剧本 ① — 手动 `/compact`

```bash
uv run opencode-py chat
```

在 REPL 中输入：
1. `请记住：项目代号 alpha，负责人 bob，截止日期 2026-07-01。`
2. `/compact`

期望：
- 出现 `Compaction completed.`
- 出现 `summary:` 预览
- token 行包含：`compact=`、`trig=`、`overflow=`、`counter=`、`window=before->after`、`ratio=`

---

## 剧本 ② — 自动 overflow 触发压缩

在同一会话连续输入 8~12 轮长文本（每轮可要求复述并追加约束），例如：
- `请把以下内容逐条整理并保留关键数字：...`（粘贴较长文本）

期望：
- 某轮开始后 `compact` 计数增长
- `trig` 计数增长
- `overflow=threshold` 至少出现一次
- `window=...` 显示压缩前后规模变化

---

## 剧本 ③ — `/sessions` 交互切换

在会话中输入：
1. `/sessions`
2. 选择另一个 session 的 index（或 thread_id）
3. 再发一句：`你当前会话标题是什么？`

期望：
- 输出 `Switched to session: ...`
- 后续对话基于被切换会话继续

---

## 剧本 ④ — `fork` 分叉会话

先记录一个已有 thread_id，然后执行：

```bash
uv run opencode-py fork <thread_id>
uv run opencode-py sessions
```

期望：
- 输出 `Forked <src> -> <dst>`
- `sessions` 列表中出现新会话，且带 `parent=<src>`

再验证父子隔离：

```bash
uv run opencode-py resume <dst> "在子会话里记住标签 child-only"
uv run opencode-py resume <src> "我刚才在这里记了什么标签？"
```

期望：
- 子会话记住 `child-only`
- 父会话不应错误继承子会话新增内容

---

## 通过标准

- 4 个剧本全部通过
- 无崩溃或 DB 锁异常
- `sessions` 与 token 行中的 compaction 指标可见且合理
