from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from opencode_py.tools.base import ToolContext, ToolDef, ToolResult


class Params(BaseModel):
    path: str = Field(description="File path (absolute or cwd-relative).")
    old_string: str = Field(description="Exact text to replace. Must be unique unless replace_all.")
    new_string: str = Field(description="Replacement text.")
    replace_all: bool = Field(default=False)


async def _execute(p: Params, ctx: ToolContext) -> ToolResult:
    full = (Path(ctx.cwd) / p.path).resolve() if not Path(p.path).is_absolute() else Path(p.path)
    if not full.exists():
        return ToolResult(ok=False, output=f"file not found: {full}")
    original = full.read_text(encoding="utf-8")
    count = original.count(p.old_string)
    if count == 0:
        return ToolResult(ok=False, output="old_string not found in file")
    if count > 1 and not p.replace_all:
        return ToolResult(ok=False, output=f"old_string occurs {count} times; pass replace_all=true or add context")
    updated = original.replace(p.old_string, p.new_string) if p.replace_all else original.replace(p.old_string, p.new_string, 1)
    full.write_text(updated, encoding="utf-8")
    return ToolResult(output=f"edited {full} ({count if p.replace_all else 1} replacement(s))")


tool = ToolDef(
    name="edit",
    description="Replace an exact substring in a file. Use replace_all for multiple occurrences.",
    params_model=Params,
    permission="edit",
    pattern_from_args=lambda a: a.get("path", "*"),
    execute=_execute,  # type: ignore[arg-type]
)
