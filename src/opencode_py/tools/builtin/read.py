from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from opencode_py.tools.base import ToolContext, ToolDef, ToolResult

MAX_BYTES = 256_000


class Params(BaseModel):
    path: str = Field(description="Absolute or cwd-relative file path to read.")
    offset: int = Field(default=0, ge=0, description="Line offset (0-based).")
    limit: int | None = Field(default=None, description="Max lines to read; None = all.")


async def _execute(p: Params, ctx: ToolContext) -> ToolResult:
    full = (Path(ctx.cwd) / p.path).resolve() if not Path(p.path).is_absolute() else Path(p.path)
    if not full.exists():
        return ToolResult(ok=False, output=f"file not found: {full}")
    if full.is_dir():
        return ToolResult(ok=False, output=f"path is a directory: {full}")
    data = full.read_bytes()
    if len(data) > MAX_BYTES:
        data = data[:MAX_BYTES]
        truncated = True
    else:
        truncated = False
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if p.limit is not None:
        lines = lines[p.offset : p.offset + p.limit]
    elif p.offset:
        lines = lines[p.offset :]
    body = "\n".join(f"{i + p.offset + 1:>5}  {line}" for i, line in enumerate(lines))
    if truncated:
        body += f"\n... (truncated at {MAX_BYTES} bytes)"
    return ToolResult(output=body, metadata={"path": str(full), "lines": len(lines)})


tool = ToolDef(
    name="read",
    description="Read a file from the filesystem with line numbers.",
    params_model=Params,
    permission="read",
    pattern_from_args=lambda a: a.get("path", "*"),
    execute=_execute,  # type: ignore[arg-type]
)
