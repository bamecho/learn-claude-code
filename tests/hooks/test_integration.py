import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.agent import Agent
from src.hooks.runner import HookRunner
from src.provider.base import ContentBlock, LLMResponse
from src.tools.base import ToolRegistry, ToolResult


class TestHookIntegration:
    def _write_config(self, tmp_path: Path, data: dict) -> Path:
        config = tmp_path / ".hooks.json"
        config.write_text(json.dumps({"hooks": data}))
        return config

    def _make_agent(self, tmp_path: Path, hook_config: dict | None = None) -> Agent:
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="done")
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="mock_tool", input={})],
            stop_reason="tool_use",
        )

        if hook_config is not None:
            self._write_config(tmp_path, hook_config)
            runner = HookRunner(
                config_path=tmp_path / ".hooks.json",
                workdir=tmp_path,
                sdk_mode=True,
            )
        else:
            runner = None

        return Agent(provider, registry, hook_runner=runner)

    def test_pre_tool_use_blocks_execution(self, tmp_path):
        agent = self._make_agent(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'no' >&2; exit 1", "matcher": "*"}]},
        )
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[-1]
        assert tool_result_msg["role"] == "user"
        block = tool_result_msg["content"][0]
        assert block["type"] == "tool_result"
        assert block["is_error"] is True
        assert "blocked" in block["content"].lower()
        # Tool should not have been executed
        agent.registry.get("mock_tool").execute.assert_not_called()

    def test_pre_tool_use_inject_then_execute(self, tmp_path):
        agent = self._make_agent(
            tmp_path,
            {"PreToolUse": [{"command": "echo 'inject before run' >&2; exit 2", "matcher": "*"}]},
        )
        agent._run_turn("run", max_turns=1)

        # Injected message should be in tool_result_blocks, not user messages
        tool_result_msg = agent.messages[-1]
        assert tool_result_msg["role"] == "user"
        blocks = tool_result_msg["content"]
        # First block is the injected message as a tool_result
        assert blocks[0]["type"] == "tool_result"
        assert "inject before run" in blocks[0]["content"]
        # Second block is the actual tool result
        assert blocks[1]["type"] == "tool_result"
        assert blocks[1]["content"] == "done"
        # Tool was executed
        agent.registry.get("mock_tool").execute.assert_called_once()

    def test_post_tool_use_inject_appends_note(self, tmp_path):
        agent = self._make_agent(
            tmp_path,
            {"PostToolUse": [{"command": "echo 'post note' >&2; exit 2", "matcher": "*"}]},
        )
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[-1]
        assert tool_result_msg["role"] == "user"
        block = tool_result_msg["content"][0]
        assert block["type"] == "tool_result"
        assert "post note" in block["content"]

    def test_pre_tool_use_updated_input(self, tmp_path):
        agent = self._make_agent(
            tmp_path,
            {"PreToolUse": [
                {"command": 'echo \'{"updatedInput": {"arg": "modified"}}\'', "matcher": "*"}
            ]},
        )
        # Mock provider to return tool_use with some input
        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="mock_tool", input={"arg": "original"})],
            stop_reason="tool_use",
        )
        agent.provider = provider
        agent._run_turn("run", max_turns=1)

        # Tool should have been called with modified input
        agent.registry.get("mock_tool").execute.assert_called_once()
        call_args = agent.registry.get("mock_tool").execute.call_args
        assert call_args[0][1] == {"arg": "modified"}

    def test_no_hook_runner_no_change(self, tmp_path):
        agent = self._make_agent(tmp_path, None)
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[-1]
        assert tool_result_msg["role"] == "user"
        block = tool_result_msg["content"][0]
        assert block["content"] == "done"

    def test_session_start_in_run_interactive(self, tmp_path):
        registry = ToolRegistry()
        provider = MagicMock()
        self._write_config(
            tmp_path,
            {"SessionStart": [{"command": "echo 'session start' >&2; exit 2"}]},
        )
        runner = HookRunner(
            config_path=tmp_path / ".hooks.json",
            workdir=tmp_path,
            sdk_mode=True,
        )
        agent = Agent(provider, registry, hook_runner=runner)
        with patch("builtins.input", return_value="exit"):
            with patch("builtins.print"):
                agent.run_interactive()

        # SessionStart hook should have run; method completes without error.
        assert agent.hook_runner is not None
