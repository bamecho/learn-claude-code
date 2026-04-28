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
    DEFAULT_THRESHOLD = 30000
    PREVIEW_LENGTH = 500

    def __init__(self, output_dir: str | None = None, threshold: int | None = None):
        self.output_dir = output_dir or ".task_outputs/tool-results"
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD

    def maybe_persist(self, tool_use_id: str, content: str) -> PersistedOutput | None:
        if len(content) <= self.threshold:
            return None
        os.makedirs(self.output_dir, exist_ok=True)
        file_path = os.path.join(self.output_dir, f"{tool_use_id}.txt")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            print(f"Warning: failed to persist output for {tool_use_id}: {exc}", file=sys.stderr)
            return None
        preview = content[: self.PREVIEW_LENGTH]
        return PersistedOutput(tool_use_id, file_path, preview, len(content))
