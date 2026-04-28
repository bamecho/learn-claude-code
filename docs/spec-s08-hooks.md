# Spec: s08 Hook System

## Objective
Add a hook system that lets external shell commands observe, intercept, or supplement the Agent's behavior at 3 fixed lifecycle points. The system is teaching-oriented: one unified return semantics, minimal events, no dynamic registration UI.

Hooks are loaded from `.hooks.json` in the working directory. Each hook is a shell command executed via `subprocess.run`. This mirrors the real Claude Code extension pattern.

## Tech Stack
- Python >= 3.11 (existing)
- pytest (existing)
- No new external dependencies

## Commands
```bash
# Run hook tests
uv run pytest tests/hooks/ -v

# Run all tests
uv run pytest tests/ -v
```

## Project Structure
```
src/
  hooks/
    __init__.py         # exports: HookRunner, load_hooks
    loader.py           # loads .hooks.json
    runner.py           # HookRunner: event dispatch + subprocess execution
  agent/
    agent.py            # integrates hooks at 3 call sites
  .claude/              # workspace trust marker
    .claude_trusted     # hooks only run if this file exists (or sdk_mode=True)
  .hooks.json           # user-level hook config (not in repo)
tests/
  hooks/
    __init__.py
    test_runner.py      # unit tests for HookRunner subprocess behavior
    test_loader.py      # unit tests for load_hooks JSON parsing
    test_integration.py # tests hook behavior inside mocked Agent loop
```

## Configuration Format
`.hooks.json` in the working directory:
```json
{
  "hooks": {
    "SessionStart": [
      {"command": "echo 'Session started'"}
    ],
    "PreToolUse": [
      {"command": "echo 'blocked' >&2; exit 1", "matcher": "bash"}
    ],
    "PostToolUse": [
      {"command": "echo 'done' >&2; exit 2", "matcher": "*"}
    ]
  }
}
```

- `command`: shell command to execute
- `matcher`: optional tool name filter (`*` = all tools; exact name = match only that tool)

## Shell Contract
Each hook command is executed with `subprocess.run(command, shell=True, capture_output=True)`.

**Exit codes:**
- `0` -> continue normally
- `1` -> block current action (reason read from stderr)
- `2` -> inject a supplemental message (read from stderr), then continue

**Environment variables:**
- `HOOK_EVENT` — event name
- `HOOK_TOOL_NAME` — tool name (PreToolUse/PostToolUse)
- `HOOK_TOOL_INPUT` — JSON string of tool input (max 10KB)
- `HOOK_TOOL_OUTPUT` — tool output string (PostToolUse only, max 10KB)

**JSON stdout protocol (exit 0 only):**
- `{"updatedInput": {...}}` — modifies the tool input before execution
- `{"additionalContext": "..."}` — injects a message into results
- `{"permissionDecision": "allow|deny|ask"}` — overrides permission decision

## Workspace Trust
Hooks only run if the workspace is trusted. Trust is indicated by the presence of `.claude/.claude_trusted` in the working directory. Pass `sdk_mode=True` to `HookRunner` to bypass the trust check (e.g., for testing).

## Code Style
- `HookRunner.run(event, context)` returns:
  ```python
  {
      "blocked": bool,
      "messages": list[str],
      "block_reason": str,
      "permission_override": str | None,
  }
  ```
- `context` is mutated in-place for `updatedInput`
- All errors are logged and swallowed; the loop never crashes because of a hook

## Testing Strategy
- **Framework:** pytest (existing)
- **Test levels:**
  - Unit: `test_runner.py` covers subprocess execution, exit codes, matchers, env vars, JSON stdout, trust, timeout
  - Unit: `test_loader.py` covers JSON parsing, error resilience
  - Integration: `test_integration.py` runs mocked `Agent` to verify block/inject/updatedInput at all 3 events
- **Coverage target:** 100% of `src/hooks/`.

## Boundaries
- **Always:** Run tests before declaring done; handle missing config / bad JSON / command failure gracefully.
- **Ask first:** Adding new hook events beyond the 3 teaching events.
- **Never:** Modify tool implementations to embed hook calls; add UI for live hook registration.

## Success Criteria
- [x] `HookRunner.run(event, context)` returns `{"blocked": ..., "messages": ..., "block_reason": ..., "permission_override": ...}`.
- [x] Hooks are loaded from `.hooks.json` with `{"hooks": {"EventName": [{"command": "...", "matcher": "*"}]}}` format.
- [x] Each hook is executed as a shell command via `subprocess.run`.
- [x] `matcher` filters hooks by tool name (`*` matches all).
- [x] Missing/broken config → empty handlers, no crash.
- [x] Command failure/timeout → logged, skipped, loop continues.
- [x] Workspace trust gate: hooks refuse to run unless `.claude/.claude_trusted` exists or `sdk_mode=True`.
- [x] `SessionStart` fires once in `run_interactive()` before the user input loop.
- [x] `PreToolUse` fires before each tool execution.
  - `blocked=True` → skip execution, append `is_error=True` tool_result with block_reason.
  - `messages` → append as separate `tool_result` blocks before the real result.
  - `updatedInput` → mutates `context["tool_input"]` before passing to tool.
- [x] `PostToolUse` fires after each tool execution.
  - `messages` → appended to tool output string.
- [x] `Agent` accepts optional `hook_runner` parameter; no runner = zero change to behavior.
- [x] All new code has passing unit and integration tests.

## Open Questions
1. Should hook events expand beyond the 3 teaching events? **Assumption:** not in this stage; add later when the base pattern is understood.
2. Should hooks support async I/O or long-running commands? **Assumption:** no; teaching edition uses a fixed 30s timeout and synchronous subprocess.
