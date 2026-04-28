import pytest
from src.permissions.engine import PermissionEngine, PermissionRule


class TestDenyRules:
    def test_deny_rule_blocks_tool(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="deny")])
        result = engine.check("bash", {"command": "ls"})
        assert result["behavior"] == "deny"
        assert "matched deny rule" in result["reason"]

    def test_deny_rule_does_not_affect_other_tools(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="deny")])
        result = engine.check("read_file", {"filePath": "foo.py"})
        assert result["behavior"] == "ask"

    def test_deny_rule_matches_path(self):
        engine = PermissionEngine(
            rules=[PermissionRule(tool="read_file", behavior="deny", path="*secret*")]
        )
        assert engine.check("read_file", {"filePath": "secret.txt"})["behavior"] == "deny"
        assert engine.check("read_file", {"filePath": "public.txt"})["behavior"] == "ask"

    def test_deny_rule_matches_content(self):
        engine = PermissionEngine(
            rules=[PermissionRule(tool="write_file", behavior="deny", content="*password*")]
        )
        assert engine.check("write_file", {"filePath": "x", "content": "my password"})["behavior"] == "deny"
        assert engine.check("write_file", {"filePath": "x", "content": "hello"})["behavior"] == "ask"


class TestAllowRules:
    def test_allow_rule_permits_tool(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="allow")])
        result = engine.check("bash", {"command": "ls"})
        assert result["behavior"] == "allow"
        assert "matched allow rule" in result["reason"]

    def test_allow_rule_comes_after_mode(self):
        engine = PermissionEngine(
            mode="plan",
            rules=[PermissionRule(tool="write_file", behavior="allow")],
        )
        result = engine.check("write_file", {"filePath": "x", "content": "y"})
        assert result["behavior"] == "allow"


class TestAskRules:
    def test_ask_rule_matches_before_fallback(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="ask")])
        result = engine.check("bash", {"command": "ls"})
        assert result["behavior"] == "ask"
        assert "matched ask rule" in result["reason"]


class TestModes:
    def test_plan_mode_blocks_writes(self):
        engine = PermissionEngine(mode="plan")
        assert engine.check("write_file", {"filePath": "x", "content": "y"})["behavior"] == "deny"
        assert engine.check("edit_file", {"filePath": "x", "oldText": "a", "newText": "b"})["behavior"] == "deny"
        assert engine.check("bash", {"command": "ls"})["behavior"] == "deny"

    def test_plan_mode_allows_reads(self):
        engine = PermissionEngine(mode="plan")
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "allow"

    def test_auto_mode_allows_reads(self):
        engine = PermissionEngine(mode="auto")
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "allow"

    def test_auto_mode_falls_back_for_writes(self):
        engine = PermissionEngine(mode="auto")
        assert engine.check("write_file", {"filePath": "x", "content": "y"})["behavior"] == "ask"

    def test_default_mode_asks_for_everything(self):
        engine = PermissionEngine(mode="default")
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "ask"
        assert engine.check("bash", {"command": "ls"})["behavior"] == "ask"


class TestPriority:
    def test_deny_overrides_allow(self):
        engine = PermissionEngine(
            rules=[
                PermissionRule(tool="bash", behavior="deny"),
                PermissionRule(tool="bash", behavior="allow"),
            ]
        )
        assert engine.check("bash", {"command": "ls"})["behavior"] == "deny"

    def test_deny_overrides_plan(self):
        engine = PermissionEngine(
            mode="plan",
            rules=[PermissionRule(tool="write_file", behavior="deny")],
        )
        result = engine.check("write_file", {"filePath": "x", "content": "y"})
        assert result["behavior"] == "deny"
        assert "deny rule" in result["reason"]

    def test_mode_overrides_fallback(self):
        engine = PermissionEngine(mode="auto")
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "allow"

    def test_allow_overrides_mode(self):
        engine = PermissionEngine(
            mode="plan",
            rules=[PermissionRule(tool="write_file", behavior="allow")],
        )
        assert engine.check("write_file", {"filePath": "x", "content": "y"})["behavior"] == "allow"


class TestBashValidator:
    def test_severe_pattern_denies(self):
        engine = PermissionEngine()
        result = engine.check("bash", {"command": "sudo apt-get update"})
        assert result["behavior"] == "deny"
        assert "Bash validator" in result["reason"]

    def test_rm_rf_denies(self):
        engine = PermissionEngine()
        result = engine.check("bash", {"command": "rm -rf /some/path"})
        assert result["behavior"] == "deny"

    def test_non_severe_asks(self):
        engine = PermissionEngine()
        result = engine.check("bash", {"command": "echo $(date)"})
        assert result["behavior"] == "ask"
        assert "Bash validator flagged" in result["reason"]

    def test_safe_bash_continues_to_rules(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="allow")])
        result = engine.check("bash", {"command": "ls -la"})
        assert result["behavior"] == "allow"


class TestFnmatch:
    def test_tool_wildcard(self):
        engine = PermissionEngine(rules=[PermissionRule(tool="*", behavior="allow")])
        assert engine.check("bash", {"command": "ls"})["behavior"] == "allow"
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "allow"

    def test_path_glob(self):
        engine = PermissionEngine(
            rules=[PermissionRule(tool="read_file", behavior="deny", path="*.secret")]
        )
        assert engine.check("read_file", {"filePath": "foo.secret"})["behavior"] == "deny"
        assert engine.check("read_file", {"filePath": "foo.txt"})["behavior"] == "ask"

    def test_content_glob(self):
        engine = PermissionEngine(
            rules=[PermissionRule(tool="bash", behavior="deny", content="rm -rf *")]
        )
        assert engine.check("bash", {"command": "rm -rf /tmp"})["behavior"] == "deny"
        assert engine.check("bash", {"command": "ls"})["behavior"] == "ask"


class TestPlanModeSemantics:
    def test_plan_auto_allows_unknown_non_write(self):
        engine = PermissionEngine(mode="plan")
        assert engine.check("unknown_tool", {})["behavior"] == "allow"

    def test_plan_auto_allows_read(self):
        engine = PermissionEngine(mode="plan")
        assert engine.check("read_file", {"filePath": "x"})["behavior"] == "allow"


class TestEngineState:
    def test_add_allow_rule(self):
        engine = PermissionEngine()
        assert engine.check("bash", {"command": "ls"})["behavior"] == "ask"
        engine.add_allow_rule("bash")
        assert engine.check("bash", {"command": "ls"})["behavior"] == "allow"

    def test_consecutive_denials(self):
        engine = PermissionEngine()
        assert engine.consecutive_denials == 0
        engine.record_denial()
        assert engine.consecutive_denials == 1
        engine.record_denial()
        engine.record_denial()
        assert engine.consecutive_denials == 3
