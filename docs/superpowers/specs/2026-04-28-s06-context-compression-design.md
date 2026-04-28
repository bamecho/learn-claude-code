# s06 Context Compression Design (Revised)

## Overview

`s06` introduces a three-layer context compression pipeline to prevent the Agent's conversation history from growing unbounded and exhausting the model's context window. The pipeline is progressive: each layer addresses a different class of bloat, and later layers only activate when earlier ones are insufficient.

The pipeline consists of:

1. **Persisted Output Manager** (automatic) — writes oversized individual tool outputs to disk and replaces them with a lightweight preview marker.
2. **Micro-Compactor** (automatic) — retains only the last 3 `tool_result` blocks in full, replacing older ones with a short placeholder hint (only if the original content is longer than 120 characters).
3. **History Compactor** (auto-triggered + agent-initiated) — when the overall context exceeds a safe size limit, the agent automatically summarizes old conversation turns before calling the API. The model can also manually trigger compaction via the `compact` tool to force an immediate summary or provide a `focus` hint.

This revision aligns the implementation with the reference teaching version while preserving useful existing parameters (`strategy`, `keep_last_assistant`).

---

## Goals

- Prevent single large tool outputs (e.g., `cat huge.log`) from consuming the entire context window.
- Prevent accumulation of old tool results from crowding out recent conversation.
- **Automatically** keep the active context small enough to keep working by checking size before every API call.
- Preserve a transcript of the full conversation before summarization for auditability.
- Track recently accessed files so summaries can remind the agent to reopen them if needed.
- Keep the change surface small: reuse the existing `Tool` protocol, `ToolRegistry`, and `LoopState`.

---

## Non-Goals

- Cross-session persistence of compressed summaries.
- Automatic recursive summarization of summaries.
- Fine-grained per-tool output size configuration (a single global threshold is sufficient for now).
- Token counting via an external tokenizer library (we use a simple character-based heuristic).

---

## Architecture

```
原始 messages
    │
    ▼
[Layer 1] Persisted Output Manager（自动，每轮工具执行后）
    单个 tool_result > 30000 字符？
    是 → 写入 .task_outputs/tool-results/<tool_use_id>.txt
          替换为 <persisted-output> 标记 + 2000 字符预览
    │
    ▼
[Layer 2] Micro-Compactor（自动，每轮工具结果追加后）
    tool_result 总数 > 3 个？
    是 → 将更早的 tool_result 中长度 >120 的内容替换为占位提示
         （保留最近 3 个完整内容）
    │
    ▼
[Layer 3a] Auto History Compaction（自动，每次 API 调用前）
    estimate_context_size(messages) > 50000 字符？
    是 → 保存 transcript → 生成 summary → 替换旧历史
    │
    ▼
[Layer 3b] compact 工具（手动触发）
    strategy='force' 或 agent 主动调用
    → 同 Layer 3a 流程，可额外传入 focus
    │
    ▼
normalize_messages() → API
```

**触发方式差异：**

- Layer 1 & 2：全自动，在 Agent 处理 tool_result 或准备调用 API 时执行，对模型透明。
- Layer 3a：全自动，在 `_agent_loop` 每次迭代调用 API 前检查上下文大小。
- Layer 3b：由模型主动调用 `compact` 工具触发，提供额外控制（如 `focus`）。

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
@dataclass(frozen=True)
class PersistedOutput:
    tool_use_id: str
    file_path: str
    preview: str          # 前 2000 字符的预览
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
  3. Write the full content to `.task_outputs/tool-results/{safe_id}.txt`.
  4. Return `PersistedOutput(tool_use_id, file_path, preview, len(content))`.

- **`_make_preview(content: str) -> str`**
  - Return the first 2000 characters of the content.

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
  3. Otherwise, for all but the last 3 `tool_result` blocks, if their `content` is a string and `len(content) > 120`, replace it with the string `"(... older tool output omitted)"`.
  4. The replacement is idempotent: running `apply` twice on the same list produces the same result.

Integration: Called inside `Agent._run_one_turn()` after all tool results for the current turn have been appended to `messages`.

### HistoryCompactor (`src/agent/context.py`)

