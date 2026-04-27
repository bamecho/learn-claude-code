from src.tools.mock_tools import MockFileReadTool
from src.tools.base import ToolResult


def test_mock_file_read():
    tool = MockFileReadTool()
    result = tool.execute("tu_1", {"path": "example.txt"})
    assert isinstance(result, ToolResult)
    assert result.tool_use_id == "tu_1"
    assert "example.txt" in result.content
    assert result.is_error is False


def test_mock_file_read_default_path():
    tool = MockFileReadTool()
    result = tool.execute("tu_2", {})
    assert "unknown" in result.content
