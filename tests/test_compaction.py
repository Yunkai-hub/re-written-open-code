from langchain_core.messages import AIMessage, HumanMessage

from opencode_py.agent.graph import _split_head_tail_messages


def test_split_head_tail_keeps_recent_turns():
    messages = [
        HumanMessage(content="u1"),
        AIMessage(content="a1"),
        HumanMessage(content="u2"),
        AIMessage(content="a2"),
        HumanMessage(content="u3"),
        AIMessage(content="a3"),
    ]
    head, tail, split_idx = _split_head_tail_messages(messages, tail_turns=2)
    assert split_idx == 2
    assert len(head) == 2
    assert len(tail) == 4
    assert isinstance(tail[0], HumanMessage)
    assert tail[0].content == "u2"
