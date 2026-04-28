from src.tools.base import ToolResult
from src.provider.base import LLMProvider
from src.agent.context import CompactState, HistoryCompactor


class CompactTool:
    name = "compact"
    description = (
        "Compress conversation history by summarizing old messages. "
        "Use strategy='auto' to compress only when context is large, "
        "or strategy='force' to compress immediately. "
        "Optionally provide a 'focus' hint to preserve in the summary."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "strategy": {
                "type": "string",
                "enum": ["auto", "force"],
                "description": "auto = compress only if token threshold exceeded; force = always compress.",
                "default": "auto",
            },
            "keep_last_assistant": {
                "type": "integer",
                "description": "Number of recent assistant messages to preserve verbatim.",
                "default": 3,
                "minimum": 1,
            },
            "focus": {
                "type": "string",
                "description": "Optional focus area or topic to preserve in the summary.",
                "default": "",
            },
        },
        "required": [],
    }

    def __init__(
        self,
        provider: LLMProvider,
        messages: list[dict],
        compact_state: CompactState,
    ):
        self.provider = provider
        self.messages = messages
        self.compact_state = compact_state

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        strategy = input.get("strategy", "auto")
        keep_last = input.get("keep_last_assistant", 3)
        focus = input.get("focus") or None

        if strategy == "auto":
            total_chars = sum(
                len(str(msg.get("content", "")))
                for msg in self.messages
            )
            estimated_tokens = total_chars // 4
            if estimated_tokens < 8000:
                return ToolResult(
                    tool_use_id=tool_use_id,
                    content="Current context is within the safe threshold; no compression needed.",
                )

        assistant_indices = [
            i for i, msg in enumerate(self.messages) if msg.get("role") == "assistant"
        ]

        if len(assistant_indices) <= keep_last:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="No old history to compress.",
            )

        cutoff_index = assistant_indices[-keep_last]
        old_history = self.messages[:cutoff_index]
        preserved = self.messages[cutoff_index:]

        old_count = len(self.messages)

        # Use HistoryCompactor for the actual compaction
        try:
            compacted, path, summary = HistoryCompactor.compact_history(
                old_history, self.compact_state, self.provider, focus=focus
            )
        except Exception as exc:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Failed to generate summary: {exc}",
                is_error=True,
            )

        # Replace messages: compacted summary + preserved recent turns
        self.messages[:] = [*compacted, *preserved]

        return ToolResult(
            tool_use_id=tool_use_id,
            content=(
                f"[transcript saved: {path}]\n"
                f"[compacted {old_count} -> {len(self.messages)} messages]\n"
                f"Summary: {summary[:200]}..."
            ),
        )
