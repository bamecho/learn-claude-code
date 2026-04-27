import os
from pathlib import Path

from .base import ToolResult


WORKDIR = Path(os.getcwd()).resolve()


def safe_path(p: str) -> Path:
    """Resolve *p* relative to WORKDIR and enforce workspace boundary."""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


class ReadFileTool:
    name = "read_file"
    description = "Read the contents of a file."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "startLine": {"type": "integer"},
            "endLine": {"type": "integer"},
        },
        "required": ["filePath"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        try:
            path = safe_path(input["filePath"])
        except ValueError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        if not path.exists():
            return ToolResult(tool_use_id=tool_use_id, content="Error: File not found", is_error=True)

        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        start = input.get("startLine")
        end = input.get("endLine")

        if start is not None:
            start_idx = max(0, start - 1)
        else:
            start_idx = 0

        if end is not None:
            end_idx = end
        else:
            end_idx = len(lines)

        selected = lines[start_idx:end_idx]
        return ToolResult(tool_use_id=tool_use_id, content="".join(selected), is_error=False)
