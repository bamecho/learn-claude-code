from unittest.mock import MagicMock
from src.tools.task_tool import TaskTool
from src.tools.base import ToolRegistry, ToolResult
from src.provider.base import LLMResponse, ContentBlock


def test_task_tool_empty_prompt():
    mock_provider = MagicMock()
    registry = ToolRegistry()
    tool = TaskTool(mock_provider, registry)
    result = tool.execute("tu1", {"prompt": ""})
    assert result.is_error is True
    assert "required" in result.content


def test_task_tool_runs_subagent_and_returns_summary():
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="text", text="Subtask done.")],
        stop_reason="end_turn",
    )
    registry = ToolRegistry()
    tool = TaskTool(mock_provider, registry)
    result = tool.execute("tu2", {"prompt": "Do something"})
    assert result.is_error is False
    assert result.content == "Subtask done."


def test_task_tool_respects_max_turns():
    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=[ContentBlock(type="tool_use", id="tu1", name="bash", input={"command": "echo 1"})],
        stop_reason="tool_use",
    )
    registry = ToolRegistry()
    bash = MagicMock()
    bash.name = "bash"
    bash.execute.return_value = ToolResult(tool_use_id="tu1", content="ok")
    registry.register(bash)

    tool = TaskTool(mock_provider, registry, max_turns=2)
    result = tool.execute("tu3", {"prompt": "Loop"})
    assert "[Subagent reached turn limit]" in result.content
    assert mock_provider.chat.call_count == 2
