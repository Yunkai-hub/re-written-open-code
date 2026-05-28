from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from opencode_py.agent.state import AgentState
from opencode_py.config import settings
from opencode_py.permission.prompt import CLIPrompter, PermissionPrompter
from opencode_py.permission.schema import DEFAULT_RULESET, Rule, Ruleset, evaluate
from opencode_py.providers import build_chat_model
from opencode_py.session.models import AgentConfig
from opencode_py.tools import registry


def _tool_schemas() -> list[dict]:
    tools = []
    for t in registry.all_tools():
        schema = t.args_schema()
        schema.pop("title", None)
        tools.append({"name": t.name, "description": t.description, "input_schema": schema})
    return tools


def _build_llm(agent: AgentConfig):
    llm = build_chat_model(agent, settings)
    return llm.bind_tools(_tool_schemas())


def _build_plain_llm(agent: AgentConfig):
    return build_chat_model(agent, settings)


def _normalize_messages_for_llm(messages: list[BaseMessage], system_prompt: str) -> list[BaseMessage]:
    if not messages:
        return [SystemMessage(content=system_prompt)]
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    return [SystemMessage(content=system_prompt), *non_system]


def _agent_from_state(state: AgentState) -> AgentConfig:
    raw = state.get("agent")
    if isinstance(raw, dict):
        return AgentConfig.model_validate(raw)
    return AgentConfig()


def _ruleset_from_state(state: AgentState) -> Ruleset:
    raw = state.get("approved_ruleset")
    if isinstance(raw, list):
        try:
            return Ruleset.model_validate({"rules": raw})
        except Exception:
            return Ruleset()
    return Ruleset()


