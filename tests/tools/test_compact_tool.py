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
        assert result.content == "Current context is within the safe threshold; no compression needed."
        assert not result.is_error

    def test_auto_mode_above_threshold_compresses(self):
        long_content = "x" * 32000
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": "old assistant msg"},
            {"role": "user", "content": "recent user msg"},
            {"role": "assistant", "content": "recent assistant msg"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary: long conversation.")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "auto", "keep_last_assistant": 1})
        assert not result.is_error
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert "Summary: long conversation." in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert "Summary: long conversation." in compact_state.last_summary

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
        assert messages[0]["role"] == "user"
        assert "Summary: user said hello." in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert "Summary: user said hello." in compact_state.last_summary

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
        assert result.content == "Failed to generate summary: network down"
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
        assert result.content == "No old history to compress."

    def test_empty_response_content_returns_error(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(content=[])
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert result.is_error
        assert "Summary generation returned empty content." in result.content

    def test_response_with_no_text_block_returns_error(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="tool_use", name="some_tool")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert result.is_error
        assert "Summary generation returned empty content." in result.content

    def test_provider_error_stop_reason_returns_error(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            stop_reason="error",
            content=[MagicMock(type="text", text="provider internal error")],
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert result.is_error
        assert result.content == "Failed to generate summary: provider internal error"
        assert not compact_state.has_compacted
        assert len(messages) == 4  # history unchanged

    def test_focus_parameter_included_in_summary(self):
        messages = [
            {"role": "user", "content": "old user msg"},
            {"role": "assistant", "content": "old assistant msg"},
            {"role": "user", "content": "recent user msg"},
            {"role": "assistant", "content": "recent assistant msg"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary: focused.")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1, "focus": "auth bug"})
        assert not result.is_error
        assert messages[0]["role"] == "user"
        assert "auth bug" in messages[0]["content"]
