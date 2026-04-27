from src.tools.base import ToolRegistry, ToolResult


class FakeTool:
    name = "fake"
    description = "A fake tool"
    input_schema = {"type": "object", "properties": {}}

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        return ToolResult(tool_use_id=tool_use_id, content="done")


def test_registry_register_and_get():
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)
    assert registry.get("fake") is tool
    assert registry.get("missing") is None


def test_registry_list_tools():
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)
    assert registry.list_tools() == [tool]


def test_registry_to_anthropic_format():
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)
    fmt = registry.to_anthropic_format()
    assert len(fmt) == 1
    assert fmt[0]["name"] == "fake"
    assert fmt[0]["description"] == "A fake tool"
    assert fmt[0]["input_schema"] == {"type": "object", "properties": {}}
