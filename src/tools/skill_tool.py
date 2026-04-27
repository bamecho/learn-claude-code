from .base import ToolResult
from .skill_registry import SkillRegistry


class SkillTool:
    name = "skill"
    description = "Load a skill by name to get its full instructions."
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the skill to load.",
            }
        },
        "required": ["name"],
    }

    def __init__(self, skill_registry: SkillRegistry):
        self._registry = skill_registry

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        name = input.get("name", "").strip()
        if not name:
            return ToolResult(
                tool_use_id=tool_use_id,
                content="Missing required 'name' field.",
                is_error=True,
            )
        doc = self._registry.get(name)
        if doc is None:
            available = ", ".join(
                m.name for m in self._registry.list_manifests()
            ) or "none"
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Skill '{name}' not found. Available skills: {available}.",
                is_error=True,
            )
        return ToolResult(
            tool_use_id=tool_use_id,
            content=(
                f'<skill name="{doc.manifest.name}">\n'
                f"{doc.body}\n"
                "</skill>"
            ),
        )
