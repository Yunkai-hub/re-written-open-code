from opencode_py.permission.schema import DEFAULT_RULESET, Rule, Ruleset, evaluate


def test_default_ruleset_basics():
    assert evaluate("read", "any.txt", DEFAULT_RULESET) == "allow"
    assert evaluate("glob", "**/*.py", DEFAULT_RULESET) == "allow"
    assert evaluate("write", "a.txt", DEFAULT_RULESET) == "ask"


def test_rightmost_rule_wins():
    base = Ruleset(rules=[Rule(permission="write", pattern="*", action="ask")])
    override = Ruleset(rules=[Rule(permission="write", pattern="file.txt", action="allow")])
    assert evaluate("write", "file.txt", base, override) == "allow"


def test_deny_overrides_when_last():
    rs1 = Ruleset(rules=[Rule(permission="bash", pattern="*", action="allow")])
    rs2 = Ruleset(rules=[Rule(permission="bash", pattern="rm", action="deny")])
    assert evaluate("bash", "rm", rs1, rs2) == "deny"