def _ruleset_to_state(ruleset: Ruleset) -> list[dict[str, str]]:
    return [
        {"permission": r.permission, "pattern": r.pattern, "action": r.action}
        for r in ruleset.rules
    ]


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _estimate_message_tokens_fallback(messages: list[BaseMessage]) -> int:
    chars = sum(len(_extract_text(getattr(m, "content", ""))) for m in messages)
    return (chars // 4) + max(1, len(messages) * 8)


def _estimate_message_tokens(messages: list[BaseMessage], agent: AgentConfig | None = None) -> int:
    agent = agent or AgentConfig()
    try:
        llm = _build_plain_llm(agent)
        estimator = getattr(llm, "get_num_tokens_from_messages", None)
        if callable(estimator):
            counted = estimator(messages)
            if isinstance(counted, int) and counted > 0:
                return counted
    except Exception:
        pass

    return _estimate_message_tokens_fallback(messages)


def _estimate_payload_tokens(
    prepared_messages: list[BaseMessage],
    agent: AgentConfig | None = None,
    include_tools: bool = True,
) -> int:
    estimated = _estimate_message_tokens(prepared_messages, agent)
    if include_tools:
        tools = _tool_schemas()
        try:
            tool_overhead = _estimate_message_tokens_fallback([HumanMessage(content=json.dumps(tools, ensure_ascii=False))])
        except Exception:
            tool_overhead = 0
        estimated += tool_overhead
    return max(1, int(estimated))


def _apply_runtime_calibration(estimated_tokens: int, state: AgentState) -> int:
    ratio = state.get("runtime_ctx_calibration_ratio", 1.0)
    try:
        ratio_f = float(ratio)
    except Exception:
        ratio_f = 1.0
    ratio_f = min(2.0, max(0.5, ratio_f))
    return max(1, int(estimated_tokens * ratio_f))


def _update_runtime_calibration(state: AgentState, observed_input_tokens: int, estimated_payload_tokens: int) -> dict:
    if observed_input_tokens <= 0 or estimated_payload_tokens <= 0:
        return {}

    observed_ratio = observed_input_tokens / max(1.0, float(estimated_payload_tokens))
    observed_ratio = min(2.0, max(0.5, observed_ratio))

    prev = state.get("runtime_ctx_calibration_ratio", 1.0)
    try:
        prev_f = float(prev)
    except Exception:
        prev_f = 1.0

    alpha = 0.2
    next_ratio = (1.0 - alpha) * prev_f + alpha * observed_ratio
    next_ratio = min(2.0, max(0.5, next_ratio))
    return {"runtime_ctx_calibration_ratio": next_ratio}


def _is_context_overflow(estimated_tokens: int) -> bool:
    if not settings.compaction_enabled:
        return False
    return estimated_tokens >= settings.compaction_trigger_tokens()


def _split_head_tail_messages(messages: list[BaseMessage], tail_turns: int) -> tuple[list[BaseMessage], list[BaseMessage], int]:
    if not messages:
        return [], [], 0

    user_indexes = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(user_indexes) <= tail_turns:
        return [], messages, 0

    split_idx = user_indexes[-tail_turns]
    return messages[:split_idx], messages[split_idx:], split_idx


def _visible_messages(state: AgentState) -> list[BaseMessage]:
    messages = state.get("messages", [])
    start = int(state.get("visible_start_index", 0) or 0)
    if start <= 0:
        return messages
    if start >= len(messages):
        return messages[-1:] if messages else []
    summary = state.get("last_compaction_summary")
    if summary:
        return [HumanMessage(content=f"[COMPACTION SUMMARY]\n{summary}"), *messages[start:]]
    return messages[start:]


def _build_compaction_prompt(head_messages: list[BaseMessage], previous_summary: str | None) -> str:
    lines: list[str] = []
    if previous_summary:
        lines.append("Previous summary:\n" + previous_summary)

    lines.append("Compress the conversation history below into a concise actionable summary.")
    lines.append("Keep: goals, constraints, decisions, completed work, pending tasks, errors.")
    lines.append("Return plain text only, no markdown heading.")

    for msg in head_messages:
        role = msg.type
        text = _extract_text(getattr(msg, "content", ""))
        if text:
            lines.append(f"[{role}] {text}")

    return "\n\n".join(lines)


async def _compact_with_llm(agent: AgentConfig, prompt: str) -> str:
    llm = _build_plain_llm(agent)
    response: AIMessage = await llm.ainvoke(
        [
            SystemMessage(content="You compress prior conversation context for an agent runtime."),
            HumanMessage(content=prompt),
        ]
    )
    text = _extract_text(response.content).strip()
    if len(text) > settings.compaction_max_summary_chars:
        text = text[: settings.compaction_max_summary_chars]
    return text


def build_graph(prompter: PermissionPrompter | None = None, checkpointer=None):
    prompter = prompter or CLIPrompter()

    async def prepare_input(state: AgentState) -> dict:
        return {
            "step_count": state.get("step_count", 0),
            "compaction_count": state.get("compaction_count", 0),
        }

    async def check_overflow(state: AgentState) -> dict:
        agent = _agent_from_state(state)
        visible = _visible_messages(state)
        prepared = _normalize_messages_for_llm(visible, agent.system_prompt)
        estimated_payload = _estimate_payload_tokens(prepared, agent, include_tools=True)
        calibrated = _apply_runtime_calibration(estimated_payload, state)
        overflow = _is_context_overflow(calibrated) or bool(state.get("force_compact", False))
        return {
            "estimated_payload_tokens": estimated_payload,
            "estimated_tokens": calibrated,
            "overflow": overflow,
        }

    def route_overflow(state: AgentState) -> Literal["compact_context", "llm_call"]:
        if state.get("overflow", False):
            return "compact_context"
        return "llm_call"

    async def compact_context(state: AgentState) -> dict:
        messages = state.get("messages", [])
        agent = _agent_from_state(state)
        summary_prev = state.get("last_compaction_summary")

        head, _, split_idx = _split_head_tail_messages(messages, settings.compaction_tail_turns)
        if not head:
            return {"overflow": False, "force_compact": False}

        prompt = _build_compaction_prompt(head, summary_prev)
        summary = await _compact_with_llm(agent, prompt)

        # Keep full history in storage/state; future LLM calls use visible window only.
        return {
            "last_compaction_summary": summary,
            "visible_start_index": split_idx,
            "compaction_count": state.get("compaction_count", 0) + 1,
            "overflow": False,
            "force_compact": False,
        }

    def route_after_compact(state: AgentState) -> Literal["llm_call", "end"]:
        if state.get("compact_only", False):
            return "end"
        return "llm_call"

    async def llm_call(state: AgentState) -> dict:
        agent = _agent_from_state(state)
        llm = _build_llm(agent)
        visible = _visible_messages(state)
        prepared = _normalize_messages_for_llm(visible, agent.system_prompt)
        ai: AIMessage = await llm.ainvoke(prepared)

        usage = getattr(ai, "usage_metadata", None) or {}
        observed_in = int(usage.get("input_tokens", 0) or usage.get("input_token_count", 0) or 0)
        estimated_payload = int(state.get("estimated_payload_tokens", 0) or 0)
        calibration_update = _update_runtime_calibration(state, observed_in, estimated_payload)

        return {
            "messages": [ai],
            "step_count": state.get("step_count", 0) + 1,
            **calibration_update,
        }

    def route_event(state: AgentState) -> dict:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return {"route": "exec_tools"}
        return {"route": "end"}

    def route_after_event(state: AgentState) -> Literal["exec_tools", "end"]:
        route = state.get("route", "end")
        if route == "exec_tools":
            return "exec_tools"
        return "end"

    async def exec_tools(state: AgentState) -> dict:
        last: AIMessage = state["messages"][-1]  # type: ignore[assignment]
        cwd = state.get("cwd") or "."
        approved = _ruleset_from_state(state)
        from opencode_py.tools.base import ToolContext

        new_messages: list = []
        new_rules: list[Rule] = list(approved.rules)

        for call in last.tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            tdef = registry.get(name)
            if tdef is None:
                new_messages.append(
                    ToolMessage(content=f"unknown tool: {name}", tool_call_id=call["id"])
                )
                continue

            pattern = tdef.pattern_from_args(args)
            current = Ruleset(rules=new_rules)
            decision = evaluate(tdef.permission, pattern, DEFAULT_RULESET, current)

            if decision == "ask":
                detail = json.dumps(args, ensure_ascii=False)[:200]
                reply = prompter.ask(tdef.permission, pattern, detail)
                if reply == "reject":
                    new_messages.append(
                        ToolMessage(content="permission denied by user", tool_call_id=call["id"])
                    )
                    continue
                if reply == "always":
                    new_rules.append(Rule(permission=tdef.permission, pattern=pattern, action="allow"))
            elif decision == "deny":
                new_messages.append(
                    ToolMessage(content=f"permission denied by ruleset ({tdef.permission}:{pattern})", tool_call_id=call["id"])
                )
                continue

            try:
                params = tdef.params_model.model_validate(args)
            except Exception as exc:
                new_messages.append(
                    ToolMessage(content=f"invalid arguments: {exc}", tool_call_id=call["id"])
                )
                continue

            ctx = ToolContext(cwd=cwd, session_id=state.get("session_id", "local"))
            try:
                result = await tdef.execute(params, ctx)
                content = result.output if result.ok else f"[error] {result.output}"
            except Exception as exc:
                content = f"[exception] {exc}"
            new_messages.append(ToolMessage(content=content, tool_call_id=call["id"]))

        return {
            "messages": new_messages,
            "approved_ruleset": _ruleset_to_state(Ruleset(rules=new_rules)),
        }

    def decide_next(state: AgentState) -> Literal["check_overflow", "end"]:
        agent = _agent_from_state(state)
        if state.get("step_count", 0) >= agent.max_steps:
            return "end"
        return "check_overflow"

    g: StateGraph = StateGraph(AgentState)
    g.add_node("prepare_input", prepare_input)
    g.add_node("check_overflow", check_overflow)
    g.add_node("compact_context", compact_context)
    g.add_node("llm_call", llm_call)
    g.add_node("route_event", route_event)
    g.add_node("exec_tools", exec_tools)

    g.add_edge(START, "prepare_input")
    g.add_edge("prepare_input", "check_overflow")
    g.add_conditional_edges("check_overflow", route_overflow, {"compact_context": "compact_context", "llm_call": "llm_call"})
    g.add_conditional_edges("compact_context", route_after_compact, {"llm_call": "llm_call", "end": END})
    g.add_edge("llm_call", "route_event")
    g.add_conditional_edges("route_event", route_after_event, {"exec_tools": "exec_tools", "end": END})
    g.add_conditional_edges("exec_tools", decide_next, {"check_overflow": "check_overflow", "end": END})

    return g.compile(checkpointer=checkpointer)


__all__ = [
    "build_graph",
    "AsyncSqliteSaver",
    "_normalize_messages_for_llm",
    "_agent_from_state",
    "_ruleset_from_state",
    "_ruleset_to_state",
    "_estimate_message_tokens",
    "_estimate_payload_tokens",
    "_apply_runtime_calibration",
    "_update_runtime_calibration",
    "_split_head_tail_messages",
]
