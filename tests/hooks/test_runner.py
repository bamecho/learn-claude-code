import json
from pathlib import Path

from src.hooks.runner import HookRunner


class TestHookRunner:
    def _write_config(self, tmp_path: Path, data: dict) -> Path:
        config = tmp_path / ".hooks.json"
        config.write_text(json.dumps({"hooks": data}))
        return config

    def _trust(self, tmp_path: Path) -> None:
        trust_dir = tmp_path / ".claude"
        trust_dir.mkdir(parents=True, exist_ok=True)
        (trust_dir / ".claude_trusted").touch()

    def test_no_handlers_returns_empty_result(self, tmp_path):
        self._write_config(tmp_path, {})
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result == {
            "blocked": False,
            "messages": [],
            "block_reason": "",
            "permission_override": None,
        }

    def test_untrusted_workspace_returns_empty(self, tmp_path):
        self._write_config(tmp_path, {"PreToolUse": [{"command": "echo test"}]})
        # No trust marker
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["messages"] == []

    def test_sdk_mode_bypasses_trust(self, tmp_path):
        self._write_config(tmp_path, {"PreToolUse": [{"command": "echo hello"}]})
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path, sdk_mode=True)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        # Should execute even without trust marker
        assert result["messages"] == []

    def test_exit_0_continue(self, tmp_path):
        self._write_config(tmp_path, {"PreToolUse": [{"command": "echo ok"}]})
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["blocked"] is False
        assert result["messages"] == []

    def test_exit_0_json_stdout_additional_context(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": 'echo \'{"additionalContext": "note"}\''}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["messages"] == ["note"]

    def test_exit_0_json_stdout_updated_input(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": 'echo \'{"updatedInput": {"command": "ls"}}\''}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        ctx = {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}
        result = runner.run("PreToolUse", ctx)
        assert ctx["tool_input"] == {"command": "ls"}
        assert result["blocked"] is False

    def test_exit_0_json_stdout_permission_override(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": 'echo \'{"permissionDecision": "allow"}\''}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["permission_override"] == "allow"

    def test_exit_1_blocks(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'no way' >&2; exit 1"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["blocked"] is True
        assert result["block_reason"] == "no way"

    def test_exit_1_no_stderr_uses_default_reason(self, tmp_path):
        self._write_config(tmp_path, {"PreToolUse": [{"command": "exit 1"}]})
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["blocked"] is True
        assert result["block_reason"] == "Blocked by hook"

    def test_exit_2_injects_message(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'inject this' >&2; exit 2"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        assert result["blocked"] is False
        assert result["messages"] == ["inject this"]

    def test_matcher_filters_by_tool_name(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [
                {"command": "echo 'for bash' >&2; exit 1", "matcher": "bash"},
                {"command": "echo 'for all' >&2; exit 1", "matcher": "*"},
            ]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        # Should match the wildcard, not the bash-specific one
        result = runner.run("PreToolUse", {"tool_name": "read_file"})
        assert result["blocked"] is True
        assert result["block_reason"] == "for all"

    def test_matcher_star_matches_all(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'blocked' >&2; exit 1", "matcher": "*"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "anything"})
        assert result["blocked"] is True

    def test_matcher_skips_non_matching(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'blocked' >&2; exit 1", "matcher": "bash"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "read_file"})
        assert result["blocked"] is False

    def test_env_vars_passed(self, tmp_path):
        script = tmp_path / "check_env.sh"
        script.write_text(
            '#!/bin/sh\n'
            'echo "$HOOK_EVENT,$HOOK_TOOL_NAME"\n'
        )
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": f"sh {script}"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash", "tool_input": {"command": "ls"}})
        assert result["blocked"] is False

    def test_expanded_tool_env_vars_passed(self, tmp_path):
        script = tmp_path / "check_expanded_env.sh"
        script.write_text(
            '#!/bin/sh\n'
            'test "$HOOK_TOOL_COMMAND" = "ls -la" || exit 1\n'
            'test "$HOOK_FILE_PATH" = ".env" || exit 1\n'
        )
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": f"sh {script}"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run(
            "PreToolUse",
            {"tool_name": "bash", "tool_input": {"command": "ls -la", "filePath": ".env"}},
        )
        assert result["blocked"] is False

    def test_exit_0_stderr_is_displayed(self, tmp_path, capsys):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'visible status' >&2"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        captured = capsys.readouterr()
        assert result["blocked"] is False
        assert "[hook:PreToolUse] stderr: visible status" in captured.out

    def test_post_tool_use_gets_tool_output(self, tmp_path):
        script = tmp_path / "check_output.sh"
        script.write_text(
            '#!/bin/sh\n'
            'echo "$HOOK_TOOL_OUTPUT"\n'
        )
        self._write_config(
            tmp_path,
            {"PostToolUse": [{"command": f"sh {script}"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PostToolUse", {"tool_name": "bash", "tool_input": {}, "tool_output": "hello"})
        assert result["blocked"] is False

    def test_timeout_is_handled(self, tmp_path):
        self._write_config(
            tmp_path,
            {"PreToolUse": [{"command": "sleep 60"}]},
        )
        self._trust(tmp_path)
        runner = HookRunner(config_path=tmp_path / ".hooks.json", workdir=tmp_path)
        result = runner.run("PreToolUse", {"tool_name": "bash"})
        # Timeout should not crash; returns empty result
        assert result["blocked"] is False
        assert result["messages"] == []
