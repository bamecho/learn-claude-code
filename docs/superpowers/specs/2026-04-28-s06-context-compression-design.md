# s06 Context Compression Design

## Overview

`s06` introduces a three-layer context compression pipeline to prevent the Agent's conversation history from growing unbounded and exhausting the model's context window. The pipeline is progressive: each layer addresses a different class of bloat, and later layers only activate when earlier ones are insufficient.

The pipeline consists of:

1. **Persisted Output Manager** (automatic) — writes oversized individual tool outputs to disk and replaces them with a lightweight preview marker.
2. **Micro-Compactor** (automatic) — retains only the last 3 `tool_result` blocks in full, replacing older ones with a short placeholder hint.
3. **`compact` tool** (agent-initiated or auto-triggered) — summarizes old user/assistant conversation turns into a single assistant message when the overall context still exceeds a token threshold.

This is the foundation for context management used throughout the project. For now it is intentionally minimal: no external summarization service, no cross-session persistence of summaries.

---

## Goals

- Prevent single large tool outputs (e.g., `cat huge.log`) from consuming the entire context window.
- Prevent accumulation of old tool results from crowding out recent conversation.
- Provide a mechanism (`compact` tool) for the Agent to summarize old conversation history when it grows too long.
- Keep the change surface small: reuse the existing `Tool` protocol, `ToolRegistry`, and `LoopState`.

---

## Non-Goals

- Cross-session persistence of compressed summaries.
- Automatic recursive summarization of summaries.
- Fine-grained per-tool output size configuration (a single global threshold is sufficient for now).
- Token counting via an external tokenizer library (we use a simple heuristic estimate).

---

## Architecture

```
原始 messages
    │
    ▼
[Layer 1] Persisted Output Manager（自动）
    单个 tool_result > 30000 字符？
    是 → 写入 .task_outputs/tool-results/<tool_use_id>.txt
          替换为 <persisted-output> 标记 + 预览
    │
    ▼
[Layer 2] Micro-Compactor（自动）
    tool_result 总数 > 3 个？
    是 → 将更早的 tool_result 内容替换为占位提示
         （保留最近 3 个完整内容）
    │
    ▼
[Layer 3] compact 工具
    如果整体上下文 still too large（token 阈值）：
    → 调用 Provider 生成摘要
    → 将旧 user/assistant 轮次合并为一条 assistant 摘要消息
    → 保留最近 N 条 assistant 消息（N 由 compact 参数决定）
    │
    ▼
normalize_messages() → API
```

**触发方式差异：**

- Layer 1 & 2：全自动，在 Agent 处理 tool_result 或准备调用 API 时执行，对模型透明。
- Layer 3：由模型主动调用 `compact` 工具触发（`auto` 模式下也可自动触发）。

---

## Data Model

### CompactState

```python
@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)
```

### PersistedOutput

```python
@dataclass
class PersistedOutput:
    tool_use_id: str
    file_path: str
    preview: str          # 前 500 字符的预览
    original_length: int
```

### LoopState Extension

```python
@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None
    max_turns: int | None = None
    compact_state: CompactState = field(default_factory=CompactState)
```

---

## Components

### PersistedOutputManager (`src/agent/context.py`)

Responsibilities:

- **`maybe_persist(tool_use_id: str, content: str) -> PersistedOutput | None`**
  1. If `len(content) <= 30000`, return `None`.
  2. Ensure `.task_outputs/tool-results/` directory exists.
  3. Write the full content to `.task_outputs/tool-results/{tool_use_id}.txt`.
  4. Return `PersistedOutput(tool_use_id, file_path, preview, len(content))`.

- **`_make_preview(content: str) -> str`**
  - Return the first 500 characters of the content.

Integration: Called inside `Agent._run_one_turn()` after each `tool_result` is produced. If a `PersistedOutput` is returned, the `content` field of that `tool_result` block is replaced with the following string:

```
<persisted-output>
Full output saved to: {file_path}
Preview:
{preview}
</persisted-output>
```

### MicroCompactor (`src/agent/context.py`)

Responsibilities:

- **`apply(messages: list[dict]) -> None`** (in-place mutation)
  1. Scan `messages` from beginning to end and collect all blocks with `type == "tool_result"`.
  2. If the total count of `tool_result` blocks is `<= 3`, do nothing.
  3. Otherwise, for all but the last 3 `tool_result` blocks, replace their `content` with the string `"(... older tool output omitted)"`.
  4. The replacement is idempotent: running `apply` twice on the same list produces the same result.

Integration: Called inside `Agent._run_one_turn()` after all tool results for the current turn have been appended to `messages`.

### CompactTool (`src/tools/compact_tool.py`)

Responsibilities:

- **Input Schema**

```json
{
  "type": "object",
  "properties": {
    "strategy": {
      "type": "string",
      "enum": ["auto", "force"],
      "description": "auto = compress only if token threshold exceeded; force = always compress.",
      "default": "auto"
    },
    "keep_last_assistant": {
      "type": "integer",
      "description": "Number of recent assistant messages to preserve verbatim.",
      "default": 3,
      "minimum": 1
    }
  }
}
```

