from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from opencode_py.tools.base import ToolContext, ToolDef, ToolResult

MAX_HITS = 200


class Params(BaseModel):
    pattern: str = Field(description="Glob pattern, e.g. '**/*.py'.")
    path: str | None = Field(default=None, description="Directory to search; defaults to cwd.")


async def _execute(p: Params, ctx: ToolContext) -> ToolResult:
    root = Path(p.path) if p.path else Path(ctx.cwd)
    if not root.is_absolute():
        root = (Path(ctx.cwd) / root).resolve()
    hits = []
    for path in root.glob(p.pattern):
        hits.append(str(path))
        if len(hits) >= MAX_HITS:
            break
    hits.sort()
    out = "\n".join(hits) if hits else "(no matches)"
    if len(hits) >= MAX_HITS:
        out += f"\n... (truncated at {MAX_HITS} hits)"
    return ToolResult(output=out, metadata={"count": len(hits)})


tool = ToolDef(
    name="glob",
    description="Find files matching a glob pattern.",
    params_model=Params,
    permission="glob",
    pattern_from_args=lambda a: a.get("pattern", "*"),
    execute=_execute,  # type: ignore[arg-type]
)
