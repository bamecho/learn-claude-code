from unittest.mock import patch, MagicMock
import subprocess

from src.tools.bash_tool import BashTool
from src.tools.base import ToolResult


def test_bash_tool_success():
    tool = BashTool()
    result = tool.execute("tu_1", {"command": "echo hello"})
    assert isinstance(result, ToolResult)
    assert result.tool_use_id == "tu_1"
    assert result.is_error is False
    assert "hello" in result.content


def test_bash_tool_dangerous_command():
    tool = BashTool()
    result = tool.execute("tu_2", {"command": "sudo apt update"})
    assert result.is_error is True
    assert "Dangerous command blocked" in result.content


def test_bash_tool_no_output():
    tool = BashTool()
    result = tool.execute("tu_3", {"command": "true"})
    assert result.is_error is False
    assert result.content == "(no output)"


def test_bash_tool_timeout():
    tool = BashTool()
    with patch(
        "src.tools.bash_tool.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="sleep 10", timeout=120),
    ):
        result = tool.execute("tu_4", {"command": "sleep 10"})
    assert result.is_error is True
    assert "Timeout" in result.content


def test_bash_tool_os_error():
    tool = BashTool()
    with patch(
        "src.tools.bash_tool.subprocess.run",
        side_effect=OSError("No such file or directory"),
    ):
        result = tool.execute("tu_5", {"command": "some_missing_binary"})
    assert result.is_error is True
    assert "No such file or directory" in result.content


def test_bash_tool_output_truncation():
    tool = BashTool()
    long_output = "x" * 60000
    mock_result = MagicMock()
    mock_result.stdout = long_output
    mock_result.stderr = ""
    with patch("src.tools.bash_tool.subprocess.run", return_value=mock_result):
        result = tool.execute("tu_6", {"command": "cat bigfile"})
    assert len(result.content) == 50000
    assert result.is_error is False
