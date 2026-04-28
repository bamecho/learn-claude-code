# s06 Context Compression Implementation Plan (Revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the existing three-layer context compression pipeline with the reference implementation: auto-compaction before API calls, transcript archiving, recent-file tracking, structured 5-point summary prompt, `focus` parameter, preview length 2000, micro-compactor min-length gate 120, and summary max_tokens=2000.

**Architecture:** Layer 1 (`PersistedOutputManager`) and Layer 2 (`MicroCompactor`) receive parameter tweaks. A new `HistoryCompactor` encapsulates auto/manual compaction logic (estimate size, write transcript, summarize, replace history). `Agent._agent_loop()` calls `HistoryCompactor.compact_history()` automatically when context exceeds 50KB. `CompactTool` delegates to `HistoryCompactor` and gains a `focus` parameter.

**Tech Stack:** Python 3.12, pytest, existing AnthropicProvider / ToolRegistry / Agent loop.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/agent/context.py` | **Modify** | `PersistedOutputManager.PREVIEW_LENGTH` 2000; `MicroCompactor` min-length gate; add `HistoryCompactor` + `track_recent_file` |
| `src/provider/base.py` | **Modify** | Add optional `max_tokens` to `LLMProvider.chat` protocol |
| `src/provider/anthropic_provider.py` | **Modify** | Accept and forward `max_tokens` kwarg |
| `src/agent/agent.py` | **Modify** | Auto-compaction in `_agent_loop`; `read_file` → `track_recent_file` |
| `src/tools/compact_tool.py` | **Modify** | Add `focus` parameter; use `HistoryCompactor`; 5-point prompt; `max_tokens=2000`; summary as `user` role |
| `tests/agent/test_context.py` | **Modify** | Update preview length test; add micro-compactor min-length tests; add HistoryCompactor unit tests |
| `tests/agent/test_agent.py` | **Modify** | Update compact role assertion; add auto-compaction integration test |
| `tests/tools/test_compact_tool.py` | **Modify** | Update role assertions; add `focus` parameter test |

---

### Task 1: Preview Length & Micro-Compactor Min-Length Gate

**Files:**
- Modify: `src/agent/context.py`
- Test: `tests/agent/test_context.py`

- [ ] **Step 1: Update PersistedOutputManager preview length**

In `src/agent/context.py`, change:
```python
    PREVIEW_LENGTH = 500
```
to:
```python
    PREVIEW_LENGTH = 2000
```

- [ ] **Step 2: Add MicroCompactor min-length gate**

In `src/agent/context.py`, in `MicroCompactor.apply`, change the replacement loop from:
```python
        for msg_idx, block_idx in tool_result_indices[:-cls.KEEP_LAST]:
            block = messages[msg_idx]["content"][block_idx]
            if block.get("content") != cls.PLACEHOLDER:
                block["content"] = cls.PLACEHOLDER
```
to:
```python
        for msg_idx, block_idx in tool_result_indices[:-cls.KEEP_LAST]:
            block = messages[msg_idx]["content"][block_idx]
            content = block.get("content", "")
            if isinstance(content, str) and len(content) > 120 and content != cls.PLACEHOLDER:
                block["content"] = cls.PLACEHOLDER
```

- [ ] **Step 3: Update preview test**

In `tests/agent/test_context.py`, change:
```python
    def test_preview_is_first_500_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "b" * 1000
            result = mgr.maybe_persist("id2", content)
            assert result.preview == "b" * 500
```
to:
```python
    def test_preview_is_first_2000_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "b" * 3000
            result = mgr.maybe_persist("id2", content)
            assert result.preview == "b" * 2000
