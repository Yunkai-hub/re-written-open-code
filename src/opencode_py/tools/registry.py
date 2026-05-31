from __future__ import annotations

from opencode_py.tools.base import ToolDef
from opencode_py.tools.builtin import bash, edit, glob_tool, read, write

_BUILTIN_TOOLS: dict[str, ToolDef] = {
    t.name: t
    for t in (
        read.tool,
        write.tool,
        edit.tool,
        glob_tool.tool,
        bash.tool,
    )
}
_DYNAMIC_TOOLS: dict[str, ToolDef] = {}


def register(tool: ToolDef, *, dynamic: bool = True) -> None:
    if dynamic:
        _DYNAMIC_TOOLS[tool.name] = tool
    else:
        _BUILTIN_TOOLS[tool.name] = tool


def register_many(tools: list[ToolDef], *, dynamic: bool = True) -> None:
    for t in tools:
        register(t, dynamic=dynamic)


def clear_dynamic() -> None:
    _DYNAMIC_TOOLS.clear()


def all_tools() -> list[ToolDef]:
    merged = dict(_BUILTIN_TOOLS)
    merged.update(_DYNAMIC_TOOLS)
    return list(merged.values())


def get(name: str) -> ToolDef | None:
    if name in _DYNAMIC_TOOLS:
        return _DYNAMIC_TOOLS[name]
    return _BUILTIN_TOOLS.get(name)


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
