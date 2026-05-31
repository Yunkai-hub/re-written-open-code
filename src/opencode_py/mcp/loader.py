from __future__ import annotations

import json
from pathlib import Path

from opencode_py.mcp.schema import MCPConfig


def load_mcp_config(path: str | Path) -> MCPConfig:
    raw = Path(path)
    data = json.loads(raw.read_text(encoding="utf-8"))
    return MCPConfig.model_validate(data)
