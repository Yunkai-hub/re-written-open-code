from __future__ import annotations

from opencode_py.tools.base import ToolDef
from opencode_py.tools.builtin import bash, edit, glob_tool, read, write

_TOOLS: dict[str, ToolDef] = {
    t.name: t
    for t in (
        read.tool,
        write.tool,
        edit.tool,
        glob_tool.tool,
        bash.tool,
    )
}


def all_tools() -> list[ToolDef]:
    return list(_TOOLS.values())


def get(name: str) -> ToolDef | None:
    return _TOOLS.get(name)


def to_anthropic_schema() -> list[dict]:
    out = []
    for t in all_tools():
        schema = t.args_schema()
        schema.pop("title", None)
        out.append(
            {
                "name": t.name,
                "description": t.description,
                "input_schema": schema,
            }
        )
    return out
