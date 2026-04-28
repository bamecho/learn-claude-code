from unittest.mock import MagicMock
from src.agent.agent import Agent
from src.provider.base import ContentBlock, LLMResponse
from src.tools.base import ToolRegistry, ToolResult


class TestAgentContextCompression:
    def test_large_tool_result_gets_persisted_marker(self, tmp_path):
        from src.agent.context import PersistedOutputManager

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        big_output = "x" * 35000
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="t1", content=big_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="mock_tool", input={})],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry)
        agent.persisted_output_manager = PersistedOutputManager(
            output_dir=str(tmp_path / "tool-results"),
            threshold=30000,
        )
        agent._run_turn("run mock", max_turns=1)

        tool_result_msg = agent.messages[2]
        assert tool_result_msg["role"] == "user"
        result_block = tool_result_msg["content"][0]
        assert "persisted-output" in result_block["content"]

    def test_micro_compactor_replaces_old_tool_results(self, tmp_path):
        from src.agent.context import PersistedOutputManager

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        long_output = "x" * 200
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="tx", content=long_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        # Simulate 5 turns, each producing a tool_use then end_turn
        responses = [
            LLMResponse(
                content=[ContentBlock(type="tool_use", id=f"t{i}", name="mock_tool", input={})],
                stop_reason="tool_use",
            )
            for i in range(5)
        ]
        responses.append(
            LLMResponse(content=[ContentBlock(type="text", text="done")], stop_reason="end_turn")
        )
        provider.chat.side_effect = responses

        agent = Agent(provider, registry)
        agent.persisted_output_manager = PersistedOutputManager(
            output_dir=str(tmp_path / "tool-results"),
            threshold=30000,
        )
        agent._run_turn("run mock", max_turns=6)

        # Find all tool_result blocks across messages
        tool_results = []
        for msg in agent.messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert len(tool_results) == 5
        assert tool_results[0]["content"] == "(... older tool output omitted)"
        assert tool_results[1]["content"] == "(... older tool output omitted)"
        assert tool_results[2]["content"] == long_output
        assert tool_results[3]["content"] == long_output
        assert tool_results[4]["content"] == long_output


class TestAgentCompactToolIntegration:
    def test_compact_tool_replaces_old_history(self):
        from src.tools.compact_tool import CompactTool

        mock_provider = MagicMock()
        registry = ToolRegistry()
        agent = Agent(mock_provider, registry)

        # Seed history: 2 old pairs + 1 recent pair
        agent.messages = [
            {"role": "user", "content": "old user 1"},
            {"role": "assistant", "content": "old assistant 1"},
            {"role": "user", "content": "old user 2"},
            {"role": "assistant", "content": "old assistant 2"},
            {"role": "user", "content": "recent user"},
            {"role": "assistant", "content": "recent assistant"},
        ]

        # Register compact tool bound to agent state
        compact_tool = CompactTool(
            provider=mock_provider,
            messages=agent.messages,
            compact_state=agent.compact_state,
        )
        registry.register(compact_tool)

        # Mock provider to return a valid summary
        mock_provider.chat.return_value = MagicMock(
            stop_reason="end_turn",
            content=[MagicMock(type="text", text="Summary of old history.")],
        )

        result = compact_tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})

        assert not result.is_error
        assert agent.compact_state.has_compacted is True
        assert agent.compact_state.last_summary == "Summary of old history."

        # Old history should be replaced by a single assistant summary
        assert len(agent.messages) == 2
        assert agent.messages[0]["role"] == "assistant"
        assert agent.messages[0]["content"] == "Summary of old history."

        # Recent pair preserved
        assert agent.messages[1]["role"] == "assistant"
        assert agent.messages[1]["content"] == "recent assistant"


class TestAgentAutoCompact:
    def test_auto_compact_triggers_when_context_too_large(self):
        from src.agent.context import HistoryCompactor

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        small_output = "x"
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="tx", content=small_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="mock_tool", input={})],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry)
        # Seed messages with a huge string to trigger auto-compaction
        agent.messages = [{"role": "user", "content": "x" * 60000}]

        agent._run_turn("run mock", max_turns=1)

        # The first provider.chat call should have been the summarization (no tools)
        # The second provider.chat call is the actual turn
        calls = provider.chat.call_args_list
        assert len(calls) >= 1
        # First call is the auto-compact summary
        first_call = calls[0]
        first_call_messages = first_call.kwargs.get("messages") if first_call.kwargs else first_call.args[0]
        assert any("Summarize" in str(m.get("content", "")) for m in first_call_messages)
        assert agent.compact_state.has_compacted is True
