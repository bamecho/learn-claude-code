import os
import subprocess

from .base import ToolResult


class BashTool:
    name = "bash"
    description = "Run a shell command in the current workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to run."},
        },
        "required": ["command"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        command = input.get("command", "")
        dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
        if any(item in command for item in dangerous):
            return ToolResult(
                tool_use_id=tool_use_id,
                content="Error: Dangerous command blocked",
                is_error=True,
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=os.getcwd(),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="Error: Timeout (120s)",
                is_error=True,
            )
        except (FileNotFoundError, OSError) as e:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Error: {e}",
                is_error=True,
            )

        output = (result.stdout + result.stderr).strip()
        if not output:
            output = "(no output)"

        return ToolResult(
            tool_use_id=tool_use_id,
            content=output[:50000],
            is_error=False,
        )
