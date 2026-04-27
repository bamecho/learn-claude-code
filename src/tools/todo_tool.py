from src.planning.todo_manager import TodoManager
from .base import ToolResult


class TodoTool:
    name = "todo"
    description = "Rewrite the current session plan for multi-step work."
    input_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                        "activeForm": {
                            "type": "string",
                            "description": "Optional present-continuous label.",
                        },
                    },
                    "required": ["content", "status"],
                },
            },
        },
        "required": ["items"],
    }

    def __init__(self, manager: TodoManager | None = None):
        self.manager = manager or TodoManager()

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        try:
            self.manager.update(input["items"])
            text = self.manager.render()
            return ToolResult(tool_use_id=tool_use_id, content=text)
        except ValueError as exc:
            return ToolResult(
                tool_use_id=tool_use_id, content=str(exc), is_error=True
            )
