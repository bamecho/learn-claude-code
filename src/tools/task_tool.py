from src.tools.base import Tool, ToolRegistry, ToolResult


class TaskTool:
    name = "task"
    description = "Run a subtask in a clean context and return a summary."
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The subtask instruction.",
            },
            "description": {
                "type": "string",
                "description": "Short description of the subtask for logging.",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, provider, registry, system=None, subagent_system=None, max_turns=40):
        self.provider = provider
        self.registry = registry
        self.system = system
        self.subagent_system = subagent_system
        self.max_turns = max_turns

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        prompt = input.get("prompt", "").strip()
        description = input.get("description", "").strip()
        if not prompt:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="prompt is required",
                is_error=True,
            )

        filtered = ToolRegistry()
        for tool in self.registry.list_tools():
            if tool.name != "task":
                filtered.register(tool)

        if description:
            print(f"> task ({description}): {prompt[:80]}")
        else:
            print(f"> task: {prompt[:80]}")

        from src.agent.agent import Agent
        subagent_system = self.subagent_system if self.subagent_system is not None else self.system
        subagent = Agent(self.provider, filtered, system=subagent_system)
        subagent._run_turn(prompt, max_turns=self.max_turns)

        summary = ""
        for msg in reversed(subagent.messages):
            if msg.get("role") == "assistant":
                content = msg.get("content")
                if isinstance(content, list):
                    texts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    summary = "\n".join(texts).strip()
                else:
                    summary = str(content).strip()
                break

        if subagent.transition_reason == "max_turns":
            summary = f"[Subagent reached turn limit] {summary}"

        return ToolResult(tool_use_id=tool_use_id, content=summary)
