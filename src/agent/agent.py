from dataclasses import dataclass

from src.provider.base import LLMProvider
from src.tools.base import ToolRegistry, ToolResult


@dataclass
class LoopState:
    # The minimal loop state: history, loop count, and why we continue.
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        system: str | None = None,
    ):
        self.provider = provider
        self.registry = registry
        self.messages: list[dict] = []
        self.system = system
        self.turn_count: int = 0
        self.transition_reason: str | None = None

    def run_interactive(self) -> None:
        print("Agent 已启动。输入 /exit、exit、q 或留空退出。")
        while True:
            try:
                user_input = input("> ").strip()
            except EOFError:
                break
            if user_input.lower() in ("/exit", "exit", "q", ""):
                print("再见！")
                break
            if not user_input:
                continue
            self._run_turn(user_input)
            print()  # 空行分隔回合

    @staticmethod
    def extract_text(content) -> str:
        if not isinstance(content, list):
            return ""
        texts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if text:
                texts.append(text)
        return "\n".join(texts).strip()

    def _run_turn(self, user_input: str) -> None:
        self.messages.append({"role": "user", "content": user_input})
        state = LoopState(messages=self.messages)
        self._agent_loop(state)
        self.turn_count = state.turn_count
        self.transition_reason = state.transition_reason

    def _agent_loop(self, state: LoopState) -> None:
        while self._run_one_turn(state):
            pass

    def _run_one_turn(self, state: LoopState) -> bool:
        tools = self.registry.to_anthropic_format()
        response = self.provider.chat(state.messages, tools, system=self.system)

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
            state.messages.append({"role": "assistant", "content": assistant_content})

        if tool_uses:
            tool_result_blocks: list[dict] = []
            for tu in tool_uses:
                command_str = ""
                if isinstance(tu.input, dict):
                    command_str = tu.input.get("command", "")
                if command_str:
                    print(f"\n\033[33m$ {command_str}\033[0m")

                tool = self.registry.get(tu.name)
                if tool is None:
                    result = ToolResult(
                        tool_use_id=tu.id,
                        content=f"Tool '{tu.name}' not found",
                        is_error=True,
                    )
                else:
                    result = tool.execute(tu.id, tu.input or {})

                print(result.content[:200])
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_use_id,
                    "content": result.content,
                    "is_error": result.is_error,
                })
            state.messages.append({"role": "user", "content": tool_result_blocks})

        if response.stop_reason == "end_turn":
            state.transition_reason = None
            return False
        elif response.stop_reason == "tool_use":
            state.turn_count += 1
            state.transition_reason = "tool_result"
            return True
        elif response.stop_reason == "max_tokens":
            print("\n[Warning: Reached token limit]")
            state.transition_reason = "max_tokens"
            return False
        elif response.stop_reason == "error":
            state.transition_reason = "error"
            return False
        else:
            state.transition_reason = None
            return False
