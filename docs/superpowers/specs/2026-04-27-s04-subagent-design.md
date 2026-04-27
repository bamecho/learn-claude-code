# s04 Subagent Design

## Overview

`s04` introduces a `task` tool that lets the parent agent offload a local subtask to an independent subagent. The subagent runs in a clean message context with the same provider and (a filtered subset of) tools, then returns only its final summary to the parent.

This is the foundation for later multi-agent features (s15–s19). For now it is intentionally minimal: one tool, no persistence, no cross-session state.

---

## Goals

- Give the model a way to say “this subtask should run in a clean context.”
- Keep the change surface small: reuse existing `Agent` loop, `ToolRegistry`, and provider.
- Prevent unbounded recursion by excluding `task` from the subagent’s toolset.
- Cap the subagent at 40 turns to avoid runaway costs.

---

## Non-Goals

- Cross-session persistence for subagent results.
- Parallel subagents (one at a time via `task` calls).
- Special subagent-specific system prompts or personalities.
- Returning structured artifacts (e.g., JSON) from the subagent—just text.

---

## Architecture

```
┌─────────────────┐
│   Parent Agent  │
│   (agent.py)    │
└────────┬────────┘
         │ tool_use: task(prompt=...)
         ▼
┌─────────────────┐
│    TaskTool     │  <-- creates filtered registry, spawns subagent
│   (tools)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Subagent      │  <-- fresh Agent instance, empty messages
│   (agent.py)    │      runs _agent_loop with max_turns=40
└────────┬────────┘
         │ final assistant text
         ▼
┌─────────────────┐
│   ToolResult    │  <-- summary returned to parent
│   (subagent)    │
└─────────────────┘
```

Only three files are touched:

1. **`src/tools/task_tool.py`** — new `TaskTool` implementing the `Tool` Protocol.
2. **`src/agent/agent.py`** — add optional `max_turns` to `LoopState` and enforce it in `_agent_loop`.
3. **`src/cli.py`** — register `TaskTool` in the bootstrap registry.

---

## Data Model

### LoopState (updated)

| Field               | Type          | Description                                    |
|---------------------|---------------|------------------------------------------------|
| `messages`          | list[dict]    | Conversation history.                          |
| `turn_count`        | int           | Current turn number (starts at 1).             |
| `transition_reason` | str \| None   | Why the last turn ended.                       |
| `max_turns`         | int \| None   | **New.** Hard cap on turns. `None` = unlimited.|

### TaskTool Input Schema

```json
{
  "type": "object",
  "properties": {
    "prompt": {
      "type": "string",
      "description": "The subtask instruction."
    }
  },
  "required": ["prompt"]
}
```

---

## Components

### TaskTool

Responsibilities:

- **`execute(tool_use_id, input) -> ToolResult`**
  1. Read `prompt` from `input`. If empty or missing, return `is_error=True`.
  2. Build a new `ToolRegistry` from `self.registry`, **excluding** the tool named `"task"`.
  3. Instantiate a new `Agent` with the same `provider`, the filtered registry, and the same `system`.
  4. Call `agent._run_turn(prompt, max_turns=40)`.
  5. After the loop ends, collect the subagent’s final assistant text from the last assistant message.
  6. If `transition_reason == "max_turns"`, prepend `[Subagent reached turn limit] ` to the summary.
  7. Return the summary as a `ToolResult`.

### Agent Loop Changes

In `_run_one_turn`, at the very start, before calling the provider:

```python
if state.max_turns is not None and state.turn_count >= state.max_turns:
    state.transition_reason = "max_turns"
    return False
```

This guarantees the loop exits before beginning another turn once the cap is reached.

---

## System Prompt Update

The CLI bootstrap (`src/cli.py`) appends the following to the existing system prompt:

```
Use the task tool to delegate independent subtasks to a fresh context.
```

---

## Error Handling

| Scenario                             | Behavior                                                              |
|--------------------------------------|-----------------------------------------------------------------------|
| Empty or missing `prompt`            | `TaskTool` returns `ToolResult` with `is_error=True`.                 |
| Subagent hits 40-turn limit          | Loop forced to `max_turns`; summary prefixed with turn-limit warning. |
| Subagent tool error                  | Existing `tool_result` with `is_error=True` flows back into subagent. |
| Subagent registry has no `task`      | By construction; prevents recursion.                                  |

---

## Testing Strategy

- **Unit tests for `TaskTool`** (`tests/tools/test_task_tool.py`):
  - Empty prompt returns `is_error=True`.
  - The filtered registry excludes `"task"`.
  - Mock provider returning a simple text block; assert summary is returned correctly.
  - Mock provider forcing 40 tool-use turns; assert turn-limit warning appears.

- **Agent-level tests** (`tests/agent/test_agent.py`):
  - `LoopState(max_turns=2)` causes the loop to stop after 2 turns.
  - `_run_one_turn` returns `False` when `turn_count == max_turns`.

---

## File Layout

```
src/
  tools/
    task_tool.py          # NEW
  agent/
    agent.py              # LoopState + max_turns enforcement
  cli.py                  # register TaskTool + system prompt update
tests/
  tools/
    test_task_tool.py     # NEW
  agent/
    test_agent.py         # additional max_turns tests
```

---

## References

- Reference implementation pattern: [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) s04 chapter.
