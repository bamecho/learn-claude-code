import pytest
from unittest.mock import MagicMock
from src.tools.compact_tool import CompactTool
from src.tools.base import ToolResult
from src.agent.context import CompactState


class TestCompactTool:
    def test_auto_mode_below_threshold_returns_noop(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "auto"})
        assert "no compression needed" in result.content.lower() or "within" in result.content.lower()
        assert not result.is_error

    def test_force_mode_compresses(self):
        messages = [
            {"role": "user", "content": "old user msg"},
            {"role": "assistant", "content": "old assistant msg"},
            {"role": "user", "content": "recent user msg"},
            {"role": "assistant", "content": "recent assistant msg"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary: user said hello.")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert not result.is_error
        assert len(messages) == 2  # summary + recent
        assert messages[0]["role"] == "assistant"
        assert "Summary" in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert compact_state.last_summary == "Summary: user said hello."

    def test_provider_failure_returns_error(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.side_effect = RuntimeError("network down")
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert result.is_error
        assert "network down" in result.content
        assert not compact_state.has_compacted

    def test_keep_last_assistant_equal_to_total_returns_noop(self):
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert "no old history" in result.content.lower()
