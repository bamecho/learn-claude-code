from src.tools.base import ToolResult
from src.provider.base import LLMProvider
from src.agent.context import CompactState


class CompactTool:
    name = "compact"
    description = (
        "Compress conversation history by summarizing old messages. "
        "Use strategy='auto' to compress only when context is large, "
        "or strategy='force' to compress immediately."
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

        flat_text = self._serialize_messages(old_history)
        prompt = (
            "Summarize the following conversation history in a concise paragraph, "
            "preserving key decisions, file paths, and error states:\n\n"
            f"{flat_text}"
        )

        try:
            response = self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
            )
        except Exception as exc:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Failed to generate summary: {exc}",
                is_error=True,
            )

        if getattr(response, "stop_reason", None) == "error":
            error_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    error_text = getattr(block, "text", "")
                    break
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Failed to generate summary: {error_text}",
                is_error=True,
            )

        summary_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                summary_text = block.text
                break

        if not summary_text:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="Summary generation returned empty content.",
                is_error=True,
            )

        self.messages[:] = [
            {"role": "assistant", "content": summary_text},
            *preserved,
        ]
        self.compact_state.has_compacted = True
        self.compact_state.last_summary = summary_text

        return ToolResult(
            tool_use_id=tool_use_id,
            content=f"Context compressed. Summary: {summary_text[:200]}...",
        )

    @staticmethod
    def _serialize_messages(messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        texts.append(block["text"])
                    elif isinstance(block, dict) and "content" in block:
                        texts.append(str(block["content"]))
                    else:
                        texts.append(str(block))
                content = "\n".join(texts)
            parts.append(f"[{role}] {content}")
        return "\n".join(parts)