```

- [ ] **Step 4: Add micro-compactor min-length test**

Append to `tests/agent/test_context.py`:
```python
    def test_short_tool_results_left_untouched(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "x"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "also short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "y"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": "still short"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "short"
        assert msgs[1]["content"][0]["content"] == "x"
        assert msgs[2]["content"][0]["content"] == "also short"
        assert msgs[3]["content"][0]["content"] == "y"
        assert msgs[4]["content"][0]["content"] == "still short"

    def test_long_tool_results_replaced_short_kept(self):
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == "short"  # <= 120 chars
        assert msgs[2]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[3]["content"][0]["content"] == long_text
        assert msgs[4]["content"][0]["content"] == long_text
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/agent/test_context.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agent/context.py tests/agent/test_context.py
git commit -m "feat(agent): increase preview to 2000 and add micro-compactor min-length gate"
```

---

### Task 2: Provider Protocol max_tokens Support

**Files:**
- Modify: `src/provider/base.py`
- Modify: `src/provider/anthropic_provider.py`
- Test: `tests/provider/test_anthropic_provider.py` (add a quick test)

- [ ] **Step 1: Update protocol**

In `src/provider/base.py`, change:
```python
    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None) -> LLMResponse:
```
to:
```python
    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None, max_tokens: int | None = None) -> LLMResponse:
```

- [ ] **Step 2: Update AnthropicProvider**

In `src/provider/anthropic_provider.py`, change:
```python
    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None) -> LLMResponse:
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 4096,
            }
            if tools:
                kwargs["tools"] = tools
            if system:
                kwargs["system"] = system
```
to:
```python
    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None, max_tokens: int | None = None) -> LLMResponse:
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens if max_tokens is not None else 4096,
            }
            if tools:
                kwargs["tools"] = tools
            if system:
                kwargs["system"] = system
```

- [ ] **Step 3: Run provider tests**

Run: `pytest tests/provider/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/provider/base.py src/provider/anthropic_provider.py
git commit -m "feat(provider): add optional max_tokens parameter to chat protocol"
```

---

### Task 3: Add HistoryCompactor & track_recent_file

**Files:**
- Modify: `src/agent/context.py`
- Test: `tests/agent/test_context.py`

- [ ] **Step 1: Add imports and new functions/classes**

Append to `src/agent/context.py` (after existing content):

```python
import json
import time
from pathlib import Path


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
        # Extract text from response
        summary_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                summary_text = block.text
                break
        return summary_text.strip()

    @classmethod
    def compact_history(cls, messages: list, state, provider, focus: str | None = None) -> list:
        transcript_path = cls.write_transcript(messages)
        print(f"[transcript saved: {transcript_path}]")
        summary = cls.summarize_history(provider, messages)
        if focus:
            summary += f"\n\nFocus to preserve next: {focus}"
        if state.recent_files:
            recent_lines = "\n".join(f"- {path}" for path in state.recent_files)
            summary += f"\n\nRecent files to reopen if needed:\n{recent_lines}"
        state.has_compacted = True
        state.last_summary = summary
        return [{
            "role": "user",
            "content": (
                "This conversation was compacted so the agent can continue working.\n\n"
                f"{summary}"
            ),
        }]
```

- [ ] **Step 2: Add HistoryCompactor unit tests**

Append to `tests/agent/test_context.py`:

```python
from unittest.mock import MagicMock
from src.agent.context import HistoryCompactor, track_recent_file, CompactState


class TestTrackRecentFile:
    def test_adds_file_and_caps_at_five(self):
        state = CompactState()
        for i in range(7):
            track_recent_file(state, f"file{i}.py")
        assert state.recent_files == [
            "file2.py", "file3.py", "file4.py", "file5.py", "file6.py"
        ]

    def test_moves_existing_file_to_end(self):
        state = CompactState()
        track_recent_file(state, "a.py")
        track_recent_file(state, "b.py")
        track_recent_file(state, "a.py")
        assert state.recent_files == ["b.py", "a.py"]


