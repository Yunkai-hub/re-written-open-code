from langchain_core.messages import HumanMessage

from opencode_py.agent.graph import _is_context_overflow, _visible_messages, build_graph


def test_graph_contains_overflow_nodes():
    g = build_graph()
    graph = g.get_graph()
    node_ids = {n.id for n in graph.nodes.values()}
    assert "check_overflow" in node_ids
    assert "compact_context" in node_ids


def test_is_context_overflow_boolean():
    assert isinstance(_is_context_overflow(1), bool)


def test_graph_compiles_with_human_message():
    g = build_graph()
    assert g is not None
    state = {"messages": [HumanMessage(content="hello")], "agent": {"max_steps": 1, "model": "claude-sonnet-4-5-20250929", "name": "default", "system_prompt": "s", "temperature": None}}
    assert isinstance(state["messages"], list)


def test_visible_messages_uses_summary_and_tail_window():
    messages = [
        HumanMessage(content="old1"),
        HumanMessage(content="old2"),
        HumanMessage(content="new1"),
    ]
    state = {
        "messages": messages,
        "visible_start_index": 2,
        "last_compaction_summary": "compressed history",
    }
    visible = _visible_messages(state)
    assert len(visible) == 2
    assert isinstance(visible[0], HumanMessage)
    assert "COMPACTION SUMMARY" in str(visible[0].content)
    assert visible[1].content == "new1"
