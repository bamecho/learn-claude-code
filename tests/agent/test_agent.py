from unittest.mock import MagicMock
from src.agent.agent import Agent
from src.provider.base import LLMResponse, ContentBlock
from src.tools.base import ToolRegistry, ToolResult


def test_agent_end_turn_with_text():
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="text", text="Hello!")],
        stop_reason="end_turn",
    )
    agent = Agent(mock_provider, ToolRegistry())
    agent._run_turn("Hi")

    assert len(agent.messages) == 2
    assert agent.messages[0] == {"role": "user", "content": "Hi"}
    assert agent.messages[1]["role"] == "assistant"


def test_agent_tool_use_chain():
    """验证 tool_use → execute → tool_result → 自动继续 → end_turn 的完整链路。"""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        LLMResponse(
            content=[
                ContentBlock(type="tool_use", id="tu1", name="mock_read", input={"path": "x"})
            ],
            stop_reason="tool_use",
        ),
        LLMResponse(
            content=[ContentBlock(type="text", text="Done")],
            stop_reason="end_turn",
        ),
    ]

    registry = ToolRegistry()
    mock_tool = MagicMock()
    mock_tool.name = "mock_read"
    mock_tool.execute.return_value = ToolResult(tool_use_id="tu1", content="mock data")
    registry.register(mock_tool)

    agent = Agent(mock_provider, registry)
    agent._run_turn("Read file")

    assert mock_provider.chat.call_count == 2
    # 第一次调用后的 messages：user + assistant(tool_use)
    # 然后追加了 tool_result user message
    # 第二次调用后的 messages：又追加了 assistant(text)
    assert agent.messages[-1]["role"] == "assistant"
    assert agent.messages[-1]["content"][0]["text"] == "Done"


def test_agent_tool_not_found():
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        LLMResponse(
            content=[ContentBlock(type="tool_use", id="tu1", name="missing", input={})],
            stop_reason="tool_use",
        ),
        LLMResponse(
            content=[ContentBlock(type="text", text="Ack")],
            stop_reason="end_turn",
        ),
    ]

    agent = Agent(mock_provider, ToolRegistry())
    agent._run_turn("Call missing")

    # tool_result 作为 user message 被追加
    tool_result_msg = agent.messages[-2]
    assert tool_result_msg["role"] == "user"
    assert "not found" in str(tool_result_msg["content"])


def test_agent_max_tokens():
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="text", text="Cut")],
        stop_reason="max_tokens",
    )
    agent = Agent(mock_provider, ToolRegistry())
    agent._run_turn("Long")

    assert len(agent.messages) == 2
    assert agent.messages[1]["role"] == "assistant"


def test_agent_error_stop_reason():
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="text", text="Error: bad")],
        stop_reason="error",
    )
    agent = Agent(mock_provider, ToolRegistry())
    agent._run_turn("Trigger error")

    assert len(agent.messages) == 2
