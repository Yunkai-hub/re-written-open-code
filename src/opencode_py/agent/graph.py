from __future__ import annotations

import json
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from opencode_py.agent.state import AgentState
from opencode_py.config import settings
from opencode_py.permission.prompt import CLIPrompter, PermissionPrompter
from opencode_py.permission.schema import DEFAULT_RULESET, Rule, Ruleset, evaluate
from opencode_py.session.models import AgentConfig
from opencode_py.tools import registry


def _build_llm(agent: AgentConfig):
    tools = []
    for t in registry.all_tools():
        schema = t.args_schema()
        schema.pop("title", None)
        tools.append({"name": t.name, "description": t.description, "input_schema": schema})
    llm = ChatAnthropic(
        model_name=agent.model,
        api_key=settings.anthropic_api_key,
        temperature=agent.temperature if agent.temperature is not None else 1.0,
        max_tokens_to_sample=4096,
        timeout=120,
        stop=None,
    )
    return llm.bind_tools(tools)


def build_graph(prompter: PermissionPrompter | None = None, checkpointer=None):
    prompter = prompter or CLIPrompter()

    async def prepare_input(state: AgentState) -> dict:
        msgs = state.get("messages", [])
        if not msgs or not isinstance(msgs[0], SystemMessage):
            agent = state.get("agent") or AgentConfig()
            sys = SystemMessage(content=agent.system_prompt)
            return {"messages": [sys] + msgs, "step_count": 0}
        return {"step_count": state.get("step_count", 0)}

    async def llm_call(state: AgentState) -> dict:
        agent = state.get("agent") or AgentConfig()
        llm = _build_llm(agent)
        ai: AIMessage = await llm.ainvoke(state["messages"])
        return {"messages": [ai], "step_count": state.get("step_count", 0) + 1}

    def route_after_llm(state: AgentState) -> Literal["exec_tools", "end"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "exec_tools"
        return "end"

    async def exec_tools(state: AgentState) -> dict:
        last: AIMessage = state["messages"][-1]  # type: ignore[assignment]
        cwd = state.get("cwd") or "."
        approved = state.get("approved_ruleset") or Ruleset()
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

        return {"messages": new_messages, "approved_ruleset": Ruleset(rules=new_rules)}

    def decide_next(state: AgentState) -> Literal["llm_call", "end"]:
        agent = state.get("agent") or AgentConfig()
        if state.get("step_count", 0) >= agent.max_steps:
            return "end"
        return "llm_call"

    g: StateGraph = StateGraph(AgentState)
    g.add_node("prepare_input", prepare_input)
    g.add_node("llm_call", llm_call)
    g.add_node("exec_tools", exec_tools)

    g.add_edge(START, "prepare_input")
    g.add_edge("prepare_input", "llm_call")
    g.add_conditional_edges("llm_call", route_after_llm, {"exec_tools": "exec_tools", "end": END})
    g.add_conditional_edges("exec_tools", decide_next, {"llm_call": "llm_call", "end": END})

    return g.compile(checkpointer=checkpointer)


__all__ = ["build_graph", "AsyncSqliteSaver"]
