from unittest.mock import MagicMock
from src.tools.todo_tool import TodoTool
from src.tools.base import ToolResult


def test_todo_tool_execute_success():
    mock_manager = MagicMock()
    mock_manager.render.return_value = "[ ] A\n(0/1 completed)"

    tool = TodoTool(manager=mock_manager)
    result = tool.execute("tu1", {"items": [{"content": "A", "status": "pending"}]})

    assert isinstance(result, ToolResult)
    assert result.tool_use_id == "tu1"
    assert "[ ] A" in result.content
    assert result.is_error is False
    mock_manager.update.assert_called_once_with([{"content": "A", "status": "pending"}])
    mock_manager.render.assert_called_once()


def test_todo_tool_execute_validation_error():
    mock_manager = MagicMock()
    mock_manager.update.side_effect = ValueError("Too many items")

    tool = TodoTool(manager=mock_manager)
    result = tool.execute("tu2", {"items": [{"content": "A", "status": "pending"}]})

    assert result.is_error is True
    assert "Too many items" in result.content


def test_todo_tool_default_manager():
    tool = TodoTool()
    result = tool.execute("tu3", {"items": [{"content": "A", "status": "pending"}]})
    assert result.is_error is False
    assert "[ ] A" in result.content


def test_todo_tool_clear_plan():
    tool = TodoTool()
    result = tool.execute("tu4", {"items": []})
    assert result.content == "No session plan yet."
