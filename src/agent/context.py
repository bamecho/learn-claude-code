import json
import time
from dataclasses import dataclass, field
import os
import sys
from pathlib import Path


@dataclass(frozen=True)
class PersistedOutput:
    tool_use_id: str
    file_path: str
    preview: str
    original_length: int


class PersistedOutputManager:
    """Manages persisting large tool outputs to disk."""

    DEFAULT_THRESHOLD = 30000
    PREVIEW_LENGTH = 2000

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


@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)


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
            content = block.get("content", "")
            if isinstance(content, str) and len(content) > 120 and content != cls.PLACEHOLDER:
                block["content"] = cls.PLACEHOLDER


# ---------------------------------------------------------------------------
# recent-files tracking
# ---------------------------------------------------------------------------

def track_recent_file(state, path: str) -> None:
    """Track the most recently read files in CompactState (max 5)."""
    if path in state.recent_files:
        state.recent_files.remove(path)
    state.recent_files.append(path)
    if len(state.recent_files) > 5:
        state.recent_files[:] = state.recent_files[-5:]


# ---------------------------------------------------------------------------
# History compactor (auto-compaction before API calls)
# ---------------------------------------------------------------------------

class HistoryCompactor:
    """Summarize and replace old conversation history when context grows too large."""

    CONTEXT_LIMIT = 50000
    TRANSCRIPT_DIR = Path(".transcripts")

    @staticmethod
    def estimate_context_size(messages: list) -> int:
        return len(str(messages))

    @classmethod
    def write_transcript(cls, messages: list) -> Path:
        cls.TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        path = cls.TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(message, default=str) + "\n")
        return path

    @classmethod
    def summarize_history(cls, provider, messages: list, max_tokens: int = 2000) -> str:
        conversation = json.dumps(messages, default=str)[:80000]
        prompt = (
            "Summarize this coding-agent conversation so work can continue.\n"
            "Preserve:\n"
            "1. The current goal\n"
            "2. Important findings and decisions\n"
            "3. Files read or changed\n"
            "4. Remaining work\n"
            "5. User constraints and preferences\n"
            "Be compact but concrete.\n\n"
            f"{conversation}"
        )
        response = provider.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            max_tokens=max_tokens,
        )

        if getattr(response, "stop_reason", None) == "error":
            error_text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    error_text = getattr(block, "text", "")
                    break
            raise RuntimeError(error_text or "provider internal error")

        summary_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                summary_text = block.text
                break

        if not summary_text:
            raise RuntimeError("Summary generation returned empty content.")

        return summary_text.strip()

    @classmethod
    def compact_history(cls, messages: list, state, provider, focus: str | None = None) -> tuple[list, Path, str]:
        transcript_path = cls.write_transcript(messages)
        summary = cls.summarize_history(provider, messages)
        if focus:
            summary += f"\n\nFocus to preserve next: {focus}"
        if state.recent_files:
            recent_lines = "\n".join(f"- {path}" for path in state.recent_files)
            summary += f"\n\nRecent files to reopen if needed:\n{recent_lines}"
        state.has_compacted = True
        state.last_summary = summary
        new_messages = [{
            "role": "user",
            "content": (
                "This conversation was compacted so the agent can continue working.\n\n"
                f"{summary}"
            ),
        }]
        return new_messages, transcript_path, summary