- **`execute(tool_use_id, input) -> ToolResult`**
  1. Read `strategy` and `keep_last_assistant` from `input` (use defaults if missing).
  2. If `strategy == "auto"`:
     - Estimate current context token count (simple heuristic: total characters / 4).
     - If estimated tokens < 8000, return a text `ToolResult` saying "Current context is within the safe threshold; no compression needed."
  3. Build the list of messages to be summarized:
     - Identify the last `keep_last_assistant` assistant messages.
     - Everything before the first of those assistant messages is considered "old history".
  4. If there is no old history, return a text `ToolResult` saying "No old history to compress."
  5. Serialize old history into a flat text string.
  6. Call `Provider.chat()` with a summarization prompt:
     ```
     Summarize the following conversation history in a concise paragraph, preserving key decisions, file paths, and error states:
     
     {old_history_text}
     ```
  7. If the Provider call fails, return `ToolResult` with `is_error=True` and the error message.
  8. Replace the old history slice in `messages` with a single assistant message containing the summary text.
  9. Update `LoopState.compact_state`:
     - `has_compacted = True`
     - `last_summary = summary_text`
     - `recent_files` updated from the summary (optional heuristic)
  10. Return a text `ToolResult` with a confirmation message.

Integration: Registered in `ToolRegistry` in `cli.py`. The `CompactTool` instance receives a reference to the `Agent`'s `LoopState` (or at least `messages` and `compact_state`) at initialization time so it can mutate them in-place.

---

## Data Flow Example

Assume 5 rounds of interaction, where Round 1 produced a 50KB `bash` output.

```
Round 1: user("查看日志") → assistant(bash) → tool_result(50KB)
Round 2: user("grep error") → assistant(bash) → tool_result(1KB)
Round 3: user("分析第3行") → assistant(bash) → tool_result(2KB)
Round 4: user("修改配置") → assistant(bash) → tool_result(1KB)
Round 5: user("重启服务") → assistant(bash) → tool_result(500B)
```

**Layer 1 (during Round 1 tool_result processing):**
- 50KB > 30000 characters → `PersistedOutputManager.maybe_persist()` triggers.
- Writes to `.task_outputs/tool-results/abc123.txt`.
- The tool_result content becomes:
  ```
  <persisted-output>
  Full output saved to: .task_outputs/tool-results/abc123.txt
  Preview:
  [first 500 chars of the log]
  </persisted-output>
  ```

**Layer 2 (after Round 5 tool_results appended):**
- 5 tool_result blocks exist.
- Retain the last 3 (Rounds 3, 4, 5) in full.
- Replace Rounds 1 and 2 tool_result content with `"(... older tool output omitted)"`.

**Layer 3 (model calls `compact` with `keep_last_assistant=2`):**
- Retain Rounds 4 and 5 verbatim.
- Rounds 1-3 are old history.
- Provider generates summary: `"User first checked a large log file (output persisted to disk), then grepped for errors, and asked to analyze line 3."`
- Messages become:
  ```
  [assistant summary msg]
  [Round 4 user]
  [Round 4 assistant]
  [Round 4 tools]
  [Round 5 user]
  [Round 5 assistant]
  [Round 5 tools]
  ```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| PersistedOutputManager disk write fails | Retain original content, print warning to stderr, do not raise. |
| MicroCompactor finds no tool_result | No-op. |
| MicroCompactor applied twice on same messages | Idempotent: already-replaced content stays replaced. |
| `compact` auto mode, tokens below threshold | Return text `ToolResult`: "No compression needed." |
| `compact` keep_last_assistant >= actual assistant count | Return text `ToolResult`: "No old history to compress." |
| Provider summarization call fails | Return `ToolResult(is_error=True, content=error_msg)`; do not modify messages. |
| `compact` produces summary adjacent to another assistant msg | `normalize_messages()` merges them before API call. |

---

## Testing Strategy

- **Unit tests for `PersistedOutputManager`** (`tests/agent/test_context.py`):
  - Content above threshold triggers write and returns `PersistedOutput`.
  - Content below threshold returns `None`.
  - Disk write failure retains original content and prints warning.
  - Preview is exactly 500 characters.

- **Unit tests for `MicroCompactor`** (`tests/agent/test_context.py`):
  - Messages with 0-3 tool_results are unchanged.
  - Messages with 5 tool_results have the first 2 replaced with placeholders.
  - Repeated application is idempotent.
  - Mixed persisted and non-persisted tool_results behave correctly.

- **Unit tests for `CompactTool`** (`tests/tools/test_compact_tool.py`):
  - `auto` mode below token threshold returns "No compression needed."
  - `force` mode always compresses.
  - Correctly retains `keep_last_assistant` recent assistant messages.
  - Provider failure returns `is_error=True` and leaves messages untouched.
  - `compact_state` is updated after successful compression.

- **Integration tests** (`tests/agent/test_agent.py` or new `test_context_compression.py`):
  - After a large bash output, the corresponding `tool_result` contains `<persisted-output>`.
  - After 4 tool results, the oldest one contains a placeholder.
  - After calling `compact`, old history is replaced by a single assistant summary message.

---

## File Layout

```
src/
  agent/
    context.py              # NEW - PersistedOutputManager + MicroCompactor
    agent.py                # MODIFY - integrate Layer 1/2, extend LoopState
  tools/
    compact_tool.py         # NEW - CompactTool
  cli.py                    # MODIFY - register CompactTool, inject LoopState reference

tests/
  agent/
    test_context.py         # NEW - PersistedOutputManager + MicroCompactor tests
    test_agent.py           # MODIFY - add integration tests for compression pipeline
  tools/
    test_compact_tool.py    # NEW - CompactTool unit tests
```

---

## References

- Reference implementation pattern: [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) s06 chapter.
- Persisted output marker format and `CompactState` inspired by the reference implementation's minimal teaching version.
