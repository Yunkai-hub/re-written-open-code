from __future__ import annotations

import asyncio
import shutil

from pydantic import BaseModel, Field

from opencode_py.tools.base import ToolContext, ToolDef, ToolResult

MAX_OUTPUT = 30_000
DEFAULT_TIMEOUT_S = 120


class Params(BaseModel):
    command: str = Field(description="Shell command to execute.")
    timeout: int = Field(default=DEFAULT_TIMEOUT_S, ge=1, le=600)


def _pick_shell() -> tuple[str, list[str]]:
    for candidate in ("bash", "C:\\Program Files\\Git\\bin\\bash.exe", "wsl"):
        path = shutil.which(candidate) if not candidate.startswith("C:") else candidate
        if path and (candidate.startswith("C:") or shutil.which(candidate)):
            return (path, ["-c"]) if candidate != "wsl" else (path, ["bash", "-c"])
    return ("cmd.exe", ["/c"])


async def _execute(p: Params, ctx: ToolContext) -> ToolResult:
    shell, prefix = _pick_shell()
    try:
        proc = await asyncio.create_subprocess_exec(
            shell,
            *prefix,
            p.command,
            cwd=ctx.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=p.timeout)
    except asyncio.TimeoutError:
        return ToolResult(ok=False, output=f"timeout after {p.timeout}s")
    text = stdout.decode("utf-8", errors="replace")
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n... (truncated at {MAX_OUTPUT} chars)"
    return ToolResult(
        ok=(proc.returncode == 0),
        output=text or "(no output)",
        metadata={"exit_code": proc.returncode, "shell": shell},
    )


tool = ToolDef(
    name="bash",
    description="Run a shell command. On Windows uses Git Bash / WSL when available, else cmd.exe.",
    params_model=Params,
    permission="bash",
    pattern_from_args=lambda a: (a.get("command", "") or "*").split()[0] if a.get("command") else "*",
    execute=_execute,  # type: ignore[arg-type]
)
