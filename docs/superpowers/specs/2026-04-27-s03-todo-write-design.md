# s03 TodoWrite Design

## Overview

`s03` introduces a lightweight session planning mechanism. The model can rewrite its current plan, keep one step in focus (`in_progress`), and receive a nudge if it stops refreshing the plan for too many conversation rounds.

This is a session-level aid, not a durable task graph. The plan lives in memory (managed by `TodoManager`) and is rendered to text for the model to see.

---

## Goals

- Give the model a structured way to track multi-step work inside a single session.
- Enforce a simple focus rule: at most one item may be `in_progress` at any time.
- Nudge the model every 3 rounds if it has not updated the plan.
- Keep the change surface minimal: reuse the existing `Tool` Protocol and `Agent` loop.

---

## Non-Goals

- Cross-session persistence of plans.
- A separate `todo_read` tool (reuse `read_file`).
- Complex dependency graphs or scheduling.

---

## Architecture

```
┌─────────────────┐
│   TodoManager   │  <-- holds PlanningState in memory
│   (planning)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    TodoTool     │  <-- standard Tool protocol implementation
│    (tools)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│      Agent      │  <-- detects todo usage each turn, drives reminder logic
│    (agent)      │
└─────────────────┘
```

Three modules are touched:

1. **`src/planning/todo_manager.py`** — `PlanItem`, `PlanningState`, `TodoManager`.
2. **`src/tools/todo_tool.py`** — `TodoTool` implementing the `Tool` Protocol.
3. **`src/agent/agent.py`** — small hooks in `_run_one_turn` to track rounds and inject reminders.

---

## Data Model

### PlanItem

| Field       | Type   | Required | Description                                              |
|-------------|--------|----------|----------------------------------------------------------|
| `content`   | string | yes      | What this step is about.                                 |
| `status`    | string | yes      | One of `pending`, `in_progress`, `completed`.            |
| `activeForm`| string | no       | Present-continuous label shown when step is in progress. |

### PlanningState

| Field                  | Type         | Description                                         |
|------------------------|--------------|-----------------------------------------------------|
| `items`                | list[PlanItem]| Ordered list of plan items.                         |
| `rounds_since_update`  | int          | How many turns have passed since the last `todo` call.|

---

## Components

### TodoManager

Responsibilities:

- **`update(items: list[dict]) -> str`**  
  Validate input, rebuild `PlanningState.items`, reset `rounds_since_update = 0`, and return a rendered summary.
  - Max 12 items.
  - Every item must have non-empty `content`.
  - `status` must be one of the allowed enum values.
  - At most one item may have `status == "in_progress"`; otherwise raise `ValueError`.

- **`note_round_without_update() -> None`**  
  Increment `rounds_since_update`.

- **`reminder() -> str | None`**  
  If `rounds_since_update >= 3` and `items` is not empty, return  
  `<reminder>Refresh your current plan before continuing.</reminder>`  
  Otherwise return `None`.

- **`render() -> str`**  
  Produce human-readable text for the current plan, e.g.:
  ```
  [ ] Read the failing test
  [>] Fix the bug (Fixing the bug)
  [ ] Run tests again

  (1/3 completed)
  ```

### TodoTool

Standard `Tool` Protocol implementation.

- **name**: `todo`
- **description**: `Rewrite the current session plan for multi-step work.`
- **input_schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "items": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "content": {"type": "string"},
            "status": {
              "type": "string",
              "enum": ["pending", "in_progress", "completed"]
            },
            "activeForm": {
              "type": "string",
              "description": "Optional present-continuous label."
            }
          },
          "required": ["content", "status"]
        }
      }
    },
    "required": ["items"]
  }
  ```
- **execute**: delegates to `TodoManager.update()` and returns the rendered text as a `ToolResult`.

### Agent Loop Integration

In `_run_one_turn`, after all tool results have been collected but before appending the user message:

1. Check whether any `tool_use` block in this turn has `name == "todo"`.
2. If yes: `todo_manager.state.rounds_since_update = 0`.
3. If no:
   - `todo_manager.note_round_without_update()`
   - If `todo_manager.reminder()` returns a string, prepend it as a `text` block to the list of results.
4. Append the results (with possible reminder) to messages as a user message.

This keeps the reminder logic out of the tool and inside the orchestration layer, exactly matching the reference design.

---

## System Prompt Update

The CLI bootstrap (`src/cli.py`) appends the following guidance to the system prompt:

```
Use the todo tool for multi-step work.
Keep exactly one step in_progress when a task has multiple steps.
Refresh the plan as work advances. Prefer tools over prose.
```

---

## Error Handling

| Scenario                              | Behavior                                                |
|---------------------------------------|---------------------------------------------------------|
| Empty `items` array                   | Valid — clears the session plan.                        |
| `status` not in allowed enum          | `TodoManager.update()` raises `ValueError`; tool returns `is_error=True`. |
| More than one `in_progress`           | `TodoManager.update()` raises `ValueError`; tool returns `is_error=True`. |
| Missing `content` on an item          | `TodoManager.update()` raises `ValueError`; tool returns `is_error=True`. |
| Exceeds 12 items                      | `TodoManager.update()` raises `ValueError`; tool returns `is_error=True`. |

---

## Testing Strategy

- **Unit tests for `TodoManager`**:
  - Happy-path update and render.
  - Validation of status enum, single `in_progress`, non-empty content, 12-item limit.
  - Reminder generation at and below the threshold.
- **Unit tests for `TodoTool`**:
  - Execute delegates correctly and returns `ToolResult`.
- **Agent-level tests**:
  - Mock provider that uses `todo`; assert `rounds_since_update` resets.
  - Mock provider that does **not** use `todo` for 3 turns; assert reminder text appears in the next user message.

---

## File Layout

```
src/
  planning/
    __init__.py
    todo_manager.py
  tools/
    todo_tool.py
  agent/
    agent.py        (minor edits)
  cli.py            (system prompt edit + register TodoTool)
tests/
  planning/
    test_todo_manager.py
  tools/
    test_todo_tool.py
  agent/
    test_agent.py   (additional tests)
```

---

## References

- Reference implementation pattern: [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) s03 chapter.
