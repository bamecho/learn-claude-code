from unittest.mock import MagicMock
from src.agent.agent import Agent
from src.provider.base import LLMResponse, ContentBlock
from src.tools.base import ToolRegistry, ToolResult
from src.tools.todo_tool import TodoTool


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


def test_agent_todo_resets_rounds():
    """Calling todo should reset rounds_since_update to 0."""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        LLMResponse(
            content=[
                ContentBlock(
                    type="tool_use",
                    id="tu1",
                    name="todo",
                    input={"items": [{"content": "Plan", "status": "pending"}]},
                )
            ],
            stop_reason="tool_use",
        ),
        LLMResponse(
            content=[ContentBlock(type="text", text="Done")],
            stop_reason="end_turn",
        ),
    ]

    registry = ToolRegistry()
    todo_tool = TodoTool()
    registry.register(todo_tool)

    agent = Agent(mock_provider, registry)
    todo_tool.manager.note_round_without_update()
    todo_tool.manager.note_round_without_update()
    assert todo_tool.manager.state.rounds_since_update == 2
    agent._run_turn("Make a plan")

    assert todo_tool.manager.state.rounds_since_update == 0


def test_agent_reminder_after_three_rounds():
    """After 3 turns without todo, the next tool result should include a reminder."""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        # Round 1: bash
        LLMResponse(
            content=[ContentBlock(type="tool_use", id="tu1", name="bash", input={"command": "echo 1"})],
            stop_reason="tool_use",
        ),
        # Round 2: bash
        LLMResponse(
            content=[ContentBlock(type="tool_use", id="tu2", name="bash", input={"command": "echo 2"})],
            stop_reason="tool_use",
        ),
        # Round 3: bash (reminder should fire now)
        LLMResponse(
            content=[ContentBlock(type="tool_use", id="tu3", name="bash", input={"command": "echo 3"})],
            stop_reason="tool_use",
        ),
        # Final: end_turn
        LLMResponse(
            content=[ContentBlock(type="text", text="Done")],
            stop_reason="end_turn",
        ),
    ]

    registry = ToolRegistry()
    bash_tool = MagicMock()
    bash_tool.name = "bash"
    bash_tool.execute.return_value = ToolResult(tool_use_id="x", content="ok")
    registry.register(bash_tool)

    todo_tool = TodoTool()
    todo_tool.manager.update([{"content": "Initial task", "status": "pending"}])
    registry.register(todo_tool)

    agent = Agent(mock_provider, registry)
    agent._run_turn("Do work")

    # Find the last user message (should be round 3 tool results)
    user_messages = [m for m in agent.messages if m["role"] == "user"]
    last_user = user_messages[-1]
    content = last_user["content"]

    assert any(
        block.get("type") == "text" and "reminder" in str(block.get("text", ""))
        for block in content
    )


def test_agent_respects_max_turns():
    """Loop should stop before exceeding max_turns."""
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="tool_use", id="tu1", name="bash", input={"command": "echo hi"})],
        stop_reason="tool_use",
    )
    registry = ToolRegistry()
    bash = MagicMock()
    bash.name = "bash"
    bash.execute.return_value = ToolResult(tool_use_id="tu1", content="ok")
    registry.register(bash)

    agent = Agent(mock_provider, registry)
    agent._run_turn("Do work", max_turns=1)

    assert mock_provider.chat.call_count == 1
    assert agent.transition_reason == "max_turns"
