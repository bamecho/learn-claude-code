from .base import ToolResult


class MockFileReadTool:
    name = "mock_file_read"
    description = "模拟读取文件内容（s01 占位工具，仅用于验证工具调用链路）。"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            }
        },
        "required": ["path"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        path = input.get("path", "unknown")
        return ToolResult(
            tool_use_id=tool_use_id,
            content=f"<mock: 这是 {path} 的模拟内容>",
            is_error=False,
        )
