from unittest.mock import MagicMock, patch
from src.agent.agent import Agent
from src.permissions.engine import PermissionEngine, PermissionRule
from src.provider.base import ContentBlock, LLMResponse
from src.tools.base import ToolRegistry, ToolResult


class TestPermissionIntegration:
    def test_deny_rule_returns_error_tool_result(self):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="ok", is_error=False)
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="bash", input={"command": "ls"})],
            stop_reason="tool_use",
        )

        engine = PermissionEngine(rules=[PermissionRule(tool="bash", behavior="deny")])
        agent = Agent(provider, registry, permission_engine=engine, interactive=False)
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[2]
        assert tool_result_msg["role"] == "user"
        block = tool_result_msg["content"][0]
        assert block["is_error"] is True
        assert "Permission denied" in block["content"]
        mock_tool.execute.assert_not_called()

    def test_ask_in_non_interactive_denies(self):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="ok", is_error=False)
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="bash", input={"command": "ls"})],
            stop_reason="tool_use",
        )

        engine = PermissionEngine(mode="default")
        agent = Agent(provider, registry, permission_engine=engine, interactive=False)
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[2]
        block = tool_result_msg["content"][0]
        assert block["is_error"] is True
        assert "Permission denied by user" in block["content"]
        mock_tool.execute.assert_not_called()

    def test_ask_in_interactive_allows_when_user_says_yes(self):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="ok", is_error=False)
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="bash", input={"command": "ls"})],
            stop_reason="tool_use",
        )

        engine = PermissionEngine(mode="default")
        agent = Agent(provider, registry, permission_engine=engine, interactive=True)
        with patch("builtins.input", return_value="y"):
            agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[2]
        block = tool_result_msg["content"][0]
        assert block["is_error"] is False
        assert block["content"] == "ok"
        mock_tool.execute.assert_called_once()

    def test_allow_rule_executes_without_prompt(self):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="content", is_error=False)
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="read_file", input={"filePath": "x"})],
            stop_reason="tool_use",
        )

        engine = PermissionEngine(rules=[PermissionRule(tool="read_file", behavior="allow")])
        agent = Agent(provider, registry, permission_engine=engine, interactive=False)
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[2]
        block = tool_result_msg["content"][0]
        assert block["is_error"] is False
        assert block["content"] == "content"
        mock_tool.execute.assert_called_once()

    def test_no_permission_engine_runs_tool_directly(self):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        mock_tool.execute.return_value = ToolResult(tool_use_id="t1", content="ok", is_error=False)
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="bash", input={"command": "ls"})],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry, permission_engine=None, interactive=False)
        agent._run_turn("run", max_turns=1)

        tool_result_msg = agent.messages[2]
        block = tool_result_msg["content"][0]
        assert block["is_error"] is False
        mock_tool.execute.assert_called_once()
