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
            "filePath": {"type": "string", "description": "Path to the file, relative to the workspace root."},
            "startLine": {"type": "integer", "description": "1-based line number to start reading from (inclusive)."},
            "endLine": {"type": "integer", "description": "1-based line number to stop reading at (inclusive)."},
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
        except (OSError, UnicodeDecodeError) as e:
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


class WriteFileTool:
    name = "write_file"
    description = "Write content to a file, overwriting if it exists."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string", "description": "Path to the file, relative to the workspace root."},
            "content": {"type": "string", "description": "Content to write into the file."},
        },
        "required": ["filePath", "content"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        try:
            path = safe_path(input["filePath"])
        except ValueError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        content = input.get("content", "")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        return ToolResult(
            tool_use_id=tool_use_id,
            content=f"Wrote {len(content.encode('utf-8'))} bytes to {input['filePath']}",
            is_error=False,
        )


class EditFileTool:
    name = "edit_file"
    description = "Replace a unique occurrence of oldText with newText in a file."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string", "description": "Path to the file, relative to the workspace root."},
            "oldText": {"type": "string", "description": "Exact text to replace. Must appear exactly once in the file."},
            "newText": {"type": "string", "description": "Text to insert in place of oldText."},
        },
        "required": ["filePath", "oldText", "newText"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        try:
            path = safe_path(input["filePath"])
        except ValueError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        old_text = input["oldText"]
        new_text = input["newText"]

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        count = content.count(old_text)
        if count == 0:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="Error: text to replace not found",
                is_error=True,
            )
        if count > 1:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Error: text to replace found {count} times, expected exactly one",
                is_error=True,
            )

        new_content = content.replace(old_text, new_text, 1)
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            return ToolResult(tool_use_id=tool_use_id, content=f"Error: {e}", is_error=True)

        return ToolResult(
            tool_use_id=tool_use_id,
            content=f"Replaced 1 occurrence in {input['filePath']}",
            is_error=False,
        )
