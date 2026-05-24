from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from opencode_py.agent.state import AgentState
from opencode_py.config import settings
from opencode_py.permission.prompt import CLIPrompter, PermissionPrompter
from opencode_py.permission.schema import DEFAULT_RULESET, Rule, Ruleset, evaluate
from opencode_py.providers import build_chat_model
from opencode_py.session.models import AgentConfig
from opencode_py.tools import registry


def _build_llm(agent: AgentConfig):
    llm = build_chat_model(agent, settings)
    tools = []
    for t in registry.all_tools():
        schema = t.args_schema()
        schema.pop("title", None)
        tools.append({"name": t.name, "description": t.description, "input_schema": schema})
    return llm.bind_tools(tools)


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


def build_graph(prompter: PermissionPrompter | None = None, checkpointer=None):
    prompter = prompter or CLIPrompter()

    async def prepare_input(state: AgentState) -> dict:
        return {"step_count": state.get("step_count", 0)}

    async def llm_call(state: AgentState) -> dict:
        agent = _agent_from_state(state)
        llm = _build_llm(agent)
        prepared = _normalize_messages_for_llm(state.get("messages", []), agent.system_prompt)
        ai: AIMessage = await llm.ainvoke(prepared)
        return {"messages": [ai], "step_count": state.get("step_count", 0) + 1}

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

            ctx = ToolContext(cwd=cwd, session_id="local")
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

    def decide_next(state: AgentState) -> Literal["llm_call", "end"]:
        agent = _agent_from_state(state)
        if state.get("step_count", 0) >= agent.max_steps:
            return "end"
        return "llm_call"

    g: StateGraph = StateGraph(AgentState)
    g.add_node("prepare_input", prepare_input)
    g.add_node("llm_call", llm_call)
    g.add_node("route_event", route_event)
    g.add_node("exec_tools", exec_tools)

    g.add_edge(START, "prepare_input")
    g.add_edge("prepare_input", "llm_call")
    g.add_edge("llm_call", "route_event")
    g.add_conditional_edges("route_event", route_after_event, {"exec_tools": "exec_tools", "end": END})
    g.add_conditional_edges("exec_tools", decide_next, {"llm_call": "llm_call", "end": END})

    return g.compile(checkpointer=checkpointer)


__all__ = ["build_graph", "AsyncSqliteSaver"]