Responsibilities:

- **`estimate_context_size(messages: list) -> int`**
  - Return `len(str(messages))` as a cheap proxy for token count.

- **`write_transcript(messages: list) -> Path`**
  - Ensure `.transcripts/` directory exists.
  - Write each message as one JSON line to `.transcripts/transcript_{timestamp}.jsonl`.
  - Return the written file path.

- **`summarize_history(provider, messages: list, max_tokens: int = 2000) -> str`**
  - Serialize the messages (truncated to 80000 chars to stay within prompt limits).
  - Send a structured prompt to the provider:
    ```
    Summarize this coding-agent conversation so work can continue.
    Preserve:
    1. The current goal
    2. Important findings and decisions
    3. Files read or changed
    4. Remaining work
    5. User constraints and preferences
    Be compact but concrete.
    ```
  - Return the generated summary text.

- **`compact_history(messages: list, state: CompactState, provider, focus: str | None = None) -> list`**
  1. Call `write_transcript(messages)` and print the path.
  2. Call `summarize_history(provider, messages)`.
  3. If `focus` is provided, append `"\n\nFocus to preserve next: {focus}"`.
  4. If `state.recent_files` is non-empty, append a list of recent files.
  5. Update `state.has_compacted = True` and `state.last_summary = summary`.
  6. Return a new single-message list:
     ```
     {"role": "user", "content": "This conversation was compacted so the agent can continue working.\n\n{summary}"}
     ```

Integration: Called in two places:
- **Auto**: Inside `Agent._agent_loop()` before each `provider.chat()` call when `estimate_context_size > 50000`.
- **Manual**: Inside `CompactTool.execute()` when `strategy == "force"` (or `auto` with threshold exceeded).

### CompactTool (`src/tools/compact_tool.py`)

Responsibilities:

- **Input Schema** (extended to include `focus` while keeping existing useful parameters):

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
    },
    "focus": {
      "type": "string",
      "description": "Optional focus area or topic to preserve in the summary.",
      "default": ""
    }
  }
}
```

- **`execute(tool_use_id, input) -> ToolResult`**
  1. Read `strategy`, `keep_last_assistant`, and `focus` from `input`.
  2. If `strategy == "auto"`: estimate context size; if below threshold, return a no-op message.
  3. Identify old history using `keep_last_assistant` (same logic as before).
  4. Call `HistoryCompactor.compact_history()` with the optional `focus`.
  5. Replace old history with a single `user` message containing the summary, followed by the preserved recent turns.
  6. Return a confirmation `ToolResult`.

### File Tool Integration (`src/tools/file_tools.py`)

Responsibilities:

- **`ReadFileTool.execute()`** — after successfully reading a file, call `track_recent_file(state, path)` on the agent's `CompactState`.
- This requires `ReadFileTool` to receive a reference to `CompactState`, or the caller (`Agent`) to update it after the read. The cleaner approach: `Agent._run_one_turn()` detects `read_file` tool usage and updates `self.compact_state.recent_files` via `track_recent_file()`.

Integration: In `Agent._run_one_turn()`, after a tool result is produced:
```python
if tu.name == "read_file":
    path = tu.input.get("filePath")
    if path:
        track_recent_file(self.compact_state, path)
```

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
  [first 2000 chars of the log]
  </persisted-output>
  ```

**Layer 2 (after Round 5 tool_results appended):**
- 5 tool_result blocks exist.
- Retain the last 3 (Rounds 3, 4, 5) in full.
- Replace Rounds 1 and 2 tool_result content with `(... older tool output omitted)` (assuming they exceed 120 chars).

