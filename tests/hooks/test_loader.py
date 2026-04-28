from pathlib import Path

from src.hooks.loader import load_hooks


class TestLoadHooks:
    def test_missing_config_returns_empty(self, tmp_path):
        result = load_hooks(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text("not json")
        result = load_hooks(str(config))
        assert result == {}

    def test_non_dict_config_returns_empty(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text("[1, 2, 3]")
        result = load_hooks(str(config))
        assert result == {}

    def test_load_single_hook(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text(
            '{"hooks": {"PreToolUse": [{"command": "echo test", "matcher": "*"}]}}'
        )
        result = load_hooks(str(config))
        assert "PreToolUse" in result
        assert len(result["PreToolUse"]) == 1
        assert result["PreToolUse"][0]["command"] == "echo test"
        assert result["PreToolUse"][0]["matcher"] == "*"

    def test_missing_hooks_key_returns_empty(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text('{"other": []}')
        result = load_hooks(str(config))
        assert result == {}

    def test_non_list_event_value_skipped(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text('{"hooks": {"PreToolUse": "not a list"}}')
        result = load_hooks(str(config))
        assert result == {}

    def test_multiple_events(self, tmp_path):
        config = tmp_path / ".hooks.json"
        config.write_text(
            '{"hooks": {"SessionStart": [{"command": "echo start"}], '
            '"PreToolUse": [{"command": "echo pre"}], '
            '"PostToolUse": [{"command": "echo post"}]}}'
        )
        result = load_hooks(str(config))
        assert set(result.keys()) == {"SessionStart", "PreToolUse", "PostToolUse"}
        assert len(result["SessionStart"]) == 1
        assert len(result["PreToolUse"]) == 1
        assert len(result["PostToolUse"]) == 1

    def test_uses_default_config_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = tmp_path / ".hooks.json"
        config.write_text(
            '{"hooks": {"PreToolUse": [{"command": "echo default"}]}}'
        )
        result = load_hooks()
        assert "PreToolUse" in result
