from src.provider.base import LLMProvider
from src.tools.base import ToolRegistry, ToolResult


class Agent:
    def __init__(self, provider: LLMProvider, registry: ToolRegistry):
        self.provider = provider
        self.registry = registry
        self.messages: list[dict] = []

    def run_interactive(self) -> None:
        print("Agent 已启动。输入 /exit 退出。")
        while True:
            try:
                user_input = input("> ").strip()
            except EOFError:
                break
            if user_input == "/exit":
                print("再见！")
                break
            if not user_input:
                continue
            self._run_turn(user_input)
            print()  # 空行分隔回合

    def _run_turn(self, user_input: str) -> None:
        self.messages.append({"role": "user", "content": user_input})
        tools = self.registry.to_anthropic_format()

        while True:
            response = self.provider.chat(self.messages, tools)

            assistant_content: list[dict] = []
            tool_uses: list = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    print(block.text, end="", flush=True)
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input or {},
                    })
                    tool_uses.append(block)

            if assistant_content:
                self.messages.append({"role": "assistant", "content": assistant_content})

            if tool_uses:
                tool_result_blocks: list[dict] = []
                for tu in tool_uses:
                    tool = self.registry.get(tu.name)
                    if tool is None:
                        result = ToolResult(
                            tool_use_id=tu.id,
                            content=f"Tool '{tu.name}' not found",
                            is_error=True,
                        )
                    else:
                        result = tool.execute(tu.id, tu.input or {})
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    })
                self.messages.append({"role": "user", "content": tool_result_blocks})

            if response.stop_reason == "end_turn":
                break
            elif response.stop_reason == "tool_use":
                continue
            elif response.stop_reason == "max_tokens":
                print("\n[Warning: Reached token limit]")
                break
            elif response.stop_reason == "error":
                break
            else:
                break
