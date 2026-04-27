from dataclasses import dataclass

from src.provider.base import LLMProvider
from src.tools.base import ToolRegistry, ToolResult


def normalize_messages(messages: list) -> list:
    """Clean up messages before sending to the API.

    Three jobs:
    1. Strip internal metadata fields the API doesn't understand
    2. Ensure every tool_use has a matching tool_result (insert placeholder if missing)
    3. Merge consecutive same-role messages (API requires strict alternation)
    """
    cleaned = []
    for msg in messages:
        clean = {"role": msg["role"]}
        if isinstance(msg.get("content"), str):
            clean["content"] = msg["content"]
        elif isinstance(msg.get("content"), list):
            clean["content"] = [
                {k: v for k, v in block.items() if not k.startswith("_")}
                for block in msg["content"]
                if isinstance(block, dict)
            ]
        else:
            clean["content"] = msg.get("content", "")
        cleaned.append(clean)

    # Collect existing tool_result IDs
    existing_results = set()
    for msg in cleaned:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    existing_results.add(block.get("tool_use_id"))

    # Find orphaned tool_use blocks and insert placeholder results
    for msg in cleaned:
        if msg["role"] != "assistant" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("id") not in existing_results:
                cleaned.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": "(cancelled)",
                            }
                        ],
                    }
                )

    # Merge consecutive same-role messages
    if not cleaned:
        return cleaned
    merged = [cleaned[0]]
    for msg in cleaned[1:]:
        if msg["role"] == merged[-1]["role"]:
            prev = merged[-1]
            prev_c = (
                prev["content"]
                if isinstance(prev["content"], list)
                else [{"type": "text", "text": str(prev["content"])}]
            )
            curr_c = (
                msg["content"]
                if isinstance(msg["content"], list)
                else [{"type": "text", "text": str(msg["content"])}]
            )
            prev["content"] = prev_c + curr_c
        else:
            merged.append(msg)
    return merged


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
        self.todo_manager = None
        todo_tool = self.registry.get("todo")
        if todo_tool is not None:
            self.todo_manager = getattr(todo_tool, "manager", None)

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
        response = self.provider.chat(normalize_messages(state.messages), tools, system=self.system)

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

            used_todo = any(tu.name == "todo" for tu in tool_uses)

            if self.todo_manager is not None:
                if used_todo:
                    self.todo_manager.state.rounds_since_update = 0
                else:
                    self.todo_manager.note_round_without_update()
                    reminder = self.todo_manager.reminder()
                    if reminder:
                        tool_result_blocks.insert(
                            0, {"type": "text", "text": reminder}
                        )

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
