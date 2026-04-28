# s06 Context Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a three-layer context compression pipeline (persisted output, micro-compaction, and `compact` tool) to prevent conversation history from exhausting the model's context window.

**Architecture:** Layer 1 (`PersistedOutputManager`) and Layer 2 (`MicroCompactor`) are automatic utilities living in `src/agent/context.py` and invoked by the Agent loop. Layer 3 is a `compact` tool registered in `ToolRegistry` that the model can call to summarize old conversation history via the LLM provider.

**Tech Stack:** Python 3.12, pytest, existing AnthropicProvider / ToolRegistry / Agent loop.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/agent/context.py` | **Create** | `PersistedOutputManager` (Layer 1) and `MicroCompactor` (Layer 2) |
| `src/tools/compact_tool.py` | **Create** | `CompactTool` implementing the `Tool` protocol (Layer 3) |
| `src/agent/agent.py` | **Modify** | Extend `LoopState` with `CompactState`; wire Layer 1 & 2 into `_run_one_turn()` |
| `src/cli.py` | **Modify** | Register `CompactTool` in `ToolRegistry` |
| `tests/agent/test_context.py` | **Create** | Unit tests for `PersistedOutputManager` and `MicroCompactor` |
| `tests/tools/test_compact_tool.py` | **Create** | Unit tests for `CompactTool` |
| `tests/agent/test_agent.py` | **Modify** | Integration tests for the full compression pipeline |

---

### Task 1: PersistedOutputManager

**Files:**
- Create: `src/agent/context.py`
- Test: `tests/agent/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import tempfile
import pytest
from src.agent.context import PersistedOutputManager


