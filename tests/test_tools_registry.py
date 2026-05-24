from opencode_py.tools import registry


def test_registry_contains_phase1_tools():
    names = {t.name for t in registry.all_tools()}
    assert {"read", "write", "edit", "glob", "bash"}.issubset(names)


def test_registry_get_known_and_unknown():
    assert registry.get("read") is not None
    assert registry.get("missing_tool") is None
