# Spec: s07 Permission System

## Objective
Add a permission-checking layer that gates every tool invocation in the Agent loop. The system must support:
- **Per-tool rules** (allow / deny / ask)
- **Execution modes** (`default`, `plan`, `auto`) that apply blanket policies
- **User confirmation** for operations that fall through to `ask`

Success looks like: dangerous or destructive operations can be blocked or require explicit approval without changing individual tool implementations.

## Tech Stack
- Python >= 3.11 (existing)
- pytest (existing)
- No new external dependencies

## Commands
```bash
# Run permission tests
uv run pytest tests/permissions/ -v

# Run all tests
uv run pytest tests/ -v
```

## Project Structure
```
src/
  permissions/
    __init__.py         # exports: PermissionRule, PermissionEngine, check_permission
    engine.py           # core logic: rule matching + mode fallback
    constants.py        # WRITE_TOOLS, READ_ONLY_TOOLS sets
  agent/
    agent.py            # integrate permission check before tool.execute()
tests/
  permissions/
    __init__.py
    test_engine.py      # unit tests for rule matching, modes, fallback
    test_integration.py # tests via mocked agent loop
```

## Code Style
```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class PermissionRule:
    tool: str
    behavior: Literal["allow", "deny", "ask"]
    path: str | None = None
    content: str | None = None
```
- Use `Literal` for string enums.
- Keep permission logic pure (no I/O inside `check_permission`).
- CLI prompt lives in `agent.py`, not the engine.

## Testing Strategy
- **Framework:** pytest (existing)
- **Test levels:**
  - Unit: `test_engine.py` covers rule matching, mode behavior, and fallback logic with no mocking.
  - Integration: `test_integration.py` runs a mocked `Agent` loop to verify `ask` flows produce a user prompt and respect the answer.
- **Coverage target:** 100% of `src/permissions/`.

## Boundaries
- **Always:** Run tests before declaring done; validate inputs (e.g. `behavior` must be one of the three literals).
- **Ask first:** Adding new tool categories beyond `WRITE_TOOLS` / `READ_ONLY_TOOLS`; changing where the prompt for `ask` is rendered.
- **Never:** Store secrets in permission rules; modify tool implementations to embed their own permission checks.

## Success Criteria
- [ ] `PermissionEngine.check(tool_name, tool_input)` returns `{"behavior": ..., "reason": ...}` for every call.
- [ ] Bash commands pass through `BashSecurityValidator` before rules (severe patterns → deny; others → ask).
- [ ] Rule matching supports `fnmatch` globs for `tool`, `path`, and `content`.
- [ ] `deny` rules match first; then `allow` rules; then `ask` rules; then mode checks; finally fallback.
- [ ] `plan` mode denies all `WRITE_TOOLS` and **auto-allows** everything else.
- [ ] `auto` mode allows all `READ_ONLY_TOOLS`; everything else falls through to rules / ask.
- [ ] When behavior is `ask`, the CLI prompts the user with the tool name and reason; `n` or empty string denies, `y` allows, `always` permanently adds an allow rule.
- [ ] Consecutive user denials are counted; reaching a threshold prints a circuit-breaker hint.
- [ ] Runtime CLI commands `/mode <default|plan|auto>` and `/rules` are supported.
- [ ] If permission is denied (rule or user), the tool is not executed and a `ToolResult` with `is_error=True` is returned to the LLM.
- [ ] All new code has passing unit and integration tests.

## Open Questions
1. Should `ask` support a non-interactive flag (e.g. for CI/testing)? **Assumption:** yes, expose an `interactive: bool` toggle on `Agent` so tests can bypass `input()`.
2. Should `path` / `content` matching be glob/regex or exact substring? **Assumption:** exact substring for the minimal system; can be upgraded later.
