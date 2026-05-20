from __future__ import annotations

from typing import Literal, Protocol

Decision = Literal["once", "always", "reject"]


class PermissionPrompter(Protocol):
    def ask(self, permission: str, pattern: str, detail: str) -> Decision: ...


class CLIPrompter:
    """Synchronous terminal prompter. Used outside LangGraph interrupt flow for MVP."""

    def ask(self, permission: str, pattern: str, detail: str) -> Decision:
        print(f"\n[permission] {permission}: {pattern}")
        if detail:
            print(f"  detail: {detail}")
        while True:
            choice = input("  allow (o)nce / (a)lways / (r)eject? ").strip().lower()
            if choice in ("o", "once", ""):
                return "once"
            if choice in ("a", "always"):
                return "always"
            if choice in ("r", "reject", "n", "no"):
                return "reject"
