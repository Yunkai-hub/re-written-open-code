from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from opencode_py.agent.graph import (
    _agent_from_state,
    _normalize_messages_for_llm,
    _ruleset_from_state,
    _ruleset_to_state,
    build_graph,
)
from opencode_py.permission.schema import Rule, Ruleset


def test_graph_contains_route_event_node():
    g = build_graph()
    graph = g.get_graph()
    node_ids = {n.id for n in graph.nodes.values()}
    assert "route_event" in node_ids


def test_route_event_end_when_no_tool_calls():
    g = build_graph()
    state = {"messages": [AIMessage(content="hello", tool_calls=[])]}
    assert state["messages"][0].tool_calls == []


def test_normalize_messages_keeps_one_leading_system():
    messages = [
        SystemMessage(content="old-system"),
        HumanMessage(content="hello"),
        SystemMessage(content="late-system"),
        AIMessage(content="hi"),
    ]
    out = _normalize_messages_for_llm(messages, "canonical-system")
    assert isinstance(out[0], SystemMessage)
    assert out[0].content == "canonical-system"
    assert sum(1 for m in out if isinstance(m, SystemMessage)) == 1
    assert len(out) == 3


def test_agent_from_state_accepts_primitive_dict():
    state = {"agent": {"name": "default", "model": "x", "max_steps": 5, "system_prompt": "s"}}
    agent = _agent_from_state(state)
    assert agent.model == "x"
    assert agent.max_steps == 5


def test_ruleset_roundtrip_primitive_state():
    rs = Ruleset(rules=[Rule(permission="write", pattern="a.txt", action="allow")])
    primitive = _ruleset_to_state(rs)
    assert isinstance(primitive, list)
    back = _ruleset_from_state({"approved_ruleset": primitive})
    assert len(back.rules) == 1
    assert back.rules[0].permission == "write"