class TestPersistedOutputManager:
    def test_small_content_returns_none(self):
        mgr = PersistedOutputManager()
        result = mgr.maybe_persist("id1", "x" * 100)
        assert result is None

    def test_large_content_persists_and_returns_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "a" * 50
            result = mgr.maybe_persist("id1", content)
            assert result is not None
            assert result.tool_use_id == "id1"
            assert result.original_length == 50
            assert os.path.exists(result.file_path)
            with open(result.file_path, "r") as f:
                assert f.read() == content

    def test_preview_is_first_500_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "b" * 1000
            result = mgr.maybe_persist("id2", content)
            assert result.preview == "b" * 500

    def test_write_failure_retains_original(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            # Create a file where the directory should be to cause write failure
            os.makedirs(os.path.join(tmpdir, "tool-results"), exist_ok=True)
            target = os.path.join(tmpdir, "tool-results", "id3.txt")
            with open(target, "w") as f:
                f.write("blocker")
            # Make file read-only dir to simulate failure... just mock instead
```

Hmm, the write-failure test is hard to make deterministic without mocking `open`. We can skip the exact disk-failure assertion in the first pass and cover it later with a mock, or we can use `unittest.mock.patch` to simulate an `OSError` on `open`. Keep it simple: use `mock.patch`.

```python
    def test_write_failure_prints_warning(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            with pytest.MonkeyPatch().context() as m:
                from unittest.mock import patch
                with patch("builtins.open", side_effect=OSError("disk full")):
                    result = mgr.maybe_persist("id3", "x" * 50)
                assert result is None
                captured = capsys.readouterr()
                assert "Warning" in captured.err or "persist" in captured.err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agent.context'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent/context.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_context.py src/agent/context.py
git commit -m "feat(agent): add PersistedOutputManager for large tool outputs"
```

---

### Task 2: MicroCompactor

**Files:**
- Modify: `src/agent/context.py`
- Test: `tests/agent/test_context.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/agent/test_context.py`:

```python
from src.agent.context import MicroCompactor


class TestMicroCompactor:
    def test_no_tool_results_unchanged(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        MicroCompactor.apply(msgs)
        assert msgs == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

    def test_three_or_fewer_tool_results_unchanged(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "out1"
        assert msgs[1]["content"][0]["content"] == "out2"
        assert msgs[2]["content"][0]["content"] == "out3"

    def test_older_tool_results_replaced(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "out4"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": "out5"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[2]["content"][0]["content"] == "out3"
        assert msgs[3]["content"][0]["content"] == "out4"
        assert msgs[4]["content"][0]["content"] == "out5"

    def test_idempotent(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "out4"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        first = msgs[0]["content"][0]["content"]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_context.py::TestMicroCompactor -v`
Expected: FAIL with `AttributeError: module 'src.agent.context' has no attribute 'MicroCompactor'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/agent/context.py`:

```python
class MicroCompactor:
    KEEP_LAST = 3
    PLACEHOLDER = "(... older tool output omitted)"

    @classmethod
    def apply(cls, messages: list[dict]) -> None:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_context.py::TestMicroCompactor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_context.py src/agent/context.py
git commit -m "feat(agent): add MicroCompactor to keep only last 3 tool results"
```

---

### Task 3: CompactState and LoopState Extension

**Files:**
- Modify: `src/agent/agent.py`

- [ ] **Step 1: Modify `LoopState` to include `CompactState`**

In `src/agent/agent.py`, update the `LoopState` dataclass:

```python
from dataclasses import dataclass, field
from src.agent.context import CompactState


@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None
    max_turns: int | None = None
    compact_state: CompactState = field(default_factory=CompactState)
```

Note: We also need to add `CompactState` to `src/agent/context.py` since `LoopState` imports it. We'll add it there in the same commit.

- [ ] **Step 2: Add `CompactState` to `src/agent/context.py`**

Append to `src/agent/context.py`:

```python
@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add src/agent/context.py src/agent/agent.py
git commit -m "feat(agent): extend LoopState with CompactState"
```

---

### Task 4: Wire Layer 1 & 2 into Agent Loop

**Files:**
- Modify: `src/agent/agent.py`

- [ ] **Step 1: Import utilities and initialize in `Agent.__init__`**

In `src/agent/agent.py`:

```python
from src.agent.context import PersistedOutputManager, MicroCompactor
```

In `Agent.__init__`:

```python
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
        self.persisted_output_manager = PersistedOutputManager()
```

- [ ] **Step 2: Apply Layer 1 inside `_run_one_turn`**

After each `tool_result` block is built (around line 195 in the current `agent.py`), wrap the content:

Current code:
```python
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_use_id,
                    "content": result.content,
                    "is_error": result.is_error,
                })
```

Replace with:
```python
                content = result.content
                persisted = self.persisted_output_manager.maybe_persist(
                    result.tool_use_id, content
                )
                if persisted is not None:
                    content = (
                        f"<persisted-output>\n"
                        f"Full output saved to: {persisted.file_path}\n"
                        f"Preview:\n"
                        f"{persisted.preview}\n"
                        f"</persisted-output>"
                    )

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_use_id,
                    "content": content,
                    "is_error": result.is_error,
                })
```

- [ ] **Step 3: Apply Layer 2 after tool results are appended to messages**

After the line:
```python
            state.messages.append({"role": "user", "content": tool_result_blocks})
```

Add:
```python
            MicroCompactor.apply(state.messages)
```

- [ ] **Step 4: Run existing tests**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS. The new behavior is transparent to existing flows because `maybe_persist` returns `None` for small content and `MicroCompactor` is a no-op when there are <=3 tool_results.

- [ ] **Step 5: Commit**

```bash
git add src/agent/agent.py
git commit -m "feat(agent): wire PersistedOutputManager and MicroCompactor into loop"
```

---

### Task 5: CompactTool

**Files:**
- Create: `src/tools/compact_tool.py`
- Test: `tests/tools/test_compact_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import MagicMock
from src.tools.compact_tool import CompactTool
from src.tools.base import ToolResult
from src.agent.context import CompactState


class TestCompactTool:
    def test_auto_mode_below_threshold_returns_noop(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "auto"})
        assert "no compression needed" in result.content.lower() or "within" in result.content.lower()
        assert not result.is_error

    def test_force_mode_compresses(self):
        messages = [
            {"role": "user", "content": "old user msg"},
            {"role": "assistant", "content": "old assistant msg"},
            {"role": "user", "content": "recent user msg"},
            {"role": "assistant", "content": "recent assistant msg"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary: user said hello.")]
        )
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert not result.is_error
        assert len(messages) == 2  # summary + recent
        assert messages[0]["role"] == "assistant"
        assert "Summary" in messages[0]["content"]
        assert compact_state.has_compacted is True
        assert compact_state.last_summary == "Summary: user said hello."

    def test_provider_failure_returns_error(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        provider.chat.side_effect = RuntimeError("network down")
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert result.is_error
        assert "network down" in result.content
        assert not compact_state.has_compacted

    def test_keep_last_assistant_equal_to_total_returns_noop(self):
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        compact_state = CompactState()
        provider = MagicMock()
        tool = CompactTool(provider, messages, compact_state)
        result = tool.execute("tid", {"strategy": "force", "keep_last_assistant": 1})
        assert "no old history" in result.content.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/tools/test_compact_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.compact_tool'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/compact_tool.py
from dataclasses import dataclass, field
from src.tools.base import ToolResult
from src.provider.base import LLMProvider
from src.agent.context import CompactState


@dataclass
class CompactTool:
    name: str = "compact"
    description: str = (
        "Compress conversation history by summarizing old messages. "
        "Use strategy='auto' to compress only when context is large, "
        "or strategy='force' to compress immediately."
    )
    input_schema: dict = field(default_factory=lambda: {
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
    })

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

        # Identify assistant message indices
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

        # Replace old history with a single assistant summary message
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/tools/test_compact_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/tools/test_compact_tool.py src/tools/compact_tool.py
git commit -m "feat(tools): add CompactTool for conversation history summarization"
```

---

### Task 6: Register CompactTool in CLI

**Files:**
- Modify: `src/cli.py`

- [ ] **Step 1: Import and register**

In `src/cli.py`, add import:
```python
from src.tools.compact_tool import CompactTool
```

After `registry.register(SkillTool(skill_registry))`, add:
```python
    registry.register(CompactTool(provider, agent.messages, agent.compact_state))
```

Wait — `agent` is created *after* the registry is populated. We need to reverse the order slightly, or inject after agent creation. The cleanest way: create the agent first (it already initializes its own `messages` and `compact_state`), then create `CompactTool` with those references, then register it.

But `Agent` constructor takes `registry`. So we can:
1. Create registry.
2. Create agent with registry.
3. Create `CompactTool(agent.provider, agent.messages, agent.compact_state)` and register it into the same registry.

Modify `src/cli.py` as follows:

```python
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(TodoTool())
    registry.register(TaskTool(provider, registry, system=system, subagent_system=subagent_system))
    registry.register(SkillTool(skill_registry))

    agent = Agent(provider, registry, system=system)
    registry.register(CompactTool(provider, agent.messages, agent.compact_state))
```

We also need to expose `compact_state` as an attribute on `Agent`. Since `LoopState` now has `compact_state`, and `_run_turn` creates a `LoopState`, the agent doesn't hold a permanent `compact_state` — each turn gets a fresh `LoopState`. That's a problem: `CompactTool` needs a stable reference to the state.

Solution: `Agent` should hold a persistent `CompactState` instance, and `_run_turn` copies it into `LoopState` (or references it). Simpler: add `self.compact_state = CompactState()` to `Agent.__init__`, and in `_run_turn` use `state.compact_state = self.compact_state`.

Let's update `Agent.__init__` and `_run_turn`:

In `Agent.__init__`:
```python
        self.compact_state = CompactState()
```

In `_run_turn`:
```python
        state = LoopState(messages=self.messages, max_turns=max_turns)
        state.compact_state = self.compact_state
        self._agent_loop(state)
```

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add src/cli.py src/agent/agent.py
git commit -m "feat(cli): register CompactTool and expose compact_state on Agent"
```

---

### Task 7: Integration Tests

**Files:**
- Modify: `tests/agent/test_agent.py`

- [ ] **Step 1: Add integration tests for the full pipeline**

If `tests/agent/test_agent.py` doesn't exist yet, create it. Otherwise append:

```python
from unittest.mock import MagicMock
from src.agent.agent import Agent
from src.tools.base import ToolRegistry
from src.tools.bash_tool import BashTool


class TestAgentContextCompression:
    def test_large_tool_result_gets_persisted_marker(self, tmp_path):
        registry = ToolRegistry()
        bash = BashTool()
        registry.register(bash)
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="tool_use", id="t1", name="bash", input={"command": "echo hi"})],
            stop_reason="tool_use",
        )
        agent = Agent(provider, registry)
        # We need to trigger a turn that produces a large tool result.
        # Since BashTool.execute runs locally, we can mock the tool instead.
```

Actually, integration tests that exercise the real tool execution while also testing compression are fragile because they depend on the real bash tool. Better approach: mock the tool in the registry so we can control the output size.

```python
    def test_large_tool_result_gets_persisted_marker(self, tmp_path):
        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_bash"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        big_output = "x" * 35000
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="t1", content=big_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[
                MagicMock(type="tool_use", id="t1", name="mock_bash", input={})
            ],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry)
        agent._run_turn("run mock", max_turns=1)

        last_msg = agent.messages[-1]
        assert last_msg["role"] == "user"
        assert any("persisted-output" in str(block.get("content", "")) for block in last_msg["content"])
```

Wait, `Agent._run_turn` appends user input, then calls `_agent_loop`, which calls `_run_one_turn`. `_run_one_turn` calls provider.chat, gets tool_use, executes tool, appends results. So after `_run_turn`, `agent.messages[-1]` should be the user message containing tool_result blocks.

But `_run_turn` also appends the initial user message at index 0. The tool results are appended later. After max_turns=1, the loop stops after one turn. `agent.messages` will be:
- [0] user "run mock"
- [1] assistant tool_use
- [2] user tool_result

So `agent.messages[2]` is the one to inspect.

Also, `PersistedOutputManager` writes to `.task_outputs/tool-results/` by default. In the test, we should set a custom output dir or clean up after.

Let's adjust: set `agent.persisted_output_manager = PersistedOutputManager(output_dir=str(tmp_path / "tool-results"), threshold=30000)` before calling `_run_turn`.

```python
    def test_large_tool_result_gets_persisted_marker(self, tmp_path):
        from src.agent.context import PersistedOutputManager

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        big_output = "x" * 35000
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="t1", content=big_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[
                MagicMock(type="tool_use", id="t1", name="mock_tool", input={})
            ],
            stop_reason="tool_use",
        )

        agent = Agent(provider, registry)
        agent.persisted_output_manager = PersistedOutputManager(
            output_dir=str(tmp_path / "tool-results"),
            threshold=30000,
        )
        agent._run_turn("run mock", max_turns=1)

        tool_result_msg = agent.messages[2]
        assert tool_result_msg["role"] == "user"
        result_block = tool_result_msg["content"][0]
        assert "persisted-output" in result_block["content"]
```

For micro-compactor integration:

```python
    def test_micro_compactor_replaces_old_tool_results(self, tmp_path):
        from src.agent.context import PersistedOutputManager

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.description = "mock"
        mock_tool.input_schema = {}
        small_output = "small"
        mock_tool.execute.return_value = ToolResult(
            tool_use_id="tx", content=small_output, is_error=False
        )
        registry.register(mock_tool)

        provider = MagicMock()
        # Simulate 4 turns, each producing a tool_use then end_turn
        responses = [
            MagicMock(
                content=[MagicMock(type="tool_use", id=f"t{i}", name="mock_tool", input={})],
                stop_reason="tool_use",
            )
            for i in range(4)
        ]
        responses.append(
            MagicMock(content=[MagicMock(type="text", text="done")], stop_reason="end_turn")
        )
        provider.chat.side_effect = responses

        agent = Agent(provider, registry)
        agent.persisted_output_manager = PersistedOutputManager(
            output_dir=str(tmp_path / "tool-results"),
            threshold=30000,
        )
        agent._run_turn("run mock", max_turns=5)

        # Find all tool_result blocks across messages
        tool_results = []
        for msg in agent.messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert len(tool_results) == 4
        assert tool_results[0]["content"] == "(... older tool output omitted)"
        assert tool_results[1]["content"] == "(... older tool output omitted)"
        assert tool_results[2]["content"] == "small"
        assert tool_results[3]["content"] == "small"
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/agent/test_agent.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_agent.py
git commit -m "test(agent): add integration tests for context compression pipeline"
```

---

## Self-Review

**1. Spec coverage:**

| Spec Section | Plan Task |
|-------------|-----------|
| PersistedOutputManager (Layer 1) | Task 1 |
| MicroCompactor (Layer 2) | Task 2 |
| CompactState data model | Task 3 |
| LoopState extension | Task 3 |
| Wire Layer 1 & 2 into Agent loop | Task 4 |
| CompactTool input schema & execute | Task 5 |
| Register CompactTool in CLI | Task 6 |
| Integration tests | Task 7 |

All sections covered.

**2. Placeholder scan:**
- No "TBD", "TODO", or vague steps.
- Every step includes exact file paths, code snippets, and expected test output.
- `CompactTool` input schema matches the spec exactly.

**3. Type consistency:**
- `CompactState` is defined in `src/agent/context.py` and imported into `src/agent/agent.py` and `src/tools/compact_tool.py`.
- `PersistedOutputManager.maybe_persist` signature is consistent between implementation and tests.
- `MicroCompactor.apply` takes `list[dict]` in both tests and implementation.
- `CompactTool` constructor signature is consistent across implementation, tests, and CLI wiring.

No issues found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-s06-context-compression.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** - Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach?**