class TestHistoryCompactor:
    def test_estimate_context_size(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        size = HistoryCompactor.estimate_context_size(msgs)
        assert size == len(str(msgs))

    def test_write_transcript_creates_jsonl(self, tmp_path):
        import os
        orig_dir = HistoryCompactor.TRANSCRIPT_DIR
        HistoryCompactor.TRANSCRIPT_DIR = tmp_path / ".transcripts"
        try:
            msgs = [{"role": "user", "content": "test"}]
            path = HistoryCompactor.write_transcript(msgs)
            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1
            assert json.loads(lines[0]) == msgs[0]
        finally:
            HistoryCompactor.TRANSCRIPT_DIR = orig_dir

    def test_summarize_history_extracts_text(self):
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary text.")]
        )
        result = HistoryCompactor.summarize_history(provider, [])
        assert result == "Summary text."
        call_args = provider.chat.call_args
        assert call_args.kwargs["max_tokens"] == 2000

    def test_compact_history_replaces_messages(self):
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Compact summary.")]
        )
        state = CompactState()
        state.recent_files = ["main.py", "utils.py"]
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
        ]
        new_msgs = HistoryCompactor.compact_history(msgs, state, provider, focus="fix bug")
        assert len(new_msgs) == 1
        assert new_msgs[0]["role"] == "user"
        assert "Compact summary." in new_msgs[0]["content"]
        assert "fix bug" in new_msgs[0]["content"]
        assert "main.py" in new_msgs[0]["content"]
        assert state.has_compacted is True
        assert state.last_summary.startswith("Compact summary.")
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/agent/test_context.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agent/context.py tests/agent/test_context.py
git commit -m "feat(agent): add HistoryCompactor, track_recent_file, and transcript archiving"
```

---

### Task 4: Wire Auto-Compaction & recent_files into Agent Loop

**Files:**
- Modify: `src/agent/agent.py`
- Test: `tests/agent/test_agent.py`

- [ ] **Step 1: Update imports**

In `src/agent/agent.py`, change:
```python
from src.agent.context import CompactState, MicroCompactor, PersistedOutputManager
```
to:
```python
from src.agent.context import CompactState, MicroCompactor, PersistedOutputManager, HistoryCompactor, track_recent_file
```

- [ ] **Step 2: Add auto-compaction before API call**

In `src/agent/agent.py`, in `_run_one_turn`, before the line:
```python
        tools = self.registry.to_anthropic_format()
        response = self.provider.chat(normalize_messages(state.messages), tools, system=self.system)
```
Insert:
```python
        # Auto-compact if context is too large
        if HistoryCompactor.estimate_context_size(state.messages) > HistoryCompactor.CONTEXT_LIMIT:
            print("[auto compact]")
            state.messages[:] = HistoryCompactor.compact_history(
                state.messages, state.compact_state, self.provider
            )
```

- [ ] **Step 3: Track recent files on read_file**

In `src/agent/agent.py`, in `_run_one_turn`, inside the `for tu in tool_uses:` loop, after:
```python
                else:
                    result = tool.execute(tu.id, tu.input or {})
```
Insert:
```python
                if tu.name == "read_file":
                    path = tu.input.get("filePath") if isinstance(tu.input, dict) else None
                    if path:
                        track_recent_file(self.compact_state, path)
```

- [ ] **Step 4: Add auto-compaction integration test**

Append to `tests/agent/test_agent.py`:

```python
    def test_auto_compact_triggers_when_context_too_large(self):
        from src.agent.context import HistoryCompactor

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        small_output = "x"
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="tx", content=small_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(
            content=[ContentBlock(type="tool_use", id="t1", name="mock_tool", input={})],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry)
        # Seed messages with a huge string to trigger auto-compaction
        agent.messages = [{"role": "user", "content": "x" * 60000}]

        agent._run_turn("run mock", max_turns=1)

        # The first provider.chat call should have been the summarization (no tools)
        # The second provider.chat call is the actual turn
        calls = provider.chat.call_args_list
        assert len(calls) >= 1
        # First call is the auto-compact summary
        first_call_messages = calls[0].kwargs.get("messages", calls[0].args[0])
        assert any("Summarize" in str(m.get("content", "")) for m in first_call_messages)
        assert agent.compact_state.has_compacted is True
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/agent/test_agent.py -v`
Expected: PASS (some existing tests may need updating in Task 6)

- [ ] **Step 6: Commit**

```bash
git add src/agent/agent.py tests/agent/test_agent.py
git commit -m "feat(agent): wire auto-compaction and recent-file tracking into loop"
```

---

### Task 5: Update CompactTool with focus, 5-point Prompt, and User-Role Summary

**Files:**
- Modify: `src/tools/compact_tool.py`
- Test: `tests/tools/test_compact_tool.py`

- [ ] **Step 1: Refactor CompactTool to use HistoryCompactor and add focus**

Replace the contents of `src/tools/compact_tool.py` with:

```python
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

        # Use HistoryCompactor for the actual compaction
        compacted = HistoryCompactor.compact_history(
            old_history, self.compact_state, self.provider, focus=focus
        )

        # Replace messages: compacted summary + preserved recent turns
        self.messages[:] = [*compacted, *preserved]

        summary_text = self.compact_state.last_summary
        return ToolResult(
            tool_use_id=tool_use_id,
            content=f"Context compressed. Summary: {summary_text[:200]}...",
        )
