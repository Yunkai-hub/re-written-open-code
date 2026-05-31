import json
import sys


def make_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def make_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            req = json.loads(raw)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "initialize":
            resp = make_result(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            )
        elif method == "tools/list":
            resp = make_result(
                req_id,
                {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo input text",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                            },
                        }
                    ]
                },
            )
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "echo":
                text = str(args.get("text", ""))
                resp = make_result(
                    req_id,
                    {"content": [{"type": "text", "text": f"echo:{text}"}]},
                )
            else:
                resp = make_error(req_id, -32601, f"unknown tool: {name}")
        else:
            resp = make_error(req_id, -32601, f"method not found: {method}")

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