**Layer 3 (before next API call, context size > 50000):**
- `write_transcript()` saves full history to `.transcripts/transcript_1234567890.jsonl`.
- `summarize_history()` generates a structured summary preserving goal, findings, files, remaining work, and constraints.
- Recent files tracked by `ReadFileTool` are appended.
- Messages are replaced with a single compacted user message containing the summary.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| PersistedOutputManager disk write fails | Retain original content, print warning to stderr, do not raise. |
| MicroCompactor finds no tool_result | No-op. |
| MicroCompactor applied twice on same messages | Idempotent: already-replaced content stays replaced. |
| HistoryCompactor auto mode, size below threshold | No-op; proceed to API call normally. |
| `compact` auto mode, tokens below threshold | Return text `ToolResult`: "Current context is within the safe threshold; no compression needed." |
| `compact` keep_last_assistant >= actual assistant count | Return text `ToolResult`: "No old history to compress." |
| Provider summarization call fails | Return `ToolResult(is_error=True, content=error_msg)`; do not modify messages. |
| `compact` produces summary adjacent to another assistant msg | `normalize_messages()` merges them before API call. |

---

## Testing Strategy

- **Unit tests for `PersistedOutputManager`** (`tests/agent/test_context.py`):
  - Content above threshold triggers write and returns `PersistedOutput`.
  - Content below threshold returns `None`.
  - Disk write failure retains original content and prints warning.
  - Preview is exactly 2000 characters.

- **Unit tests for `MicroCompactor`** (`tests/agent/test_context.py`):
  - Messages with 0-3 tool_results are unchanged.
  - Messages with 5 tool_results have the first 2 replaced with placeholders (if content > 120 chars).
  - Short tool results (<= 120 chars) are left untouched even if old.
  - Repeated application is idempotent.

- **Unit tests for `HistoryCompactor`** (`tests/agent/test_context.py`):
  - `estimate_context_size` returns correct length.
  - `write_transcript` produces a valid `.jsonl` file.
  - `summarize_history` sends the structured 5-point prompt.
  - `compact_history` appends `focus` and `recent_files` when present.

- **Unit tests for `CompactTool`** (`tests/tools/test_compact_tool.py`):
  - `auto` mode below token threshold returns "No compression needed."
  - `force` mode always compresses.
  - `focus` parameter is forwarded to the summary.
  - Correctly retains `keep_last_assistant` recent assistant messages.
  - Provider failure returns `is_error=True` and leaves messages untouched.
  - `compact_state` is updated after successful compression.

- **Integration tests** (`tests/agent/test_agent.py`):
  - After a large bash output, the corresponding `tool_result` contains `<persisted-output>`.
  - After 4 tool results, the oldest one contains a placeholder.
  - After context exceeds threshold, auto-compaction triggers and replaces old history.
  - After calling `compact` with `focus`, the summary includes the focus text.

---

## File Layout

```
src/
  agent/
    context.py              # MODIFY - add HistoryCompactor, track_recent_file, update defaults
    agent.py                # MODIFY - integrate auto-compaction, transcript, recent_files
  tools/
    compact_tool.py         # MODIFY - add focus parameter, use HistoryCompactor
  cli.py                    # MODIFY - register CompactTool (no changes needed if already registered)

tests/
  agent/
    test_context.py         # MODIFY - update preview length and micro-compactor tests
    test_agent.py           # MODIFY - add auto-compaction and focus tests
  tools/
    test_compact_tool.py    # MODIFY - add focus parameter tests
```

---

## Key Revisions from Previous Design

| Change | Rationale |
|--------|-----------|
| **Preview length: 2000** (was 500) | 500 characters is too short for meaningful preview; 2000 matches the reference implementation. |
| **MicroCompactor min-length gate: 120 chars** | Avoid replacing already-short tool results with a placeholder that may be longer. |
| **Auto History Compaction before API calls** | The core teaching goal: keep active context small automatically. Relying solely on the model to call `compact` is unreliable. |
| **Transcript archive before compaction** | Preserve full audit trail before summarization. |
| **`track_recent_file` on read** | Include recently accessed files in the summary so the agent knows what to reopen. |
| **Structured 5-point summary prompt** | Higher-quality summaries that preserve actionable context (goal, findings, files, remaining work, constraints). |
| **`focus` parameter on `compact` tool** | Allows the agent to hint at what should be preserved, improving summary relevance. |
| **`max_tokens=2000` on summary call** | Prevents runaway token usage during summarization. |

---

## References

- Reference implementation pattern: [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) s06 chapter.
- Persisted output marker format and `CompactState` inspired by the reference implementation's minimal teaching version.