```

- [ ] **Step 2: Update test assertions for user-role summary**

In `tests/tools/test_compact_tool.py`, update all tests that assert `messages[0]["role"] == "assistant"` to `"user"`, and check for the prefixed content.

Changes needed:

1. `test_auto_mode_above_threshold_compresses`:
```python
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert "Summary: long conversation." in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert "Summary: long conversation." in compact_state.last_summary
```

2. `test_force_mode_compresses`:
```python
        assert len(messages) == 2  # summary + recent
        assert messages[0]["role"] == "user"
        assert "Summary: user said hello." in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert "Summary: user said hello." in compact_state.last_summary
```

3. Add a new `focus` test:
```python
    def test_focus_parameter_included_in_summary(self):
        messages = [
            {"role": "user", "content": "old user msg"},
            {"role": "assistant", "content": "old assistant msg"},
            {"role": "user", "content": "recent user msg"},
            {"role": "assistant", "content": "recent assistant msg"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary: focused.")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1, "focus": "auth bug"})
        assert not result.is_error
        assert messages[0]["role"] == "user"
        assert "auth bug" in messages[0]["content"]
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_compact_tool.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/compact_tool.py tests/tools/test_compact_tool.py
git commit -m "feat(tools): add focus param to CompactTool, use HistoryCompactor, user-role summary"
```

---

### Task 6: Update Agent Integration Test for User-Role Summary

**Files:**
- Modify: `tests/agent/test_agent.py`

- [ ] **Step 1: Update test_compact_tool_replaces_old_history**

In `tests/agent/test_agent.py`, in `test_compact_tool_replaces_old_history`, change:
```python
        assert len(agent.messages) == 2
        assert agent.messages[0]["role"] == "assistant"
        assert agent.messages[0]["content"] == "Summary of old history."
```
to:
```python
        assert len(agent.messages) == 2
        assert agent.messages[0]["role"] == "user"
        assert "Summary of old history." in agent.messages[0]["content"]
```

Also change:
```python
        assert agent.messages[1]["role"] == "assistant"
        assert agent.messages[1]["content"] == "recent assistant"
```
to:
```python
        assert agent.messages[1]["role"] == "assistant"
        assert agent.messages[1]["content"] == "recent assistant"
```
(This part stays the same, but verify it passes.)

- [ ] **Step 2: Run all agent tests**

Run: `pytest tests/agent/test_agent.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_agent.py
git commit -m "test(agent): update compact integration test for user-role summary"
```

---

### Task 7: Full Test Suite Verification

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Commit if any last fixes were needed**

(Only if fixes were made.)

---

## Self-Review

**1. Spec coverage:**

| Spec Requirement | Plan Task |
|------------------|-----------|
| Preview length 2000 | Task 1 |
| MicroCompactor min-length gate 120 | Task 1 |
| Auto-compaction before API calls (50KB) | Task 4 |
| Transcript archiving | Task 3 |
| `track_recent_file` on read | Task 4 |
| `focus` parameter on compact tool | Task 5 |
| Structured 5-point summary prompt | Task 3 |
| `max_tokens=2000` on summary | Task 2 + Task 3 |
| Summary as `user` role | Task 5 + Task 6 |

All requirements covered.

**2. Placeholder scan:**
- No "TBD", "TODO", or vague steps.
- All code blocks contain complete, runnable code.
- Test assertions match the new `user`-role summary format.

**3. Type consistency:**
- `HistoryCompactor.compact_history` returns `list[dict]` consistent with how `Agent` and `CompactTool` consume it.
- `track_recent_file` accepts `CompactState` (same type used elsewhere).
- `max_tokens: int | None` added consistently to protocol and implementation.

No issues found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-s06-context-compression-revised.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** - Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach?**
