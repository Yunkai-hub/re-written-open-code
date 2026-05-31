import json

from opencode_py.mcp.loader import load_mcp_config


def test_load_mcp_config(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": {
                    "fs": {
                        "enabled": True,
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "x"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_mcp_config(cfg_file)
    assert cfg.version == 1
    assert "fs" in cfg.servers
