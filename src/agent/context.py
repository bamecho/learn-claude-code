from dataclasses import dataclass
import os
import sys


@dataclass(frozen=True)
class PersistedOutput:
    tool_use_id: str
    file_path: str
    preview: str
    original_length: int


class PersistedOutputManager:
    """Manages persisting large tool outputs to disk."""

    DEFAULT_THRESHOLD = 30000
    PREVIEW_LENGTH = 500

    def __init__(self, output_dir: str | None = None, threshold: int | None = None):
        self.output_dir = output_dir or ".task_outputs/tool-results"
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD

    def maybe_persist(self, tool_use_id: str, content: str) -> PersistedOutput | None:
        """Persist content to disk if it exceeds the threshold, returning metadata."""
        if len(content) <= self.threshold:
            return None
        os.makedirs(self.output_dir, exist_ok=True)
        safe_id = os.path.basename(tool_use_id).replace(os.sep, "_")
        file_path = os.path.join(self.output_dir, f"{safe_id}.txt")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            print(f"Warning: failed to persist output for {tool_use_id}: {exc}", file=sys.stderr)
            return None
        preview = content[: self.PREVIEW_LENGTH]
        return PersistedOutput(tool_use_id, file_path, preview, len(content))


class MicroCompactor:
    """Compact older tool_result blocks in message histories to reduce context size."""

    KEEP_LAST = 3
    PLACEHOLDER = "(... older tool output omitted)"

    @classmethod
    def apply(cls, messages: list[dict]) -> None:
        """Replace content of older tool_result blocks with a placeholder, keeping the last 3."""
        tool_result_indices: list[tuple[int, int]] = []
        for msg_idx, msg in enumerate(messages):
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block_idx, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_result_indices.append((msg_idx, block_idx))

        if len(tool_result_indices) <= cls.KEEP_LAST:
            return

        for msg_idx, block_idx in tool_result_indices[:-cls.KEEP_LAST]:
            block = messages[msg_idx]["content"][block_idx]
            if block.get("content") != cls.PLACEHOLDER:
                block["content"] = cls.PLACEHOLDER
