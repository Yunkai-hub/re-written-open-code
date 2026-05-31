from __future__ import annotations

import fnmatch
from typing import Literal

from pydantic import BaseModel

Action = Literal["allow", "deny", "ask"]


class Rule(BaseModel):
    permission: str
    pattern: str = "*"
    action: Action


class Ruleset(BaseModel):
    rules: list[Rule] = []

    def extend(self, *more: "Ruleset") -> "Ruleset":
        out = list(self.rules)
        for m in more:
            out.extend(m.rules)
        return Ruleset(rules=out)


def evaluate(permission: str, pattern: str, *rulesets: Ruleset) -> Action:
    """Greedy-rightmost: scan all rules, last match wins. Default = ask."""
    decision: Action = "ask"
    for rs in rulesets:
        for rule in rs.rules:
            if rule.permission != permission and rule.permission != "*":
                continue
            if fnmatch.fnmatch(pattern, rule.pattern):
                decision = rule.action
    return decision


DEFAULT_RULESET = Ruleset(
    rules=[
        Rule(permission="read", pattern="*", action="allow"),
        Rule(permission="glob", pattern="*", action="allow"),
        Rule(permission="write", pattern="*", action="ask"),
        Rule(permission="edit", pattern="*", action="ask"),
        Rule(permission="bash", pattern="*", action="ask"),
        Rule(permission="mcp", pattern="*", action="ask"),
    ]
)
