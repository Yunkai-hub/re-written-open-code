from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from opencode_py.tools.base import ToolContext, ToolDef, ToolResult


class Params(BaseModel):
    path: str = Field(description="File path (absolute or cwd-relative).")
    content: str = Field(description="Full file contents to write.")


async def _execute(p: Params, ctx: ToolContext) -> ToolResult:
    full = (Path(ctx.cwd) / p.path).resolve() if not Path(p.path).is_absolute() else Path(p.path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(p.content, encoding="utf-8")
    return ToolResult(output=f"wrote {len(p.content)} bytes to {full}", metadata={"path": str(full)})


tool = ToolDef(
    name="write",
    description="Write (or overwrite) a file with the given content.",
    params_model=Params,
    permission="write",
    pattern_from_args=lambda a: a.get("path", "*"),
    execute=_execute,  # type: ignore[arg-type]
)
