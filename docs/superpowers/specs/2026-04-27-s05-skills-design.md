# s05 Skills Design

## Overview

`s05` introduces a `skill` tool that lets the Agent dynamically load skill instructions from `.claude/skills/*/SKILL.md`. The system keeps the skill metadata (name and description) lightweight in the system prompt, while the full body is only loaded when the model explicitly asks for it via the `skill` tool.

This is the foundation for the skill system used throughout the project. For now it is intentionally minimal: one tool, no persistence, no cross-session state.

---

## Goals

- Let the model know which skills are available via a lightweight manifest in the system prompt.
- Let the model load a skill’s full instructions on demand by calling the `skill` tool.
- Keep the change surface small: reuse the existing `Tool` protocol and `ToolRegistry`.

---

## Non-Goals

- Persist loaded skills across sessions.
- Automatically inject a skill’s body into the system prompt on load.
- Skill nesting or skill-to-skill dependencies.
- Hot-reloading skills at runtime.

---

## Architecture

```
┌─────────────────────────────────────────┐
│  cli.py 启动时                           │
│  1. SkillRegistry 扫描 .claude/skills/*  │
│  2. 提取所有 SKILL.md 的 YAML frontmatter │
│  3. 生成 "Available skills: ..." 注入    │
│     system prompt                        │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  用户输入 → Agent → LLM                 │
│  LLM 根据 system prompt 中的 skill 列表 │
│  自行判断是否需要调用 skill 工具          │
└─────────────────────────────────────────┘
                    │
        skill(name="brainstorming")
                    │
                    ▼
┌─────────────────────────────────────────┐
│  SkillTool.execute()                    │
│  1. 从 SkillRegistry 读取完整 body      │
│  2. 作为 ToolResult 返回给 LLM          │
└─────────────────────────────────────────┘
```

Only three files are touched:

1. **`src/tools/skill_registry.py`** — new `SkillRegistry` class for scanning and parsing skill files.
2. **`src/tools/skill_tool.py`** — new `SkillTool` implementing the `Tool` Protocol.
3. **`src/cli.py`** — create `SkillRegistry`, inject skill list into system prompt, register `SkillTool`.

---

## Data Model

### SkillManifest

```python
@dataclass
class SkillManifest:
    name: str
    description: str
```

### SkillDocument

```python
@dataclass
class SkillDocument:
    manifest: SkillManifest
    body: str
```

### SkillRegistry

```python
class SkillRegistry:
    _skills: dict[str, SkillDocument]

    def list_manifests(self) -> list[SkillManifest]
    def get(self, name: str) -> SkillDocument | None
```

### SkillTool Input Schema

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Name of the skill to load."
    }
  },
  "required": ["name"]
}
```

---

## Components

### SkillRegistry

Responsibilities:

- **`__init__(skills_dir: str)`**
  1. Initialize `self._skills = {}`.
  2. Walk `skills_dir/*/` directories.
  3. For each directory, look for `SKILL.md`.
  4. Read the file and split into YAML frontmatter and body.
  5. Parse frontmatter for `name` and `description` (both required). Frontmatter parsing uses a lightweight inline regex for `key: value` pairs to avoid adding a heavy YAML dependency.
  6. If parsing fails or required fields are missing, skip the skill and print a warning.
  7. Store `SkillDocument(manifest, body)` keyed by `name`.

- **`list_manifests() -> list[SkillManifest]`**
  - Return `[doc.manifest for doc in self._skills.values()]`.

- **`get(name: str) -> SkillDocument | None`**
  - Return `self._skills.get(name)`.

### SkillTool

Responsibilities:

- **`execute(tool_use_id, input) -> ToolResult`**
  1. Read `name` from `input`. If empty or missing, return `ToolResult` with `is_error=True`.
  2. Call `self.skill_registry.get(name)`.
  3. If not found, return `is_error=True` with a message listing available skill names.
  4. If found, return the `skill_document.body` as the `ToolResult.content`.

### cli.py Changes

- Create `SkillRegistry(skills_dir=".claude/skills")` during bootstrap.
- Append the following to the existing system prompt (only if manifests are non-empty):
  ```
  Available skills: brainstorming (Brainstorming Ideas Into Designs), code-review (Checklist for reviewing code changes), ...
  Use the skill tool to load a skill when its instructions are relevant to the current task.
  ```
- Register `SkillTool(skill_registry)` in the `ToolRegistry`.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `.claude/skills/` 目录不存在 | `SkillRegistry` 初始化为空列表，system prompt 中不显示 skill 段，不影响其他功能 |
| `SKILL.md` 缺少 frontmatter 或必需字段 | 跳过该 skill，打印 warning |
| `SkillTool` 调用时 `name` 为空/缺失 | 返回 `is_error=True` |
| `SkillTool` 调用时 `name` 不存在 | 返回 `is_error=True`，附带可用 skill 列表 |
| `SkillTool` 调用时文件已被删除 | 返回 `is_error=True`（由于初始化时缓存，运行时删文件不影响） |

---

## Testing Strategy

- **Unit tests for `SkillRegistry`** (`tests/tools/test_skill_registry.py`):
  - Normal directory scan parses frontmatter correctly.
  - File missing frontmatter is skipped.
  - Missing required fields cause the skill to be skipped.
  - Non-existent directory returns empty manifests.

- **Unit tests for `SkillTool`** (`tests/tools/test_skill_tool.py`):
  - Empty or missing `name` returns `is_error=True`.
  - Non-existent `name` returns `is_error=True` with available names.
  - Existing `name` returns the correct body.

---

## File Layout

```
src/
  tools/
    skill_registry.py     # NEW
    skill_tool.py         # NEW
  cli.py                  # register SkillTool + system prompt update
tests/
  tools/
    test_skill_registry.py  # NEW
    test_skill_tool.py      # NEW
```

---

## References

- Reference implementation pattern: [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) s05 chapter.
